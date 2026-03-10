"""Tests for URI parser."""

from __future__ import annotations

import pytest

from acatome_mcp.uri import parse


class TestParseBasic:
    def test_slug_bare(self):
        u = parse("slug:smith2024quantum")
        assert u.scheme == "slug"
        assert u.ident == "smith2024quantum"
        assert u.view == ""
        assert u.range_start is None

    def test_ref_bare(self):
        u = parse("ref:42")
        assert u.scheme == "ref"
        assert u.ident == "42"

    def test_slug_with_view(self):
        u = parse("slug:smith2024/abstract")
        assert u.scheme == "slug"
        assert u.ident == "smith2024"
        assert u.view == "abstract"

    def test_slug_with_view_and_range(self):
        u = parse("slug:smith2024/chunk/4")
        assert u.view == "chunk"
        assert u.range_start == 4
        assert u.range_end == 4
        assert u.is_single

    def test_closed_range(self):
        u = parse("slug:smith2024/chunk/4-6")
        assert u.range_start == 4
        assert u.range_end == 6
        assert not u.is_single
        assert not u.is_open_range

    def test_open_range(self):
        u = parse("slug:smith2024/chunk/11-")
        assert u.range_start == 11
        assert u.range_end is None
        assert u.is_open_range

    def test_page_range(self):
        u = parse("slug:smith2024/page/2-4")
        assert u.view == "page"
        assert u.range_start == 2
        assert u.range_end == 4


class TestParseDOI:
    def test_doi_bare(self):
        u = parse("doi:10.1038/s41567-024-1234-5")
        assert u.scheme == "doi"
        assert u.ident == "10.1038/s41567-024-1234-5"
        assert u.view == ""

    def test_doi_with_view(self):
        u = parse("doi:10.1038/s41567-024-1234-5/toc")
        assert u.ident == "10.1038/s41567-024-1234-5"
        assert u.view == "toc"

    def test_doi_with_view_and_range(self):
        u = parse("doi:10.1038/s41567-024-1234-5/page/3")
        assert u.ident == "10.1038/s41567-024-1234-5"
        assert u.view == "page"
        assert u.range_start == 3


class TestParseNote:
    def test_note_id(self):
        u = parse("note:42")
        assert u.scheme == "note"
        assert u.ident == "42"


class TestParseNotes:
    def test_paper_level_notes(self):
        u = parse("slug:smith2024/notes")
        assert u.scheme == "slug"
        assert u.ident == "smith2024"
        assert u.view == ""
        assert u.notes is True

    def test_chunk_notes(self):
        u = parse("slug:smith2024/chunk/9/notes")
        assert u.view == "chunk"
        assert u.range_start == 9
        assert u.notes is True

    def test_toc_notes(self):
        u = parse("slug:smith2024/toc/notes")
        assert u.view == "toc"
        assert u.notes is True

    def test_doi_notes(self):
        u = parse("doi:10.1038/s41567-024-1234-5/notes")
        assert u.ident == "10.1038/s41567-024-1234-5"
        assert u.notes is True
        assert u.view == ""

    def test_no_notes_by_default(self):
        u = parse("slug:smith2024/chunk/4")
        assert u.notes is False


class TestParseSupplement:
    def test_supplement_bare(self):
        u = parse("slug:smith2024/supplement/s1")
        assert u.ident == "smith2024"
        assert u.supplement == "s1"
        assert u.view == ""

    def test_supplement_with_view(self):
        u = parse("slug:smith2024/supplement/s1/toc")
        assert u.ident == "smith2024"
        assert u.supplement == "s1"
        assert u.view == "toc"

    def test_supplement_with_chunk_range(self):
        u = parse("slug:smith2024/supplement/methods/chunk/4")
        assert u.supplement == "methods"
        assert u.view == "chunk"
        assert u.range_start == 4

    def test_supplement_with_notes(self):
        u = parse("slug:smith2024/supplement/s1/notes")
        assert u.supplement == "s1"
        assert u.notes is True
        assert u.view == ""

    def test_supplement_chunk_notes(self):
        u = parse("slug:smith2024/supplement/s1/chunk/4/notes")
        assert u.supplement == "s1"
        assert u.view == "chunk"
        assert u.range_start == 4
        assert u.notes is True

    def test_supplement_lowercased(self):
        u = parse("slug:smith2024/supplement/S1")
        assert u.supplement == "s1"

    def test_doi_with_supplement(self):
        u = parse("doi:10.1038/s41567-024-1234-5/supplement/s1/toc")
        assert u.ident == "10.1038/s41567-024-1234-5"
        assert u.supplement == "s1"
        assert u.view == "toc"

    def test_no_supplement_by_default(self):
        u = parse("slug:smith2024/chunk/4")
        assert u.supplement is None

    def test_empty_supplement_name_raises(self):
        with pytest.raises(ValueError, match="Empty supplement"):
            parse("slug:smith2024/supplement/")


class TestParseChunkHash:
    """Tests for #N chunk shorthand syntax."""

    def test_hash_single(self):
        u = parse("slug:smith2024#38")
        assert u.ident == "smith2024"
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.range_end == 38
        assert u.is_single

    def test_hash_closed_range(self):
        u = parse("slug:smith2024#38-42")
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.range_end == 42

    def test_hash_open_range(self):
        u = parse("slug:smith2024#38-")
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.range_end is None
        assert u.is_open_range

    def test_hash_with_notes(self):
        u = parse("slug:smith2024#38/notes")
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.notes is True

    def test_hash_with_summary(self):
        u = parse("slug:smith2024#38/summary")
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.summary is True

    def test_hash_range_with_summary(self):
        u = parse("slug:smith2024#38-42/summary")
        assert u.view == "chunk"
        assert u.range_start == 38
        assert u.range_end == 42
        assert u.summary is True

    def test_hash_with_supplement(self):
        u = parse("slug:smith2024/supplement/s1#4")
        assert u.supplement == "s1"
        assert u.view == "chunk"
        assert u.range_start == 4

    def test_hash_conflicts_with_other_view(self):
        with pytest.raises(ValueError, match="Cannot combine"):
            parse("slug:smith2024#38/toc")


class TestParseSummary:
    """Tests for /summary modifier."""

    def test_paper_level_summary_is_view(self):
        u = parse("slug:smith2024/summary")
        assert u.view == "summary"
        assert u.summary is False

    def test_chunk_summary_is_modifier(self):
        u = parse("slug:smith2024#38/summary")
        assert u.view == "chunk"
        assert u.summary is True
        assert u.range_start == 38

    def test_no_summary_by_default(self):
        u = parse("slug:smith2024#38")
        assert u.summary is False

    def test_summary_and_notes(self):
        u = parse("slug:smith2024#38/summary/notes")
        assert u.view == "chunk"
        assert u.summary is True
        assert u.notes is True


class TestParseErrors:
    def test_missing_scheme(self):
        with pytest.raises(ValueError, match="Missing scheme"):
            parse("smith2024quantum")

    def test_unknown_scheme(self):
        with pytest.raises(ValueError, match="Unknown scheme"):
            parse("foo:bar")

    def test_empty_ident(self):
        with pytest.raises(ValueError, match="Empty identifier"):
            parse("slug:")

    def test_unknown_view(self):
        with pytest.raises(ValueError, match="Unknown view"):
            parse("slug:smith2024/blorp")
