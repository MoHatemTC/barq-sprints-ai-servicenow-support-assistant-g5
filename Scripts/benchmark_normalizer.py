"""scripts/benchmark_normalization.py
Compares Qdrant retrieval score: Raw Human Ticket vs. Normalized Query
"""
from Services.shared import get_embedder, get_qdrant
from Services.query_normalizer import normalize_incident

TEST_CASES = [
    (
        "VPN Problem",
        "This stupid network thingy keeps kicking me out from home, fix this ASAP I have work!!"
    ),
    (
        "Wi-Fi Problem",
        "My internet is acting crazy and disconnecting every 2 minutes on my laptop!!"
    ),
]

def run_benchmark():
    embedder = get_embedder()
    qdrant = get_qdrant()
    
    print(f"{'TEST CASE':<15} | {'RAW SCORE':<10} | {'NORMALIZED SCORE':<16} | {'IMPROVEMENT':<12}")
    print("-" * 65)

    for name, raw_text in TEST_CASES:
        # 1. Search with Raw Text
        raw_vec = embedder.embed_text(raw_text[:100])
        raw_hits = qdrant.client.query_points(
            collection_name=qdrant.collection_name,
            query=raw_vec,
            limit=1
        ).points
        raw_score = round(raw_hits[0].score, 4) if raw_hits else 0.0

        # 2. Search with Normalized Query
        normalized = normalize_incident(raw_text)
        norm_vec = embedder.embed_text(normalized.optimized_search_query)
        norm_hits = qdrant.client.query_points(
            collection_name=qdrant.collection_name,
            query=norm_vec,
            limit=1
        ).points
        norm_score = round(norm_hits[0].score, 4) if norm_hits else 0.0

        diff = round(norm_score - raw_score, 4)
        print(f"{name:<15} | {raw_score:<10} | {norm_score:<16} | +{diff:<10}")

if __name__ == "__main__":
    run_benchmark()