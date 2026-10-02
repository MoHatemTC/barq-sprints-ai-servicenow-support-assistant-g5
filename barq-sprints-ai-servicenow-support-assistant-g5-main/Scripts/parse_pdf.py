import os
import gc
import json
import base64
import sys
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from litellm import completion
import pymupdf as fitz  # fitz alias kept for compatibility with existing code

# Suppress PyMuPDF unclosed-document warnings produced by Docling's internal BytesIO handling
import warnings
warnings.filterwarnings("ignore", message=".*still open.*", category=UserWarning)

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    AcceleratorOptions,
    AcceleratorDevice,
    RapidOcrOptions,
)
from docling_core.types.doc import DocItemLabel, TableItem, PictureItem

# Load environment variables from .env file (LITELLM_BASE_URL, LITELLM_API_KEY, LLM_MODEL)
load_dotenv()

# ==========================================
# PHASE 1: DOCUMENT EXTRACTION
# ==========================================

def _create_converter(device: AcceleratorDevice) -> DocumentConverter:
    """Creates a document converter with image generation enabled and specified accelerator device."""
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_page_images = True
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = RapidOcrOptions(
        lang=[value.strip() for value in os.getenv("OCR_LANGUAGES", "english,arabic").split(",") if value.strip()]
    )
    pipeline_options.accelerator_options = AcceleratorOptions(device=device)
    
    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )


def normalize_extracted_text(text: str) -> str:
    """Normalize composed Unicode without reversing logical RTL text."""
    return unicodedata.normalize("NFC", text)

import sys
import os
sys.stdout.reconfigure(line_buffering=True)


def check_hardware_acceleration() -> tuple[AcceleratorDevice, str]:
    """Verifies GPU availability (NVIDIA CUDA) and falls back to CPU if unavailable or failing."""
    print("=" * 60, flush=True)
    print("[Hardware Check] Testing CUDA GPU acceleration...", flush=True)
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            cuda_ver = torch.version.cuda
            # Test CUDA memory allocation
            _ = torch.tensor([1.0], device="cuda")
            msg = f"GPU ACTIVE: {gpu_name} ({vram_gb:.2f} GB VRAM | CUDA {cuda_ver})"
            print(f"[Hardware Check] ✓ {msg}", flush=True)
            print("=" * 60 + "\n", flush=True)
            return AcceleratorDevice.CUDA, msg
    except Exception as e:
        print(f"[Hardware Check] ⚠ GPU test failed ({e}). Falling back to CPU...", flush=True)
    
    msg = "CPU ACTIVE (Fallback mode)"
    print(f"[Hardware Check] ℹ {msg}", flush=True)
    print("=" * 60 + "\n", flush=True)
    return AcceleratorDevice.CPU, msg


def _create_converter_with_fallback() -> DocumentConverter:
    """Creates a DocumentConverter once (GPU first, CPU fallback)."""
    device, _ = check_hardware_acceleration()
    try:
        return _create_converter(device)
    except Exception as e:
        print(f"[Phase 1] Converter creation failed on {device.value}: {e}. Retrying CPU...", flush=True)
        return _create_converter(AcceleratorDevice.CPU)


def convert_pdf_with_fallback(
    pdf_path: str,
    page_range: tuple[int, int] | None = None,
    converter: DocumentConverter | None = None,
):
    """Runs conversion using a pre-built converter (or creates one)."""
    _converter = converter or _create_converter_with_fallback()
    try:
        return _converter.convert(pdf_path, page_range=page_range or (1, sys.maxsize))
    except Exception as e:
        if converter is not None:
            raise
        print(f"[Phase 1] Conversion failed: {e}. Retrying with CPU converter...", flush=True)
        cpu_converter = _create_converter(AcceleratorDevice.CPU)
        return cpu_converter.convert(pdf_path, page_range=page_range or (1, sys.maxsize))


