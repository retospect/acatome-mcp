"""Tests for MCP tools (mock store)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import acatome_mcp.tools as tools_mod
from acatome_mcp.tools import note, paper, search


def _make_mock_store():
    """Create a mock store with common return values."""
    mock = MagicMock()
    mock.get.return_value = {
        "ref_id": 1,
        "id": 1,
        "title": "Quantum Error Correction",
        "slug": "smith2024quantum",
        "doi": "10.1038/s41567-024-1234-5",
        "year": 2024,
    }
    mock.get_blocks.return_value = [
        {
            "node_id": "smith2024-p01-001",
            "block_type": "text",
            "block_index": 0,
            "page": 1,
            "text": "First block of text about qubits.",
            "summary": None,
            "section_path": '["Introduction"]',
        },
        {
            "node_id": "ref:1:abstract",
            "block_type": "abstract",
            "block_index": None,
            "page": None,
            "text": "We present a new approach...",
            "summary": None,
            "section_path": None,
        },
    ]
    mock.get_toc.return_value = [
        {
            "node_id": "ref:1:abstract",
            "page": None,
            "block_type": "abstract",
            "section_path": None,
            "preview": "We present a new approach...",
        },
        {
            "node_id": "smith2024-p01-001",
            "page": 1,
            "block_type": "text",
            "section_path": '["Introduction"]',
            "preview": "First block of text about qubits.",
        },
    ]
    mock.get_notes.return_value = []
    mock.add_note.return_value = 1
    mock.delete_note.return_value = True
    mock.update_note.return_value = True
    mock.search_text.return_value = []
    return mock


class _MockStoreFixture:
    """Context manager that patches the store singleton."""

    def __init__(self):
        self.mock = _make_mock_store()

    def __enter__(self):
        tools_mod._store = self.mock
        return self.mock

    def __exit__(self, *args):
        tools_mod._store = None


class TestPaperDefault:
    def test_default_view(self):
        with _MockStoreFixture() as mock:
            result = paper(id="slug:smith2024quantum")
            assert "meta" in result
            assert result["meta"]["title"] == "Quantum Error Correction"
            assert "hints" in result
            assert "abstract" in result

    def test_not_found(self):
        with _MockStoreFixture() as mock:
            mock.get.return_value = None
            result = paper(id="slug:nonexistent")
            assert "error" in result


class TestPaperViews:
    def test_meta(self):
        with _MockStoreFixture() as mock:
            result = paper(id="slug:smith2024quantum/meta")
            assert "meta" in result
            assert result["meta"]["slug"] == "smith2024quantum"
            assert "hints" in result

    def test_abstract(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"text": "We present a new approach...", "block_type": "abstract"}
            ]
            result = paper(id="slug:smith2024quantum/abstract")
            assert result["abstract"] == "We present a new approach..."

    def test_toc(self):
        with _MockStoreFixture() as mock:
            result = paper(id="slug:smith2024quantum/toc")
            assert "items" in result
            assert result["total"] == 2

    def test_chunk_all(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "n1",
                    "block_type": "text",
                    "block_index": 0,
                    "text": "chunk 0",
                },
            ]
            result = paper(id="slug:smith2024quantum/chunk")
            assert "items" in result
            assert result["total"] == 1

    def test_chunk_single(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "n0",
                    "block_type": "text",
                    "block_index": 0,
                    "text": "zero",
                },
                {
                    "node_id": "n4",
                    "block_type": "text",
                    "block_index": 4,
                    "text": "four",
                },
            ]
            result = paper(id="slug:smith2024quantum/chunk/4")
            assert len(result["items"]) == 1
            assert result["items"][0]["text"] == "four"

    def test_chunk_open_range(self):
        with _MockStoreFixture() as mock:
            blocks = [
                {
                    "node_id": f"n{i}",
                    "block_type": "text",
                    "block_index": i,
                    "text": f"block {i}",
                }
                for i in range(20)
            ]
            mock.get_blocks.return_value = blocks
            result = paper(id="slug:smith2024quantum/chunk/11-")
            assert len(result["items"]) == 9  # blocks 11-19
            assert result["items"][0]["block_index"] == 11


class TestPaperFilter:
    def test_chunk_filter(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "n0",
                    "block_type": "text",
                    "block_index": 0,
                    "text": "about qubits",
                },
                {
                    "node_id": "n1",
                    "block_type": "text",
                    "block_index": 1,
                    "text": "about cats",
                },
            ]
            result = paper(id="slug:smith2024quantum/chunk", filter="qubit")
            assert result["total"] == 1
            assert result["items"][0]["text"] == "about qubits"


class TestPaperHints:
    def test_default_has_hints(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum")
            assert len(result["hints"]) > 0
            assert any("toc" in h for h in result["hints"])

    def test_toc_has_chunk_hint(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum/toc")
            assert any("chunk" in h for h in result["hints"])


class TestSearch:
    def test_search_basic(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "qubit fidelity result",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "smith2024quantum"},
                }
            ]
            result = search(query="qubit fidelity")
            assert len(result["items"]) == 1
            assert result["items"][0]["provenance"] == "original"
            assert "hints" in result

    def test_search_generated_provenance(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {"text": "summary text", "metadata": {"block_type": "paper_summary"}}
            ]
            result = search(query="summary")
            assert result["items"][0]["provenance"] == "generated"


class TestSearchScope:
    def test_scope_single_slug(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "LOV2 result",
                    "metadata": {"block_type": "text", "paper_id": "1"},
                    "paper": {"slug": "zimmerman2016engineering"},
                }
            ]
            result = search(query="LOV2", scope="zimmerman2016engineering")
            assert len(result["items"]) == 1
            # Verify where filter includes paper_id
            call_args = mock.search_text.call_args
            where = call_args.kwargs.get("where") or call_args[1].get("where")
            assert where is not None
            assert "paper_id" in where
            assert where["paper_id"] == "1"

    def test_scope_multi_slug(self):
        with _MockStoreFixture() as mock:
            # Mock get() to return different ref_ids for different slugs
            def side_get(ident):
                if ident == "smith2024quantum":
                    return {"ref_id": 1, "slug": "smith2024quantum"}
                if ident == "jones2023photon":
                    return {"ref_id": 2, "slug": "jones2023photon"}
                return None

            mock.get.side_effect = side_get
            mock.search_text.return_value = []
            result = search(query="photon", scope="smith2024quantum,jones2023photon")
            call_args = mock.search_text.call_args
            where = call_args.kwargs.get("where") or call_args[1].get("where")
            assert where["paper_id"] == {"$in": ["1", "2"]}

    def test_scope_nonexistent(self):
        with _MockStoreFixture() as mock:
            mock.get.return_value = None
            result = search(query="anything", scope="nonexistent")
            assert result["items"] == []
            assert "No papers matched" in result["hints"][0]
            mock.search_text.assert_not_called()

    def test_scope_with_kinds(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = []
            result = search(
                query="imaging", kinds=["text"], scope="zimmerman2016engineering"
            )
            call_args = mock.search_text.call_args
            where = call_args.kwargs.get("where") or call_args[1].get("where")
            assert where["paper_id"] == "1"
            assert where["block_type"] == "text"

    def test_scope_empty_string_ignored(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = []
            result = search(query="test", scope="")
            call_args = mock.search_text.call_args
            where = call_args.kwargs.get("where") or call_args[1].get("where")
            assert where is None  # No scope → no where filter


class TestPaperNotes:
    def test_paper_notes_modifier(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [{"id": 1, "content": "Great paper"}]
            result = paper(id="slug:smith2024quantum/notes")
            assert "notes" in result
            assert len(result["notes"]) == 1

    def test_chunk_notes_modifier(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"node_id": "n9", "block_type": "text", "block_index": 9},
            ]
            mock.get_notes.return_value = [{"id": 2, "content": "Chunk note"}]
            result = paper(id="slug:smith2024quantum/chunk/9/notes")
            assert "notes" in result
            assert len(result["notes"]) == 1

    def test_default_view_note_count(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [
                {"id": 1, "content": "n1", "block_node_id": None},
                {"id": 2, "content": "n2", "block_node_id": None},
            ]
            result = paper(id="slug:smith2024quantum")
            assert result["note_count"] == 2
            assert any("notes" in h for h in result["hints"])

    def test_default_view_no_note_count_when_zero(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum")
            assert "note_count" not in result

    def test_chunk_note_count_annotated(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"node_id": "n0", "block_type": "text", "block_index": 0, "text": "hi"},
            ]
            mock.get_notes.return_value = [
                {"id": 1, "block_node_id": "n0", "content": "annotated"},
            ]
            result = paper(id="slug:smith2024quantum/chunk")
            assert result["items"][0]["note_count"] == 1
            assert any("notes" in h for h in result["hints"])


class TestNote:
    def test_read_notes(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [{"id": 1, "content": "Great paper"}]
            result = note(id="slug:smith2024quantum")
            assert len(result["notes"]) == 1

    def test_write_note(self):
        with _MockStoreFixture() as mock:
            result = note(id="slug:smith2024quantum", content="Key insight")
            assert "note_id" in result
            mock.add_note.assert_called_once()

    def test_delete_by_note_id(self):
        with _MockStoreFixture() as mock:
            result = note(id="note:42", delete=True)
            assert result["deleted"] is True
            mock.delete_note.assert_called_once_with(42)

    def test_update_by_note_id(self):
        with _MockStoreFixture() as mock:
            result = note(id="note:42", content="Updated content")
            assert result["updated"] is True

    def test_read_by_note_id(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [
                {"id": 42, "content": "Found it"},
                {"id": 99, "content": "Other note"},
            ]
            result = note(id="note:42")
            assert len(result["notes"]) == 1
            assert result["notes"][0]["id"] == 42

    def test_note_on_block(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "smith2024-p01-001",
                    "block_type": "text",
                    "block_index": 0,
                },
            ]
            result = note(id="slug:smith2024quantum/chunk/0", content="Block note")
            assert "note_id" in result
            mock.add_note.assert_called_once()
