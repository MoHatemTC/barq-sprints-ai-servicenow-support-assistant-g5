"""Rebuild the Qdrant collection from published ServiceNow KB articles.

Run after changing the chunker or CHUNK_SIZE / CHUNK_OVERLAP:
    python reindex.py
"""

import asyncio
import logging

from Services.KB_ingestion_service import reindex_all

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(reindex_all()))