def extract_pdf_structure(pdf_path: str, output_dir: str, max_workers: int = 1):
    """Reads PDF, extracts text/tables in order, saves images, and writes draft markdown."""
    import time
    output_path = Path(output_dir)
    images_dir = output_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    folder_name = output_path.name
    doc_prefix = folder_name.split('_')[0] if '_' in folder_name else Path(pdf_path).stem

    # Build converter ONCE
    print("[Phase 1] Loading Layout & OCR AI models...", flush=True)
    shared_converter = _create_converter_with_fallback()

    # Collect page metadata and optional source title via fitz
    page_count = 0
    pages_meta = []
    source_title = None
    with fitz.open(pdf_path) as source_pdf:
        page_count = len(source_pdf)
        if page_count > 0:
            first_page_text = source_pdf[0].get_text("text") or ""
            for line in (line.strip() for line in first_page_text.splitlines()):
                if "assistant" in line.lower() and len(line) >= 20:
                    source_title = line
                    break

        for page_number, source_page in enumerate(source_pdf, 1):
            rotation = int(source_page.rotation or 0)
            has_text = bool((source_page.get_text("text") or "").strip())
            page_meta = {
                "page": page_number,
                "ocr_used": not has_text,
                "ocr_engine": "rapidocr",
                "ocr_languages": [
                    value.strip()
                    for value in os.getenv("OCR_LANGUAGES", "english,arabic").split(",")
                    if value.strip()
                ],
                "rotation_detected_deg": rotation,
                "rotation_corrected_deg": rotation,
                "warnings": [],
            }
            if rotation:
                page_meta["warnings"].append(
                    "Rotation detected; Docling page conversion applied the page orientation."
                )
            pages_meta.append(page_meta)

    # Process PDF page by page to provide tracing and avoid memory / backend unload issues
    markdown_content = []
    images_metadata = []
    image_counter = 1

    print(f"[Phase 1] Models loaded. Processing PDF document '{pdf_path}' ({page_count} pages total) page-by-page...", flush=True)
    t_conv_start = time.time()
    
    for page_number in range(1, page_count + 1):
        print(f"[Phase 1] Scanning & extracting page {page_number}/{page_count}...", flush=True)
        t_page_start = time.time()
        
        try:
            result = convert_pdf_with_fallback(pdf_path, page_range=(page_number, page_number), converter=shared_converter)
            doc = result.document
        except Exception as conv_err:
            print(f"[Phase 1 Error] Page {page_number} conversion failed: {conv_err}", flush=True)
            pages_meta[page_number - 1]["warnings"].append(f"Page conversion failed: {conv_err}")
            continue

        markdown_content.append(f"<!-- page: {page_number} -->")
        page_meta = pages_meta[page_number - 1]
        text_count = 0
        table_count = 0
        image_count = 0

        for item, level in doc.iterate_items():
            try:
                # Fallback to current page_number if item.prov is missing or empty
                item_page = item.prov[0].page_no if getattr(item, "prov", None) and item.prov else page_number
                
                if item.label in [
                    DocItemLabel.TEXT, DocItemLabel.TITLE, DocItemLabel.PARAGRAPH,
                    DocItemLabel.SECTION_HEADER, DocItemLabel.LIST_ITEM
                ]:
                    if getattr(item, "text", None):
                        markdown_content.append(normalize_extracted_text(item.text))
                        text_count += 1
                elif item.label == DocItemLabel.TABLE and isinstance(item, TableItem):
                    markdown_content.append("\n" + item.export_to_markdown(doc=doc) + "\n")
                    table_count += 1
                elif item.label in [DocItemLabel.PICTURE, DocItemLabel.CHART]:
                    placeholder = f"<!-- IMAGE_PLACEHOLDER_{image_counter} -->"
                    markdown_content.append(f"\n{placeholder}\n")
                    image_rel_path = None
                    image_status = "pending"
                    image_error = None
                    image_width = None
                    image_height = None
                    if isinstance(item, PictureItem):
                        try:
                            img = item.get_image(doc=doc)
                            if img:
                                image_width, image_height = img.size
                                img_filename = f"image_{image_counter}.png"
                                img_save_path = images_dir / img_filename
                                img.save(img_save_path)
                                image_rel_path = f"images/{img_filename}"
                                image_count += 1
                            else:
                                image_status = "missing"
                        except Exception as img_err:
                            image_status = "failed"
                            image_error = str(img_err)
                    if getattr(item, "prov", None) and item.prov:
                        prov = item.prov[0]
                        image_meta = {
                            "image_id": placeholder,
                            "image_index": image_counter,
                            "doc_prefix": doc_prefix,
                            "image_path": str(output_path / image_rel_path) if image_rel_path else None,
                            "page_no": item_page,
                            "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
                            "status": image_status,
                            "width": image_width,
                            "height": image_height,
                            "is_diagram_candidate": True,
                        }
                        if image_error:
                            image_meta["error"] = image_error
                        images_metadata.append(image_meta)
                    image_counter += 1
            except Exception as item_error:
                page_meta["warnings"].append(f"Item extraction failed: {item_error}")

        elapsed_page = time.time() - t_page_start
        print(f"[Phase 1] [Page {page_number:02d}/{page_count:02d}] Done in {elapsed_page:.1f}s - Extracted {text_count} text blocks, {table_count} tables, {image_count} images", flush=True)

    print(f"[Phase 1] Document conversion finished in {time.time()-t_conv_start:.1f}s!", flush=True)
    
    final_markdown = "\n\n".join(markdown_content)

    try:
        with open(output_path / "document_draft.md", "w", encoding="utf-8") as f:
            f.write(final_markdown)

        # Determine document title from filename or doc items
        title_str = source_title or Path(pdf_path).stem.replace('_', ' ').title()
        for item_text in markdown_content:
            if item_text.startswith("#"):
                title_str = item_text.lstrip("# ").strip()
                break

        source_type = Path(pdf_path).suffix.lstrip('.').lower() or "pdf"
        parsed_at_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        manifest_path = output_path / "manifest.json"
        manifest_payload = {
            "doc_id": output_path.name,
            "title": title_str,
            "source_file": Path(pdf_path).name,
            "source_type": source_type,
            "page_count": page_count,
            "parsed_at": parsed_at_iso,
            "parser": "Docling + RapidOCR + LiteLLM Vision",
            "ocr_engine": "rapidocr",
            "ocr_languages": pages_meta[0]["ocr_languages"] if pages_meta else [],
            "status": "partial_failure" if any(page.get("error") for page in pages_meta) else "in_progress",
            "pages": pages_meta,
            "images_to_process": images_metadata
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Phase 1 Error] Failed writing draft files to '{output_dir}': {e}", flush=True)
        raise e

    print(f"[Phase 1] Completed! Saved draft and manifest to {output_dir}", flush=True)


