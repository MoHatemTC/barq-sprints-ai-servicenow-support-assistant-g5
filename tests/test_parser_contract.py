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
    
    # Verify presence of page markers
    assert "<!-- page: 1 -->" in content, "document.md must contain consecutive <!-- page: N --> markers"

def test_manifest_json_contract():
    assert MANIFEST_PATH.exists(), "manifest.json must exist in parsed output directory"
    
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "status" in data, "manifest.json must contain a status field"
    assert data["status"] in ["completed", "in_progress"], f"Unexpected status: {data['status']}"
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
