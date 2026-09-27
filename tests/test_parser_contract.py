import os
import sys
import json
import pytest
import fitz
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARSED_DIR = Path("data/parsed/doc_001")
DOCUMENT_PATH = PARSED_DIR / "document.md"
MANIFEST_PATH = PARSED_DIR / "manifest.json"

def test_parsed_directory_exists():
    assert PARSED_DIR.exists() and PARSED_DIR.is_dir(), "Parsed output directory must exist"

def test_document_md_contract():
    assert DOCUMENT_PATH.exists(), "document.md must exist in parsed output directory"
    assert DOCUMENT_PATH.stat().st_size > 0, "document.md must not be empty"
    
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    page_count = manifest.get("page_count", 1)
    
    # Verify presence of consecutive page markers and diagram blockquotes
    for p in range(1, page_count + 1):
        assert f"<!-- page: {p} -->" in content, f"document.md missing consecutive marker for page {p}"
    assert "> [Diagram p." in content, "document.md must contain > [Diagram p.N] blockquotes"

def test_manifest_json_contract():
    assert MANIFEST_PATH.exists(), "manifest.json must exist in parsed output directory"
    
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handoff contract top-level schema assertions
    required_top_level = ["doc_id", "title", "source_file", "source_type", "page_count", "parsed_at", "parser"]
    for field in required_top_level:
        assert field in data, f"manifest.json must contain top-level field '{field}'"
    
    assert isinstance(data["page_count"], int), "manifest.json must contain integer page_count"
    assert "status" in data, "manifest.json must contain status field"
    assert data["status"] in ["completed", "in_progress", "partial_failure", "failed"], f"Unexpected status: {data['status']}"
    
    # Page-level metadata array contract assertions
    assert "pages" in data and isinstance(data["pages"], list), "manifest.json must contain pages list"
    assert len(data["pages"]) == data["page_count"], "pages array length must match page_count"
    page_obj = data["pages"][0]
    assert "page" in page_obj or "page_no" in page_obj
    assert "ocr_used" in page_obj and isinstance(page_obj["ocr_used"], bool)
    if "ocr_engine" in page_obj:
        assert isinstance(page_obj["ocr_engine"], str)
        assert "ocr_languages" in page_obj and isinstance(page_obj["ocr_languages"], list)
        assert "rotation_detected_deg" in page_obj and isinstance(page_obj["rotation_detected_deg"], int)
    assert "rotation_corrected_deg" in page_obj and isinstance(page_obj["rotation_corrected_deg"], int)
    assert "warnings" in page_obj and isinstance(page_obj["warnings"], list)

    assert "images_to_process" in data, "manifest.json must contain images_to_process list"
    images = data["images_to_process"]
    assert isinstance(images, list)
    
    required_keys = {"image_id", "image_index", "page_no", "status"}
    for img_meta in images:
        assert required_keys.issubset(img_meta.keys()), f"Missing required keys in image metadata: {img_meta}"

def test_extracted_images_exist():
    images_dir = PARSED_DIR / "images"
    if images_dir.exists():
        images = list(images_dir.glob("*.png"))
        assert len(images) > 0, "Extracted images directory should contain PNG files"

def test_parser_cli_invalid_pdf():
    from scripts.parse_pdf import run_full_pipeline
    with pytest.raises(FileNotFoundError):
        run_full_pipeline("non_existent_file.pdf", "data/parsed/test_invalid")


def test_image_failure_is_recorded_without_raising(tmp_path):
    from scripts.parse_pdf import process_images_from_manifest

    output_dir = tmp_path / "parsed"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({
            "status": "in_progress",
            "pages": [{"page": 1, "error": "synthetic page failure"}],
            "images_to_process": [{
                "image_id": "<!-- IMAGE_PLACEHOLDER_1 -->",
                "image_index": 1,
                "page_no": 1,
                "status": "pending",
                "image_path": str(output_dir / "missing.png"),
                "is_diagram_candidate": True,
            }],
        }),
        encoding="utf-8",
    )

    extracted = process_images_from_manifest(str(output_dir))

    assert "<!-- IMAGE_PLACEHOLDER_1 -->" in extracted
    assert "Image file missing" in extracted["<!-- IMAGE_PLACEHOLDER_1 -->"]
    updated = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert updated["status"] == "partial_failure"
    assert updated["images_to_process"][0]["status"] == "missing"


def test_decorative_image_is_skipped(tmp_path):
    from scripts.parse_pdf import process_images_from_manifest

    output_dir = tmp_path / "parsed"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({
            "status": "in_progress",
            "pages": [],
            "images_to_process": [{
                "image_id": "<!-- IMAGE_PLACEHOLDER_1 -->",
                "image_index": 1,
                "page_no": 1,
                "status": "pending",
                "image_path": str(output_dir / "not-needed.png"),
                "is_diagram_candidate": False,
            }],
        }),
        encoding="utf-8",
    )

    extracted = process_images_from_manifest(str(output_dir))

    assert extracted["<!-- IMAGE_PLACEHOLDER_1 -->"] == ""
    updated = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert updated["images_to_process"][0]["status"] == "skipped_decorative"


def test_page_failure_isolated_in_manifest(tmp_path, monkeypatch):
    from scripts import parse_pdf

    pdf_path = tmp_path / "two-pages.pdf"
    pdf = fitz.open()
    pdf.new_page()
    rotated_page = pdf.new_page()
    rotated_page.set_rotation(90)
    pdf.save(pdf_path)
    pdf.close()

    class FakeDocument:
        pages = {1: object()}

        def iterate_items(self):
            return iter(())

    class FakeResult:
        document = FakeDocument()

    def fake_convert(_path, page_range=None):
        if page_range == (2, 2):
            raise RuntimeError("synthetic page failure")
        return FakeResult()

    monkeypatch.setattr(parse_pdf, "convert_pdf_with_fallback", fake_convert)
    output_dir = tmp_path / "parsed"
    parse_pdf.extract_pdf_structure(str(pdf_path), str(output_dir))

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    draft = (output_dir / "document_draft.md").read_text(encoding="utf-8")
    assert manifest["status"] == "partial_failure"
    assert manifest["pages"][1]["error"] == "synthetic page failure"
    assert manifest["pages"][1]["rotation_detected_deg"] == 90
    assert manifest["pages"][1]["rotation_corrected_deg"] == 90
    assert "<!-- page: 1 -->" in draft
    assert "<!-- page: 2 -->" in draft