# ==========================================
# PHASE 2: LLM VISION PROCESSING
# ==========================================

def encode_image_to_base64(image_path: str) -> str:
    """Reads an image file and returns its Base64 encoded string."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"[Phase 2 Error] Failed to encode image '{image_path}': {e}")
        raise e

def extract_insights_with_llm(base64_image: str) -> str:
    """Sends the base64 image to the LiteLLM endpoint with a strict extraction prompt."""
    
    prompt_text = """
    Analyze this image carefully. It is extracted from a technical runbook.
    1. Extract all text exactly as written, preserving Arabic and English seamlessly.
    2. If this is a flowchart, diagram, or schematic: describe the relationships, steps, branches, and connections clearly. Use markdown blockquotes (>) and bullet points to represent the flow structure.
    3. If this is a nested table or complex UI screenshot: convert the structural data into a clean markdown format.
    4. Do not include any conversational filler (e.g., 'Here is the extraction'). Output ONLY the structural markdown text.
    """
    
    model_name = os.getenv("LLM_MODEL", "gemini/gemini-3.6-flash")
    api_base = os.getenv("LITELLM_BASE_URL")
    api_key = os.getenv("LITELLM_API_KEY")

    response = completion(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }
        ],
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai" if api_base else None
    )
    return response.choices[0].message.content.strip()


from concurrent.futures import ThreadPoolExecutor, as_completed

def process_images_from_manifest(output_dir: str, max_workers: int = 5) -> dict:
    """Reads manifest, processes images in parallel via LLM, and returns a mapping of placeholders to text."""
    output_path = Path(output_dir)
    manifest_path = output_path / "manifest.json"
    
    if not manifest_path.exists():
        print("[Phase 2] Manifest not found. Skipping image processing.", flush=True)
        return {}

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
    except Exception as e:
        print(f"[Phase 2 Error] Failed to read or parse manifest.json: {e}", flush=True)
        raise e
    
    images = manifest_data.get("images_to_process", [])
    extracted_data_map = {}
    failed_images = []

    print(f"[Phase 2] Starting parallel LLM extraction for {len(images)} images (max {max_workers} workers)...", flush=True)
    
    folder_name = output_path.name
    default_doc_prefix = folder_name.split('_')[0] if '_' in folder_name else "doc"

    def process_single_image(idx_and_meta):
        idx, img_meta, diagram_num = idx_and_meta
        img_id = img_meta["image_id"]
        img_path = img_meta.get("image_path")
        img_index = img_meta.get("image_index", idx)
        doc_prefix = img_meta.get("doc_prefix", default_doc_prefix)
        img_label = f"{doc_prefix} image {img_index}"
        rel_img_path = os.path.relpath(img_path, output_dir) if img_path else ""
        diagram_label = f"Diagram {diagram_num}"

        # Check if already extracted in previous successful run
        if img_meta.get("status") == "success" and img_meta.get("extracted_text"):
            print(f"[Phase 2] Image {img_label} already extracted. Using cached result.", flush=True)
            llm_text = img_meta["extracted_text"]
            llm_lines = [f"> {line}" if line.strip() else ">" for line in llm_text.splitlines()]
            blockquoted_text = "\n".join(llm_lines)
            formatted_text = f"\n\n> **{diagram_label}**\n> ![{img_label}]({rel_img_path})\n>\n{blockquoted_text}\n"
            return (img_id, formatted_text, img_meta, None)

        if img_path and os.path.exists(img_path):
            print(f"[Phase 2] Analyzing {img_path} ({img_label}) with LLM...", flush=True)
            try:
                base64_img = encode_image_to_base64(img_path)
                llm_text = extract_insights_with_llm(base64_img)
                
                llm_lines = [f"> {line}" if line.strip() else ">" for line in llm_text.splitlines()]
                blockquoted_text = "\n".join(llm_lines)
                formatted_text = f"\n\n> **{diagram_label}**\n> ![{img_label}]({rel_img_path})\n>\n{blockquoted_text}\n"
                
                img_meta["extracted_text"] = llm_text
                img_meta["status"] = "success"
                img_meta.pop("error", None)
                print(f"[Phase 2] Completed {img_label}", flush=True)
                return (img_id, formatted_text, img_meta, None)
            except Exception as img_err:
                print(f"[Phase 2 Error] Failed processing {img_label}: {img_err}", flush=True)
                img_meta["status"] = "failed"
                img_meta["error"] = str(img_err)
                failure_text = f"\n\n> **{diagram_label}**\n> ![{img_label}]({rel_img_path})\n> [Image extraction failed: {img_label}]\n"
                return (img_id, failure_text, img_meta, img_label)
        else:
            print(f"[Phase 2 Warning] Image file not found for {img_id}", flush=True)
            img_meta["status"] = "missing"
            failure_text = f"\n\n> **{diagram_label}** *(image file missing)*\n"
            return (img_id, failure_text, img_meta, None)

    # Build items list with sequential diagram numbering (counts ALL images, including decorative)
    items_to_process = [(idx, img_meta, idx) for idx, img_meta in enumerate(images, 1)]
    
    with ThreadPoolExecutor(max_workers=min(max_workers, len(images) or 1)) as executor:
        futures = [executor.submit(process_single_image, item) for item in items_to_process]
        for future in as_completed(futures):
            img_id, formatted_text, updated_meta, failed_label = future.result()
            if formatted_text is not None:
                extracted_data_map[img_id] = formatted_text
            if failed_label:
                failed_images.append(failed_label)

    # Save manifest with status and timestamp
    page_failures = any(page.get("error") for page in manifest_data.get("pages", []))
    manifest_data["status"] = "completed" if not failed_images and not page_failures else "partial_failure"
    manifest_data["parsed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Phase 2 Error] Could not update manifest.json: {e}", flush=True)

    if failed_images:
        raise RuntimeError(f"Image LLM extraction failed for {len(failed_images)} images: {failed_images}")

    print("[Phase 2] Image extraction completed successfully.", flush=True)
    return extracted_data_map


# ==========================================
# PHASE 3: FINAL ASSEMBLY
# ==========================================

def assemble_final_markdown(output_dir: str, extraction_map: dict):
    """Replaces placeholders in the draft markdown with the LLM extracted text."""
    output_path = Path(output_dir)
    draft_path = output_path / "document_draft.md"
    final_path = output_path / "document.md"
    
    if not draft_path.exists():
        print("[Phase 3 Error] Draft document not found. Assembly aborted.")
        raise FileNotFoundError(f"Draft document not found at {draft_path}")

    try:
        with open(draft_path, "r", encoding="utf-8") as f:
            content = f.read()

        print("[Phase 3] Injecting LLM extractions into the final document...")
        
        for placeholder, extracted_text in extraction_map.items():
            content = content.replace(placeholder, extracted_text)

        with open(final_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[Phase 3] Final document successfully generated at: {final_path}")
    except Exception as e:
        print(f"[Phase 3 Error] Assembly failed: {e}")
        raise e


# ==========================================
# MAIN PIPELINE RUNNER
# ==========================================

def run_full_pipeline(pdf_file_path: str, output_directory: str, overwrite: bool = False, max_workers: int = 5):
    """Orchestrates the entire PDF parsing, LLM extraction, and assembly process."""
    output_path = Path(output_directory)
    final_file = output_path / "document.md"
    manifest_path = output_path / "manifest.json"

    # Prevent running twice if document.md exists AND manifest status is 'completed'
    if not overwrite and final_file.exists() and final_file.stat().st_size > 0:
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                if m_data.get("status") == "completed":
                    print("========================================")
                    print(f"[Pipeline Skipped] Document already fully processed and verified at '{final_file}'.")
                    print("Set overwrite=True to force re-execution.")
                    print("========================================")
                    return
                else:
                    print(f"[Pipeline Info] Previous run was incomplete (status: '{m_data.get('status')}'). Resuming pipeline execution...")
            except Exception:
                pass
        else:
            print(f"[Pipeline Skipped] Document already exists at '{final_file}'.")
            return

    if not os.path.exists(pdf_file_path):
        err_msg = f"Input PDF file does not exist: '{pdf_file_path}'"
        print(f"[Pipeline Error] {err_msg}")
        raise FileNotFoundError(err_msg)

    print("========================================")
    print(f"Starting Document Parsing Pipeline")
    print(f"Target: {pdf_file_path}")
    print(f"Output: {output_directory}")
    print(f"Concurrency: {max_workers} workers")
    print("========================================\n")

    try:
        # Step 1: Extract structure and images with parallel workers
        extract_pdf_structure(pdf_file_path, output_directory, max_workers=max_workers)
        print("-" * 40)
        
        # Step 2: Run LLM Vision on extracted images with parallel workers
        llm_extractions = process_images_from_manifest(output_directory, max_workers=max_workers)
        print("-" * 40)
        
        # Step 3: Assemble into document.md
        assemble_final_markdown(output_directory, llm_extractions)
        
        print("\n========================================")
        print("Pipeline Execution Finished Successfully!")
        print("========================================")
    except Exception as e:
        # Cleanup broken output file on failure so it won't false-skip next time
        if final_file.exists():
            try:
                final_file.unlink()
            except Exception:
                pass
        print("\n========================================")
        print(f"[Pipeline Error] Pipeline failed: {e}")
        print("========================================")
        raise e

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse PDF to Markdown with LLM image extraction.")
    parser.add_argument("--pdf", type=str, required=True, help="Path to the input PDF file")
    parser.add_argument("--output", type=str, required=True, help="Directory to save the output markdown and images")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing parsed results")
    parser.add_argument("--max-workers", type=int, default=5, help="Number of concurrent workers for extraction (default: 5)")
    args = parser.parse_args()

    try:
        run_full_pipeline(args.pdf, args.output, args.overwrite, max_workers=args.max_workers)
    except Exception as err:
        print(f"\n[Fatal Error] Pipeline execution halted: {err}")
        sys.exit(1)
