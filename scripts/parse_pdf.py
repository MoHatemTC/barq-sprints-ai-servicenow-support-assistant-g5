import os
import json
import base64
import sys
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from litellm import completion

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling_core.types.doc import DocItemLabel, TableItem, PictureItem

# Load environment variables from .env file (LITELLM_BASE_URL, LITELLM_API_KEY, MODEL_NAME)
load_dotenv()

# ==========================================
# PHASE 1: DOCUMENT EXTRACTION
# ==========================================

def _create_converter(device: AcceleratorDevice) -> DocumentConverter:
    """Creates a document converter with image generation enabled and specified accelerator device."""
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_page_images = True
    pipeline_options.accelerator_options = AcceleratorOptions(device=device)
    
    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )

def convert_pdf_with_fallback(pdf_path: str):
    """Attempts to process the document using GPU first, falls back to CPU on error."""
    try:
        print("[Phase 1] Processing PDF (GPU/AUTO)...")
        converter = _create_converter(AcceleratorDevice.AUTO)
        return converter.convert(pdf_path)
    except Exception as e:
        print(f"[Phase 1] Error during GPU processing: {e}")
        print("[Phase 1] Automatically switching to CPU fallback...")
        try:
            converter = _create_converter(AcceleratorDevice.CPU)
            return converter.convert(pdf_path)
        except Exception as cpu_err:
            print(f"[Phase 1 Error] CPU fallback also failed: {cpu_err}")
            raise cpu_err

