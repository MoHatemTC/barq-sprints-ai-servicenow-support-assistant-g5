"""Offline unit test suite for Sprint 3.3 Agent Tool Layer.

Tests all four tools (searchKB, addworknote, suggestAnswer, requestHR),
the ToolRegistry, RunContext, formatting, and terminal state semantics.

Runs 100% offline using in-memory Qdrant (QdrantClient(":memory:")),
a deterministic mock embedder, and FakeWriteBackPort.
"""

import sys
from pathlib import Path
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# Ensure workspace root is on sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


from agent.config import MAX_NOTE_LENGTH, MIN_REASON_LENGTH, SCORE_THRESHOLD
from agent.formatting import (
    calculate_ai_confidence,
    format_escalation_message,
    format_suggested_resolution,
    validate_numbered_procedure,
    validate_step_citations,
)
from agent.ports import FakeWriteBackPort
from agent.run_context import RunContext
from agent.tools import (
    AddWorkNoteTool,
    RequestHRTool,
    SearchKBTool,
    SuggestAnswerTool,
    ToolRegistry,
)


class DeterministicMockEmbedder:
    """Offline mock embedder producing predictable 768-dim normalized vectors."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        lower = text.lower()
        if "wifi" in lower or "network" in lower:
            vec[0] = 0.95
            vec[1] = 0.30
        elif "vpn" in lower or "cisco" in lower:
            vec[2] = 0.90
            vec[3] = 0.40
        elif "printer" in lower:
            vec[4] = 0.85
            vec[5] = 0.50
        elif "retired" in lower or "archived" in lower:
            vec[6] = 0.92
            vec[7] = 0.38
        else:
            # Low background similarity for unrelated queries
            vec[10] = 0.20
            vec[20] = 0.10

        # Simple Euclidean norm normalization
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


@pytest.fixture
def mock_embedder():
    return DeterministicMockEmbedder(dim=768)


@pytest.fixture
def in_memory_qdrant(mock_embedder):
    """Sets up an in-memory Qdrant client with test KB articles."""
    client = QdrantClient(":memory:")
    collection_name = "kb_test_collection"

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

    # Seed test points
    # 1. WiFi fix (published)
    wifi_vec = mock_embedder.embed_text("wifi network connection guide")
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=1,
                vector=wifi_vec,
                payload={
                    "article_id": "KB0010001",
                    "title": "Fix WiFi Disconnections",
                    "text": "Forget the network, reconnect, and update adapter drivers.",
                    "workflow_state": "published",
                    "status": "published",
                    "chunk_index": 0,
                },
            ),
        ],
    )

    # 2. VPN fix (published)
    vpn_vec = mock_embedder.embed_text("vpn cisco anyconnect setup")
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=2,
                vector=vpn_vec,
                payload={
                    "article_id": "KB0010002",
                    "title": "Cisco VPN Client Setup",
                    "text": "Restart the Cisco AnyConnect secure mobility service.",
                    "workflow_state": "published",
                    "status": "published",
                    "chunk_index": 0,
                },
            ),
        ],
    )

    # 3. Retired article (should never be returned)
    retired_vec = mock_embedder.embed_text("retired legacy network docs")
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=3,
                vector=retired_vec,
                payload={
                    "article_id": "KB0099999",
                    "title": "Old Archived Network Guide",
                    "text": "Legacy Windows XP network instructions.",
                    "workflow_state": "retired",
                    "status": "retired",
                    "chunk_index": 0,
                },
            ),
        ],
    )

    class QdrantWrapper:
        def __init__(self, c, name):
            self.client = c
            self.collection_name = name

    return QdrantWrapper(client, collection_name)


@pytest.fixture
def run_context():
    return RunContext(sys_id="a" * 32, number="INC0010001")


@pytest.fixture
def write_back_port():
    return FakeWriteBackPort()


# ============================================================================ #
# 1. Tool Registry & Zero-Privilege Security Tests
# ============================================================================ #

def test_registry_exposes_strictly_four_tools(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    registry = ToolRegistry(
        run_context=run_context,
        write_back_port=write_back_port,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
    )
    assert len(registry.tools) == 4
    assert set(registry.tools.keys()) == {"searchKB", "addworknote", "suggestAnswer", "requestHR"}


def test_registry_security_rejects_forbidden_capabilities(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    registry = ToolRegistry(
        run_context=run_context,
        write_back_port=write_back_port,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
    )
    # Injecting forbidden actions must raise an error
    registry.tools["resolveIncident"] = lambda: "forbidden"
    with pytest.raises((ValueError, RuntimeError)):
        registry.assert_strictly_four_tools()


def test_langchain_tools_conversion(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    registry = ToolRegistry(
        run_context=run_context,
        write_back_port=write_back_port,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
    )
    lc_tools = registry.get_langchain_tools()
    assert len(lc_tools) == 4
    tool_names = [t.name for t in lc_tools]
    assert tool_names == ["searchKB", "addworknote", "suggestAnswer", "requestHR"]


# ============================================================================ #
# 2. searchKB Tool Tests (Non-Terminal)
# ============================================================================ #

def test_search_kb_happy_path(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    search_tool = SearchKBTool(
        run_context=run_context,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
        score_threshold=0.50,
    )
    res = search_tool.run("laptop wifi keeps dropping")

    assert res["status"] == "success"
    assert res["count"] >= 1
    assert res["chunks"][0]["article_id"] == "KB0010001"
    assert res["best_score"] >= 0.50
    assert not run_context.is_finished  # Must remain non-terminal

    # Check RunContext updated
    assert len(run_context.retrieved_chunks) >= 1
    assert "KB0010001" in run_context.get_known_article_ids()
    assert run_context.best_score == res["best_score"]


def test_search_kb_filters_out_retired_articles(run_context, in_memory_qdrant, mock_embedder):
    search_tool = SearchKBTool(
        run_context=run_context,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
        score_threshold=0.10,
    )
    res = search_tool.run("retired legacy network docs")
    # Retired article must not be in returned chunks
    returned_ids = [c["article_id"] for c in res.get("chunks", [])]
    assert "KB0099999" not in returned_ids


def test_search_kb_threshold_pruning(run_context, in_memory_qdrant, mock_embedder):
    search_tool = SearchKBTool(
        run_context=run_context,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
        score_threshold=0.70,
    )
    # Unrelated query yields low similarity score (below 0.70 threshold)
    res = search_tool.run("how to bake sourdough bread in kitchen")
    assert res["status"] == "no_results"
    assert res["count"] == 0
    assert res["chunks"] == []
    assert res["best_score"] < 0.70



def test_search_kb_empty_query(run_context, in_memory_qdrant, mock_embedder):
    search_tool = SearchKBTool(
        run_context=run_context,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
    )
    res = search_tool.run("   ")
    assert res["status"] == "error"
    assert "empty" in res["error"].lower()


def test_search_kb_handles_exception_cleanly(run_context, mock_embedder):
    class BrokenQdrant:
        client = None

    search_tool = SearchKBTool(
        run_context=run_context,
        qdrant_service=BrokenQdrant(),
        embedder=mock_embedder,
    )
    res = search_tool.run("wifi issue")
    assert res["status"] == "error"
    assert "Search failed" in res["error"]


# ============================================================================ #
# 3. addworknote Tool Tests (Non-Terminal)
# ============================================================================ #

def test_add_worknote_happy_path(run_context, write_back_port):
    tool = AddWorkNoteTool(run_context=run_context, write_back_port=write_back_port)
    res = tool.run("Checking knowledge base for WiFi resolution...")

    assert res["status"] == "success"
    assert "Work note added" in res["message"]
    assert not run_context.is_finished
    assert len(run_context.work_notes) == 1
    assert len(write_back_port.work_notes) == 1
    assert write_back_port.work_notes[0]["note"] == "Checking knowledge base for WiFi resolution..."


def test_add_worknote_empty_note_rejected(run_context, write_back_port):
    tool = AddWorkNoteTool(run_context=run_context, write_back_port=write_back_port)
    res = tool.run("  ")
    assert res["status"] == "error"
    assert "cannot be empty" in res["error"]
    assert len(write_back_port.work_notes) == 0


def test_add_worknote_exceeds_max_length(run_context, write_back_port):
    tool = AddWorkNoteTool(
        run_context=run_context,
        write_back_port=write_back_port,
        max_note_length=50,
    )
    long_note = "A" * 51
    res = tool.run(long_note)
    assert res["status"] == "error"
    assert "exceeds maximum allowed limit" in res["error"]
    assert len(write_back_port.work_notes) == 0


def test_add_worknote_port_failure_leaves_run_open(run_context):
    failing_port = FakeWriteBackPort(should_fail=True, fail_error="Network 503")
    tool = AddWorkNoteTool(run_context=run_context, write_back_port=failing_port)
    res = tool.run("Valid note")

    assert res["status"] == "error"
    assert "Network 503" in res["error"]
    assert not run_context.is_finished  # Run remains open for retry


# ============================================================================ #
# 4. suggestAnswer Tool Tests (Terminal)
# ============================================================================ #

def test_suggest_answer_happy_path(run_context, write_back_port):
    # Seed RunContext with a retrieved article
    run_context.retrieved_chunks.append({
        "article_id": "KB0010001",
        "title": "Fix WiFi Disconnections",
        "score": 0.8521,
    })
    run_context.best_score = 0.8521

    tool = SuggestAnswerTool(run_context=run_context, write_back_port=write_back_port)
    procedure = (
        "1. Forget the existing network profile. [Article: KB0010001]\n"
        "2. Reconnect and authenticate. [Article: KB0010001]"
    )
    res = tool.run(procedure=procedure)

    assert res["status"] == "success"
    assert res["ai_confidence"] == 0.8521
    assert res["citations"] == ["KB0010001"]
    assert run_context.is_finished is True  # Terminal state transition
    assert run_context.terminal_tool == "suggestAnswer"

    # Verify write-back port received payload
    assert len(write_back_port.suggestions) == 1
    assert write_back_port.suggestions[0]["payload"]["human_review_required"] is True
    assert write_back_port.suggestions[0]["payload"]["escalated"] is False


def test_suggest_answer_blocks_subsequent_calls(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    run_context.retrieved_chunks.append({"article_id": "KB0010001", "score": 0.80})
    tool = SuggestAnswerTool(run_context=run_context, write_back_port=write_back_port)
    res = tool.run("1. Step one. [Article: KB0010001]")
    assert res["status"] == "success"
    assert run_context.is_finished is True

    # Attempt second call to suggestAnswer
    second_res = tool.run("1. Another step. [Article: KB0010001]")
    assert second_res["status"] == "error"
    assert second_res["code"] == "RUN_ALREADY_FINISHED"

    # Attempt calling addworknote
    note_tool = AddWorkNoteTool(run_context=run_context, write_back_port=write_back_port)
    note_res = note_tool.run("Test note")
    assert note_res["status"] == "error"
    assert note_res["code"] == "RUN_ALREADY_FINISHED"

    # Attempt calling searchKB
    search_tool = SearchKBTool(run_context=run_context, qdrant_service=in_memory_qdrant, embedder=mock_embedder)
    search_res = search_tool.run("query")
    assert search_res["status"] == "error"
    assert search_res["code"] == "RUN_ALREADY_FINISHED"


def test_suggest_answer_rejects_non_numbered_procedure(run_context, write_back_port):
    run_context.retrieved_chunks.append({"article_id": "KB0010001", "score": 0.80})
    tool = SuggestAnswerTool(run_context=run_context, write_back_port=write_back_port)

    # Paragraph text instead of numbered list
    res = tool.run("Just reboot your laptop and it should work. [Article: KB0010001]")
    assert res["status"] == "error"
    assert "numbered" in res["error"].lower()
    assert run_context.is_finished is False  # Must not lock run on validation error


def test_suggest_answer_rejects_uncited_step(run_context, write_back_port):
    run_context.retrieved_chunks.append({"article_id": "KB0010001", "score": 0.80})
    tool = SuggestAnswerTool(run_context=run_context, write_back_port=write_back_port)

    procedure = "1. Step one has citation. [Article: KB0010001]\n2. Step two lacks citation."
    res = tool.run(procedure)
    assert res["status"] == "error"
    assert "citation" in res["error"].lower()
    assert run_context.is_finished is False


def test_suggest_answer_rejects_hallucinated_source(run_context, write_back_port):
    run_context.retrieved_chunks.append({"article_id": "KB0010001", "score": 0.80})
    tool = SuggestAnswerTool(run_context=run_context, write_back_port=write_back_port)

    # KB0099999 was never retrieved!
    procedure = "1. Perform reset. [Article: KB0099999]"
    res = tool.run(procedure)
    assert res["status"] == "error"
    assert "unretrieved" in res["error"].lower() or "unknown" in res["error"].lower()
    assert run_context.is_finished is False


def test_suggest_answer_port_failure_leaves_run_open(run_context):
    run_context.retrieved_chunks.append({"article_id": "KB0010001", "score": 0.80})
    failing_port = FakeWriteBackPort(should_fail=True, fail_error="ServiceNow Timeout")
    tool = SuggestAnswerTool(run_context=run_context, write_back_port=failing_port)

    res = tool.run("1. Step one. [Article: KB0010001]")
    assert res["status"] == "error"
    assert "ServiceNow Timeout" in res["error"]
    assert run_context.is_finished is False  # Open for retry!


# ============================================================================ #
# 5. requestHR Tool Tests (Terminal)
# ============================================================================ #

def test_request_hr_happy_path(run_context, write_back_port):
    run_context.best_score = 0.42  # Below-threshold score from earlier search

    tool = RequestHRTool(run_context=run_context, write_back_port=write_back_port)
    reason = "No knowledge base article matched with sufficient confidence for hardware issue."
    res = tool.run(reason=reason)

    assert res["status"] == "success"
    assert res["ai_confidence"] == 0.42
    assert run_context.is_finished is True
    assert run_context.terminal_tool == "requestHR"

    assert len(write_back_port.escalations) == 1
    escalation = write_back_port.escalations[0]
    assert escalation["payload"]["escalated"] is True
    assert escalation["payload"]["human_review_required"] is True
    assert escalation["reason"] == reason


def test_request_hr_blocks_subsequent_calls(run_context, write_back_port):
    tool = RequestHRTool(run_context=run_context, write_back_port=write_back_port)
    res = tool.run("Escalating due to policy.")
    assert res["status"] == "success"
    assert run_context.is_finished is True

    # Subsequent call blocked
    second = tool.run("Another escalation.")
    assert second["status"] == "error"
    assert second["code"] == "RUN_ALREADY_FINISHED"


def test_request_hr_validation_empty_reason(run_context, write_back_port):
    tool = RequestHRTool(run_context=run_context, write_back_port=write_back_port)
    res = tool.run("   ")
    assert res["status"] == "error"
    assert "empty" in res["error"].lower()
    assert run_context.is_finished is False


def test_request_hr_port_failure_leaves_run_open(run_context):
    failing_port = FakeWriteBackPort(should_fail=True, fail_error="Connection Reset")
    tool = RequestHRTool(run_context=run_context, write_back_port=failing_port)
    res = tool.run("Valid reason for escalation.")

    assert res["status"] == "error"
    assert "Connection Reset" in res["error"]
    assert run_context.is_finished is False  # Stays open for retry


# ============================================================================ #
# 6. Formatting & Confidence Formula Unit Tests
# ============================================================================ #

def test_ai_confidence_formula():
    # Empty
    assert calculate_ai_confidence([]) == 0.0
    # Single score
    assert calculate_ai_confidence([0.7258]) == 0.7258
    # Multiple scores: selects maximum
    assert calculate_ai_confidence([0.6512, 0.8149, 0.7301]) == 0.8149
    # Clamping test (> 1.0)
    assert calculate_ai_confidence([1.05]) == 1.0
    # Clamping test (< 0.0)
    assert calculate_ai_confidence([-0.2]) == 0.0


def test_validate_numbered_procedure_variations():
    valid, steps, err = validate_numbered_procedure("1. First step\n2. Second step")
    assert valid and len(steps) == 2

    valid, steps, err = validate_numbered_procedure("1) First step\n2) Second step")
    assert valid and len(steps) == 2

    invalid, steps, err = validate_numbered_procedure("First step\nSecond step")
    assert not invalid and "not numbered" in err


# ============================================================================ #
# 7. End-to-End Multi-Tool Workflow Test
# ============================================================================ #

def test_full_agent_workflow(run_context, write_back_port, in_memory_qdrant, mock_embedder):
    registry = ToolRegistry(
        run_context=run_context,
        write_back_port=write_back_port,
        qdrant_service=in_memory_qdrant,
        embedder=mock_embedder,
        score_threshold=0.50,
    )
    tools = registry.tools

    # Step 1: Search KB (Non-terminal)
    search_res = tools["searchKB"]("wifi disconnection")
    assert search_res["status"] == "success"
    assert not run_context.is_finished

    # Step 2: Add Work Note (Non-terminal)
    note_res = tools["addworknote"]("Retrieved KB0010001 for WiFi resolution.")
    assert note_res["status"] == "success"
    assert not run_context.is_finished

    # Step 3: Suggest Answer (Terminal)
    suggest_res = tools["suggestAnswer"](
        "1. Forget network profile. [Article: KB0010001]\n"
        "2. Reconnect to office SSID. [Article: KB0010001]"
    )
    assert suggest_res["status"] == "success"
    assert run_context.is_finished is True

    # Step 4: Verify post-terminal lock across all tools
    for tool_name in ["searchKB", "addworknote", "suggestAnswer", "requestHR"]:
        call_res = tools[tool_name]("any arg")
        assert call_res["status"] == "error"
        assert call_res["code"] == "RUN_ALREADY_FINISHED"


def test_src_agent_package_contract():
    """Verify that importing through src.agent exposes all required contract modules."""
    import src.agent as sa
    import src.agent.run_context as src_rc
    import src.agent.formatting as src_fmt
    import src.agent.tools as src_tools

    assert hasattr(src_rc, "RunContext")
    assert hasattr(src_fmt, "calculate_ai_confidence")
    assert hasattr(src_tools, "ToolRegistry")
    assert hasattr(src_tools, "SearchKBTool")
    assert hasattr(src_tools, "AddWorkNoteTool")
    assert hasattr(src_tools, "SuggestAnswerTool")
    assert hasattr(src_tools, "RequestHRTool")

