"""Tests for MCP tools (mock store)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import acatome_mcp.tools as tools_mod
from acatome_mcp.tools import _T, _clean_jats, note, paper, search


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
            "block_index": None,
            "page": None,
            "block_type": "abstract",
            "section_path": None,
            "preview": "We present a new approach...",
        },
        {
            "node_id": "smith2024-p01-001",
            "block_index": 1,
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
            assert isinstance(result, str)
            assert "Quantum Error Correction" in result
            assert "Next:" in result
            assert "abstract" in result.lower()

    def test_not_found(self):
        with _MockStoreFixture() as mock:
            mock.get.return_value = None
            result = paper(id="slug:nonexistent")
            assert "not found" in result.lower()


class TestPaperViews:
    def test_meta(self):
        with _MockStoreFixture() as mock:
            result = paper(id="slug:smith2024quantum/meta")
            assert isinstance(result, str)
            assert "smith2024quantum" in result
            assert "metadata" in result
            assert "Next:" in result

    def test_abstract(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"text": "We present a new approach...", "block_type": "abstract"}
            ]
            result = paper(id="slug:smith2024quantum/abstract")
            assert "We present a new approach..." in result

    def test_toc(self):
        with _MockStoreFixture() as mock:
            result = paper(id="slug:smith2024quantum/toc")
            assert "2 blocks" in result
            assert "qubits" in result

    def test_chunk_all(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "n0",
                    "block_type": "text",
                    "block_index": 0,
                    "text": "chunk 0",
                }
            ]
            result = paper(id="slug:smith2024quantum/chunk")
            assert isinstance(result, str)
            assert "chunk 0" in result

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
            result = paper(id="slug:smith2024quantum#4")
            assert "four" in result
            assert "smith2024quantum#4" in result

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
            result = paper(id="slug:smith2024quantum#11..")
            assert "block 11" in result
            assert "block 19" in result


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
            assert "about qubits" in result
            assert "about cats" not in result


class TestPaperHints:
    def test_default_has_hints(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum")
            assert "Next:" in result
            assert "toc" in result

    def test_toc_has_chunk_hint(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum/toc")
            assert "#N" in result


class TestSearch:
    def test_search_summary_mode(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "qubit fidelity result",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "smith2024quantum", "year": 2024, "title": "Quantum"},
                }
            ]
            result = search(query="qubit fidelity")
            assert isinstance(result, str)
            assert "1 paper" in result
            assert "smith2024quantum" in result
            assert "slug | title | snippet" in result  # header row

    def test_search_summary_dedup(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "hit one",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "foo2020", "year": 2020, "title": "Foo"},
                },
                {
                    "text": "hit two",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "foo2020", "year": 2020, "title": "Foo"},
                },
            ]
            result = search(query="test")
            assert "1 paper" in result
            assert "2 hits" in result

    def test_search_summary_with_paper_summary(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "raw chunk",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "bar2021", "year": 2021, "title": "Bar"},
                }
            ]
            mock.get_blocks.return_value = [
                {"text": "Generated paper summary about bar.", "block_type": "paper_summary"}
            ]
            result = search(query="test")
            assert "\u2726" in result  # generated marker
            assert "Generated paper summary" in result

    def test_search_chunk_mode(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "exact passage",
                    "metadata": {"block_type": "text", "page": 5},
                    "paper": {"slug": "smith2024quantum", "year": 2024, "title": "Quantum"},
                }
            ]
            result = search(query="qubit", style="chunk")
            assert "1 hit" in result
            assert "p5" in result
            assert "exact passage" in result
            assert "slug#index (page)" in result  # header row

    def test_search_filters_reference_blocks(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "(6) Sumida, K.; Rogow, D. L.",
                    "metadata": {"block_type": "text", "section_path": '["References"]'},
                    "paper": {"slug": "xie2020", "year": 2020, "title": "Xie"},
                },
                {
                    "text": "useful result",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "good2020", "year": 2020, "title": "Good"},
                },
            ]
            result = search(query="test")
            assert "xie2020" not in result
            assert "good2020" in result

    def test_search_no_results(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = []
            result = search(query="nonexistent")
            assert "0 results" in result

    def test_search_year_exact(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "old paper",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "old2010", "year": 2010, "title": "Old"},
                },
                {
                    "text": "new paper",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "new2020", "year": 2020, "title": "New"},
                },
            ]
            result = search(query="test", year="2020")
            assert "new2020" in result
            assert "old2010" not in result

    def test_search_year_range(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "a",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "p2018", "year": 2018, "title": "A"},
                },
                {
                    "text": "b",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "p2020", "year": 2020, "title": "B"},
                },
                {
                    "text": "c",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "p2025", "year": 2025, "title": "C"},
                },
            ]
            result = search(query="test", year="2019..2024")
            assert "p2020" in result
            assert "p2018" not in result
            assert "p2025" not in result

    def test_search_year_from(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "a",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "p2015", "year": 2015, "title": "A"},
                },
                {
                    "text": "b",
                    "metadata": {"block_type": "text"},
                    "paper": {"slug": "p2022", "year": 2022, "title": "B"},
                },
            ]
            result = search(query="test", year="2020..")
            assert "p2022" in result
            assert "p2015" not in result


class TestSearchScope:
    def test_scope_single_slug(self):
        with _MockStoreFixture() as mock:
            mock.search_text.return_value = [
                {
                    "text": "LOV2 result",
                    "metadata": {"block_type": "text", "paper_id": "1"},
                    "paper": {"slug": "zimmerman2016engineering", "year": 2016, "title": "LOV2"},
                }
            ]
            result = search(query="LOV2", scope="zimmerman2016engineering")
            assert "zimmerman2016engineering" in result
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
            assert "No papers matched" in result
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
            assert isinstance(result, str)
            assert "1 note" in result
            assert "Great paper" in result

    def test_chunk_notes_modifier(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"node_id": "n9", "block_type": "text", "block_index": 9},
            ]
            mock.get_notes.return_value = [{"id": 2, "content": "Chunk note"}]
            result = paper(id="slug:smith2024quantum#9/notes")
            assert isinstance(result, str)
            assert "Chunk note" in result

    def test_default_view_note_count(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [
                {"id": 1, "content": "n1", "block_node_id": None},
                {"id": 2, "content": "n2", "block_node_id": None},
            ]
            result = paper(id="slug:smith2024quantum")
            assert "2 note(s)" in result
            assert "notes" in result

    def test_default_view_no_note_count_when_zero(self):
        with _MockStoreFixture():
            result = paper(id="slug:smith2024quantum")
            assert "note(s)" not in result

    def test_chunk_note_count_annotated(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {"node_id": "n0", "block_type": "text", "block_index": 0, "text": "hi"},
            ]
            mock.get_notes.return_value = [
                {"id": 1, "block_node_id": "n0", "content": "annotated"},
            ]
            result = paper(id="slug:smith2024quantum/chunk")
            assert isinstance(result, str)
            assert "notes" in result


class TestNote:
    def test_read_notes(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [{"id": 1, "content": "Great paper"}]
            result = note(id="slug:smith2024quantum")
            assert isinstance(result, str)
            assert "Great paper" in result
            assert "1 note" in result

    def test_write_note(self):
        with _MockStoreFixture() as mock:
            result = note(id="slug:smith2024quantum", content="Key insight")
            assert isinstance(result, str)
            assert "created" in result.lower()
            mock.add_note.assert_called_once()

    def test_delete_by_note_id(self):
        with _MockStoreFixture() as mock:
            result = note(id="note:42", delete=True)
            assert isinstance(result, str)
            assert "Deleted" in result
            mock.delete_note.assert_called_once_with(42)

    def test_update_by_note_id(self):
        with _MockStoreFixture() as mock:
            result = note(id="note:42", content="Updated content")
            assert isinstance(result, str)
            assert "Updated" in result

    def test_read_by_note_id(self):
        with _MockStoreFixture() as mock:
            mock.get_notes.return_value = [
                {"id": 42, "content": "Found it"},
                {"id": 99, "content": "Other note"},
            ]
            result = note(id="note:42")
            assert isinstance(result, str)
            assert "Found it" in result

    def test_note_on_block(self):
        with _MockStoreFixture() as mock:
            mock.get_blocks.return_value = [
                {
                    "node_id": "smith2024-p01-001",
                    "block_type": "text",
                    "block_index": 0,
                },
            ]
            result = note(id="slug:smith2024quantum#0", content="Block note")
            assert isinstance(result, str)
            assert "created" in result.lower()
            mock.add_note.assert_called_once()


# ---------------------------------------------------------------------------
# _clean_jats
# ---------------------------------------------------------------------------


class TestCleanJats:
    def test_subscript_digits(self):
        assert _clean_jats("CO<jats:sub>2</jats:sub>") == "CO₂"

    def test_superscript_digits(self):
        assert _clean_jats("10<jats:sup>-3</jats:sup>") == "10⁻³"

    def test_italic(self):
        assert _clean_jats("<jats:italic>in situ</jats:italic>") == "*in situ*"

    def test_bold(self):
        assert _clean_jats("<jats:bold>important</jats:bold>") == "**important**"

    def test_title_and_paragraph(self):
        raw = "<jats:title>Significance</jats:title><jats:p>Some text.</jats:p>"
        result = _clean_jats(raw)
        assert "**Significance**" in result
        assert "Some text." in result

    def test_strips_remaining_tags(self):
        raw = "<jats:sec><jats:p>Hello</jats:p></jats:sec>"
        result = _clean_jats(raw)
        assert "<" not in result
        assert "Hello" in result

    def test_passthrough_no_jats(self):
        plain = "No XML here, just plain text."
        assert _clean_jats(plain) == plain

    def test_combined_chemistry(self):
        raw = "H<jats:sub>2</jats:sub>O and CO<jats:sub>2</jats:sub>"
        assert _clean_jats(raw) == "H₂O and CO₂"


class TestToolPrefix:
    def test_prefix_value(self):
        assert _T == "acatome."

    def test_hint_has_prefix(self):
        mock = _make_mock_store()
        with patch.object(tools_mod, "_get_store", return_value=mock):
            result = paper(id="slug:smith2024quantum")
        assert "acatome.paper(" in result
        assert "acatome.search(" in result
        assert "acatome.note(" in result
