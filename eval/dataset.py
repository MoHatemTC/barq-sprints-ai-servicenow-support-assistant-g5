"""Golden dataset loading helpers (no heavy imports, safe to use offline)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_DATASET = Path("eval/datasets/rag_golden.json")


def make_query(short_description: str, description: str = "") -> str:
    """The text sent to retrieval AND the lookup key for snapshots.

    One shared function so live mode and snapshot mode can never disagree.
    """
    return f"{short_description.strip()}\n{description.strip()}".strip()


def case_query(case: dict) -> str:
    return make_query(case["short_description"], case.get("description", ""))


def load_dataset(path: str | Path = DEFAULT_DATASET) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dataset_sha256(path: str | Path = DEFAULT_DATASET) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()