def extract_pdf_structure(pdf_path: str, output_dir: str):
    """Reads PDF, extracts text/tables in order, saves images, and writes draft markdown."""
    try:
        result = convert_pdf_with_fallback(pdf_path)
        doc = result.document
    except Exception as e:
        print(f"[Phase 1 Error] Could not convert PDF document '{pdf_path}': {e}")
        raise e

    markdown_content = []
    images_metadata = []
    image_counter = 1

    output_path = Path(output_dir)
    images_dir = output_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Extract doc prefix for image naming (e.g. 'doc' from 'doc_001' or stem of pdf_path)
    folder_name = output_path.name
    doc_prefix = folder_name.split('_')[0] if '_' in folder_name else Path(pdf_path).stem

    current_page = None
    for item, level in doc.iterate_items():
        page_no = item.prov[0].page_no if (hasattr(item, "prov") and item.prov and len(item.prov) > 0) else None
        if page_no is not None and page_no != current_page:
            current_page = page_no
            markdown_content.append(f"<!-- page: {current_page} -->")

        if item.label in [
            DocItemLabel.TEXT, DocItemLabel.TITLE, DocItemLabel.PARAGRAPH,
            DocItemLabel.SECTION_HEADER, DocItemLabel.PAGE_HEADER, DocItemLabel.LIST_ITEM
        ]:
            if hasattr(item, "text") and item.text:
                markdown_content.append(item.text)
            
        elif item.label == DocItemLabel.TABLE:
            if isinstance(item, TableItem):
                markdown_content.append("\n" + item.export_to_markdown(doc=doc) + "\n")
            
        elif item.label in [DocItemLabel.PICTURE, DocItemLabel.CHART]:
            placeholder = f"<!-- IMAGE_PLACEHOLDER_{image_counter} -->"
            markdown_content.append(f"\n{placeholder}\n")
            
            image_rel_path = None
            if isinstance(item, PictureItem):
                try:
                    img = item.get_image(doc=doc)
                    if img:
                        img_filename = f"image_{image_counter}.png"
                        img_save_path = images_dir / img_filename
                        img.save(img_save_path)
                        image_rel_path = f"images/{img_filename}"
                except Exception as img_err:
                    print(f"[Phase 1] Failed to save image {image_counter}: {img_err}")

            if hasattr(item, "prov") and item.prov:
                prov = item.prov[0]
                images_metadata.append({
                    "image_id": placeholder,
                    "image_index": image_counter,
                    "doc_prefix": doc_prefix,
                    "image_path": str(output_path / image_rel_path) if image_rel_path else None,
                    "page_no": prov.page_no,
                    "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
                    "status": "pending"
                })
            image_counter += 1

    # Calculate total page count and page-level metadata list
    page_count = len(doc.pages) if (hasattr(doc, "pages") and doc.pages) else (current_page or 1)
    pages_meta = []
    for p in range(1, page_count + 1):
        pages_meta.append({
            "page": p,
            "ocr_used": True,
            "rotation_corrected_deg": 0,
            "warnings": []
        })

    final_markdown = "\n\n".join(markdown_content)

    try:
        with open(output_path / "document_draft.md", "w", encoding="utf-8") as f:
            f.write(final_markdown)

        # Determine document title from filename or doc items
        title_str = Path(pdf_path).stem.replace('_', ' ').title()
        if hasattr(doc, "iterate_items"):
            for item, _ in doc.iterate_items():
                if hasattr(item, "label") and item.label == DocItemLabel.TITLE and hasattr(item, "text") and item.text:
                    title_str = item.text.strip()
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
            "status": "in_progress",
            "pages": pages_meta,
            "images_to_process": images_metadata
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Phase 1 Error] Failed writing draft files to '{output_dir}': {e}")
        raise e

    print(f"[Phase 1] Completed! Saved draft and manifest to {output_dir}")


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
    
    model_name = os.getenv("MODEL_NAME", "gemini/gemini-3.6-flash")
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
        idx, img_meta = idx_and_meta
        img_id = img_meta["image_id"]
        img_path = img_meta.get("image_path")
        img_index = img_meta.get("image_index", idx)
        doc_prefix = img_meta.get("doc_prefix", default_doc_prefix)
        img_label = f"{doc_prefix} image {img_index}"
        page_n = img_meta.get("page_no", "?")
        
        # Check if already extracted in previous successful run
        if img_meta.get("status") == "success" and img_meta.get("extracted_text"):
            print(f"[Phase 2] Image {img_label} already extracted. Using cached result.", flush=True)
            llm_text = img_meta["extracted_text"]
            formatted_text = f"\n\n> [Diagram p.{page_n}]\n{llm_text}\n"
            return (img_id, formatted_text, img_meta, None)

        if img_path and os.path.exists(img_path):
            print(f"[Phase 2] Analyzing {img_path} ({img_label}) with LLM...", flush=True)
            try:
                base64_img = encode_image_to_base64(img_path)
                llm_text = extract_insights_with_llm(base64_img)
                
                formatted_text = f"\n\n> [Diagram p.{page_n}]\n{llm_text}\n"
                img_meta["extracted_text"] = llm_text
                img_meta["status"] = "success"
                img_meta.pop("error", None)
                print(f"[Phase 2] Completed {img_label}", flush=True)
                return (img_id, formatted_text, img_meta, None)
            except Exception as img_err:
                print(f"[Phase 2 Error] Failed processing {img_label}: {img_err}", flush=True)
                img_meta["status"] = "failed"
                img_meta["error"] = str(img_err)
                return (img_id, None, img_meta, img_label)
        else:
            print(f"[Phase 2 Warning] Image file not found for {img_id}", flush=True)
            img_meta["status"] = "missing"
            return (img_id, None, img_meta, img_label)

    items_to_process = list(enumerate(images, 1))
    
    with ThreadPoolExecutor(max_workers=min(max_workers, len(images) or 1)) as executor:
        futures = [executor.submit(process_single_image, item) for item in items_to_process]
        for future in as_completed(futures):
            img_id, formatted_text, updated_meta, failed_label = future.result()
            if formatted_text:
                extracted_data_map[img_id] = formatted_text
            if failed_label:
                failed_images.append(failed_label)

    # Save manifest with status and timestamp
    manifest_data["status"] = "completed" if not failed_images else "partial_failure"
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

def run_full_pipeline(pdf_file_path: str, output_directory: str, overwrite: bool = False):
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
    print("========================================\n")

    try:
        # Step 1: Extract structure and images
        extract_pdf_structure(pdf_file_path, output_directory)
        print("-" * 40)
        
        # Step 2: Run LLM Vision on extracted images
        llm_extractions = process_images_from_manifest(output_directory)
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
    args = parser.parse_args()

    try:
        run_full_pipeline(args.pdf, args.output, args.overwrite)
    except Exception as err:
        print(f"\n[Fatal Error] Pipeline execution halted: {err}")
        sys.exit(1)