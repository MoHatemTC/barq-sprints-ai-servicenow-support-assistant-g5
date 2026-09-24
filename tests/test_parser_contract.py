import os
import sys
import json
import pytest
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
    assert data["status"] in ["completed", "in_progress"], f"Unexpected status: {data['status']}"
    
    # Page-level metadata array contract assertions
    assert "pages" in data and isinstance(data["pages"], list), "manifest.json must contain pages list"
    assert len(data["pages"]) == data["page_count"], "pages array length must match page_count"
    page_obj = data["pages"][0]
    assert "page" in page_obj or "page_no" in page_obj
    assert "ocr_used" in page_obj and isinstance(page_obj["ocr_used"], bool)
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
