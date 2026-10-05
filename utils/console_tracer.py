from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

LOG_FILE = Path("logs/trace.log")
WIDTH = 72


def _get(obj: Any, *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = obj.get(key) if isinstance(obj, Mapping) else getattr(obj, key, None)
        if value not in (None, ""):
            return value
    return default


def _clip(text: Any, limit: int = 160) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def build_trace(incident, chunks, response, confidence=None) -> str:
    out = []
    bar = "=" * WIDTH

    out += [bar, "==== INCIDENT DETAILS ====", bar]
    out.append(f"number      : {_get(incident, 'original_number', 'number')}")
    out.append(f"sys_id      : {_get(incident, 'sys_id')}")
    out.append(f"query       : {_get(incident, 'sanitized_query', 'short_description')}")
    out.append(f"description : {_clip(_get(incident, 'truncated_description', 'description'))}")
    out.append(f"is_safe     : {_get(incident, 'is_safe', default='n/a')}")

    out += ["", bar, "==== RETRIEVED CHUNKS & SCORES ====", bar]
    chunk_list = list(chunks or [])
    if not chunk_list:
        out.append("(no chunks above the similarity threshold)")
    for i, c in enumerate(chunk_list, start=1):
        score = c.get("score")
        score_txt = f"{score:.4f}" if isinstance(score, (int, float)) else "n/a"
        out.append(f"[{i}] {c.get('article_id')} - \"{c.get('title')}\"  score: {score_txt}")
        out.append(f"    {_clip(_get(c, 'content', 'chunk_text', 'text'))}")
    if confidence is not None:
        out.append(f"confidence  : {confidence}")

    out += ["", bar, "==== FINAL STRUCTURED ANSWER ====", bar]
    out.append(response.render())
    rejected = getattr(response, "rejected_steps", [])
    if rejected:
        out += ["", "Rejected steps (not grounded):"]
        out += [f"- [{r['reason']}] {_clip(r['text'])}" for r in rejected]
    out.append(bar)
    return "\n".join(out)


def print_execution_trace(incident, chunks, response, confidence=None, log_file=LOG_FILE):
    trace = build_trace(incident, chunks, response, confidence)
    print(trace)
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n##### RUN {datetime.now().isoformat(timespec='seconds')} #####\n")
        f.write(trace + "\n")
    return trace


def print_cache_store_trace(number, sys_id, cache_key, close_code, close_notes, log_file=LOG_FILE):
    bar = "=" * WIDTH
    out = [
        bar,
        "==== RESOLVED INCIDENT CACHED IN REDIS ====",
        bar,
        f"number      : {number or 'n/a'}",
        f"sys_id      : {sys_id}",
        f"cache_key   : {cache_key}",
        f"close_code  : {close_code}",
        f"close_notes : {_clip(close_notes, 200)}",
        f"status      : STORED_IN_REDIS (exact match ready)",
        bar,
    ]
    trace = "\n".join(out)
    print(trace)
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n##### RUN {datetime.now().isoformat(timespec='seconds')} #####\n")
        f.write(trace + "\n")
    return trace


def print_cache_hit_trace(incident, cached_data, log_file=LOG_FILE):
    bar = "=" * WIDTH
    number = _get(incident, "original_number", "number")
    sys_id = _get(incident, "sys_id")
    query = _get(incident, "short_description", "sanitized_query")
    close_notes = cached_data.get("close_notes", "")
    cached_num = cached_data.get("number", "n/a")
    cached_sys_id = cached_data.get("sys_id", "n/a")

    out = [
        bar,
        "==== EXACT-MATCH REDIS CACHE HIT ====",
        bar,
        f"number               : {number}",
        f"sys_id               : {sys_id}",
        f"short_description    : {query}",
        f"cached_from_incident : {cached_num} (sys_id: {cached_sys_id})",
        f"source               : previously_resolved_incident (human-verified)",
        f"verified             : True",
        "",
        bar,
        "==== VERIFIED RESOLUTION (PREVIOUSLY RESOLVED IN SERVICENOW) ====",
        bar,
        close_notes,
        bar,
    ]
    trace = "\n".join(out)
    print(trace)
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n##### RUN {datetime.now().isoformat(timespec='seconds')} #####\n")
        f.write(trace + "\n")
    return trace