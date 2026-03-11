"""MCP tool implementations for acatome.

Three tools:
  ``paper``  — read paper content via URI addressing
  ``search`` — semantic search with provenance
  ``note``   — read / write / delete user notes
"""

from __future__ import annotations

import json
import re
from typing import Any

from acatome_store.store import Store

from acatome_mcp.uri import PAGE_SIZE, ParsedURI, parse

# Tool name prefix — MCP qualifies tools as "server.tool", hints must match.
_T = "acatome."

# ---------------------------------------------------------------------------
# Shared store singleton
# ---------------------------------------------------------------------------

_store: Store | None = None


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_identifier(store: Store, uri: ParsedURI) -> str | int:
    """Turn parsed URI into a store-level identifier (slug, DOI str, or int)."""
    if uri.scheme == "ref":
        return int(uri.ident)
    if uri.scheme == "doi":
        return uri.ident  # DOI string, store.get handles it
    if uri.scheme == "slug":
        return uri.ident  # slug string
    if uri.scheme in ("arxiv", "s2"):
        return uri.ident  # store._find_ref checks arxiv_id / s2_id
    raise ValueError(f"Cannot resolve scheme {uri.scheme!r} to paper identifier")


def _paginate(
    items: list[dict],
    page: int,
) -> tuple[list[dict], int, bool]:
    """Slice items by result page (1-indexed). Returns (page_items, total, has_more)."""
    total = len(items)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = items[start:end]
    has_more = end < total
    return page_items, total, has_more


def _filter_items(
    items: list[dict],
    filter_str: str,
    fields: tuple[str, ...] = ("text", "summary", "preview"),
) -> list[dict]:
    """Case-insensitive substring filter across given fields."""
    if not filter_str:
        return items
    q = filter_str.lower()
    result = []
    for item in items:
        for f in fields:
            val = item.get(f)
            if val and q in val.lower():
                result.append(item)
                break
    return result


def _range_slice(
    items: list[dict], uri: ParsedURI, index_key: str = "block_index"
) -> list[dict]:
    """Apply range addressing (by block_index or page number)."""
    if not uri.has_range:
        return items
    start = uri.range_start
    end = uri.range_end
    if uri.is_open_range:
        # e.g. /chunk/11- → block_index >= 11, first PAGE_SIZE
        return [i for i in items if (i.get(index_key) or 0) >= start][:PAGE_SIZE]
    if uri.is_single:
        return [i for i in items if i.get(index_key) == start]
    # Closed range: start-end inclusive
    return [i for i in items if start <= (i.get(index_key) or 0) <= end]


# ---------------------------------------------------------------------------
# JATS XML → markdown / Unicode
# ---------------------------------------------------------------------------

_JATS_SUB_MAP = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_JATS_SUP_MAP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def _jats_sub(m: re.Match) -> str:
    return m.group(1).translate(_JATS_SUB_MAP)


def _jats_sup(m: re.Match) -> str:
    return m.group(1).translate(_JATS_SUP_MAP)


def _clean_jats(text: str) -> str:
    """Convert JATS XML tags to markdown / Unicode.

    Handles <jats:sub>, <jats:sup>, <jats:italic>, <jats:bold>,
    <jats:title>, <jats:p>, and strips remaining XML tags.
    """
    if "<jats:" not in text and "<mml:" not in text:
        return text

    # Subscript → Unicode digits
    text = re.sub(r"<jats:sub>([^<]+)</jats:sub>", _jats_sub, text)
    # Superscript → Unicode digits
    text = re.sub(r"<jats:sup>([^<]+)</jats:sup>", _jats_sup, text)
    # Italic → markdown
    text = re.sub(r"<jats:italic>([^<]+)</jats:italic>", r"*\1*", text)
    # Bold → markdown
    text = re.sub(r"<jats:bold>([^<]+)</jats:bold>", r"**\1**", text)
    # Title → bold
    text = re.sub(r"<jats:title>([^<]*)</jats:title>", r"**\1** ", text)
    # Paragraph → double newline
    text = re.sub(r"<jats:p>", "\n", text)
    text = re.sub(r"</jats:p>", "\n", text)
    # Strip all remaining XML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace (preserve double newlines for paragraphs)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _make_hint(
    base_id: str, suffix: str, filter_str: str = "", page: int | None = None
) -> str:
    """Build a hint string for the next action."""
    call = f"{_T}paper('{base_id}{suffix}'"
    if filter_str:
        call += f", filter='{filter_str}'"
    if page is not None:
        call += f", page={page}"
    call += ")"
    return call


def _base_id(uri: ParsedURI) -> str:
    """Reconstruct scheme:ident portion."""
    return f"{uri.scheme}:{uri.ident}"


def _clean_section_path(raw: str | None) -> str:
    """Convert JSON section_path to clean text: '§1.5. Metal–Organic Frameworks'."""
    if not raw:
        return ""
    try:
        sections = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return ""
    if sections:
        return "§" + str(sections[-1])
    return ""


def _format_block_line(
    item: dict, slug: str, show_summary: bool = False
) -> str:
    """Format a single block as compact text line(s).

    Returns:
        slug:x#N (pP) | type | §section
        text or summary content
    """
    bi = item.get("block_index")
    pg = item.get("page")
    bt = item.get("block_type", "text")
    section = _clean_section_path(item.get("section_path"))

    # Header: slug:x#N (pP) | type | §section
    chunk_ref = f"slug:{slug}#{bi}" if bi is not None else f"slug:{slug}"
    page_ref = f" (p{pg})" if pg else ""
    parts = [f"{chunk_ref}{page_ref}", bt]
    if section:
        parts.append(section)
    header = " | ".join(parts)

    # Content: summary or text
    if show_summary:
        content = item.get("summary") or "(no summary available)"
    else:
        content = item.get("text", "")

    return f"{header}\n{content}"


def _format_hints(hints: list[str]) -> str:
    """Format hints as a Next: block."""
    if not hints:
        return ""
    return "\n\nNext:\n" + "\n".join(hints)


def _format_meta_text(meta: dict) -> str:
    """Format metadata dict as compact key: value lines."""
    lines = []
    for k, v in meta.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _annotate_note_counts(items: list[dict], store: Store, ref_id: int) -> list[dict]:
    """Add note_count field to items that have notes (skip if 0)."""
    all_notes = store.get_notes(ref_id=ref_id)
    # Build {block_node_id: count}
    counts: dict[str | None, int] = {}
    for n in all_notes:
        nid = n.get("block_node_id")
        counts[nid] = counts.get(nid, 0) + 1
    for item in items:
        node_id = item.get("node_id")
        if node_id and counts.get(node_id, 0) > 0:
            item["note_count"] = counts[node_id]
    return items


# ---------------------------------------------------------------------------
# paper() tool
# ---------------------------------------------------------------------------


def _format_paper_list(papers: list[dict]) -> str:
    """Format list_papers output as compact text."""
    if not papers:
        return "📚 No papers in library.\nUse acatome-extract to ingest PDFs."
    lines = [f"📚 {len(papers)} paper(s) in library"]
    lines.append("slug | year | title | blocks | keywords")
    for p in papers:
        slug = p.get("slug") or "?"
        year = p.get("year") or "?"
        title = _truncate(p.get("title") or "(untitled)", 60)
        bc = p.get("block_count", 0)
        kw = p.get("keywords")
        if isinstance(kw, list):
            kw = "; ".join(kw[:5])
        elif not kw:
            kw = ""
        lines.append(f"{slug} | {year} | {title} | {bc} blocks | {kw}")
    lines.append("")
    lines.append("Next:")
    # Pick first slug for examples
    first = papers[0].get("slug", "example")
    lines.append(f"{_T}paper('slug:{first}') — overview of a paper")
    lines.append(f"{_T}paper('slug:{first}/toc') — table of contents")
    lines.append(f"{_T}search('your query') — semantic search across all papers")
    return "\n".join(lines)


def paper(id: str = "", filter: str = "", page: int = 1) -> str:
    """Look up a paper — read its abstract, browse structure, or dive into specific passages.

    Args:
        id: URI — scheme:identifier[#chunk][/view][/summary][/notes]
            Schemes: slug, doi, arxiv, s2, ref
            Views: meta, abstract, summary, toc, page, fig
            Chunks: #N (single), #N..M (range), #N.. (open, next 10)
            Modifiers: /summary (enrichment summary), /notes (annotations)
            Empty string: list all papers in the library.
        filter: Substring filter on block text (case-insensitive).
        page: Result page (1-indexed) for paginated views.
    """
    # Empty id → list all papers
    if not id or not id.strip():
        store = _get_store()
        papers = store.list_papers()
        return _format_paper_list(papers)

    uri = parse(id)
    store = _get_store()
    ident = _resolve_identifier(store, uri)
    bid = _base_id(uri)

    paper_dict = store.get(ident)
    if paper_dict is None:
        hints = [f"{_T}search('your query') — try searching"]
        return f"Paper not found: {id}" + _format_hints(hints)

    ref_id = paper_dict.get("ref_id") or paper_dict.get("id")
    slug = paper_dict.get("slug", "")
    # Prefer slug for hints, fall back to original scheme
    hint_id = f"slug:{slug}" if slug else bid
    supp = uri.supplement  # None = main paper
    supp_prefix = f"/supplement/{supp}" if supp else ""

    view = uri.view

    # --- /notes modifier: intercept early ---
    if uri.notes:
        block_node_id = None
        if uri.view == "chunk" and uri.range_start is not None:
            blocks = store.get_blocks(ident, block_type="text", supplement=supp)
            target = [b for b in blocks if b.get("block_index") == uri.range_start]
            if target:
                block_node_id = target[0]["node_id"]
            else:
                return f"Chunk {uri.range_start} not found"
        if block_node_id:
            notes = store.get_notes(block_node_id=block_node_id)
        else:
            notes = store.get_notes(ref_id=ref_id)

        if notes:
            note_lines = []
            for n in notes:
                nid = n.get("id")
                content = n.get("content", "")
                note_lines.append(f"[{nid}] {content}")
            body = f"{len(notes)} note(s) for {hint_id}\n" + "\n".join(note_lines)
        else:
            body = f"No notes for {hint_id}"

        hints = [
            f"{_T}note('{hint_id}', content='...') — add a note",
            f"{_T}paper('{hint_id}') — view paper",
        ]
        for n in notes:
            nid = n.get("id")
            hints.append(f"{_T}note('note:{nid}', content='...') — edit note {nid}")
            hints.append(f"{_T}note('note:{nid}', delete=True) — delete note {nid}")
        return body + _format_hints(hints)

    # --- meta ---
    if view == "meta":
        meta = _clean_meta(paper_dict)
        body = f"slug:{slug} — metadata\n" + _format_meta_text(meta)
        hints = [
            f"{_T}paper('{hint_id}/abstract') — read abstract",
            f"{_T}paper('{hint_id}/toc') — browse structure",
            f"{_T}paper('{hint_id}/notes') — read notes",
        ]
        return body + _format_hints(hints)

    # --- abstract ---
    if view == "abstract":
        blocks = store.get_blocks(ident, block_type="abstract", supplement=supp)
        text = _clean_jats(blocks[0]["text"]) if blocks else "(no abstract)"
        body = f"slug:{slug} — abstract\n{text}"
        hints = [
            f"{_T}paper('{hint_id}/toc') — browse structure",
            f"{_T}paper('{hint_id}#0') — read first block",
            f"{_T}search('{_truncate(text, 40)}') — find related",
        ]
        return body + _format_hints(hints)

    # --- summary ---
    if view == "summary":
        blocks = store.get_blocks(ident, block_type="paper_summary", supplement=supp)
        text = blocks[0]["text"] if blocks else "(no summary available)"
        prov = " (generated)" if blocks else ""
        body = f"slug:{slug} — summary{prov}\n{text}"
        hints = [
            f"{_T}paper('{hint_id}/abstract') — original abstract",
            f"{_T}paper('{hint_id}/toc') — browse structure",
        ]
        return body + _format_hints(hints)

    # --- toc ---
    if view == "toc":
        toc = store.get_toc(ident, supplement=supp)
        toc = _filter_items(toc, filter, fields=("preview", "section_path"))

        # Hide junk blocks unless filter explicitly asks for them
        show_junk = filter and "junk" in filter.lower()
        if not show_junk:
            junk_count = sum(1 for t in toc if t.get("block_type") == "junk")
            toc = [t for t in toc if t.get("block_type") != "junk"]
        else:
            junk_count = 0

        toc_page_size = 100
        total = len(toc)
        start = (page - 1) * toc_page_size
        end = start + toc_page_size
        page_items = toc[start:end]
        has_more = end < total

        lines = []
        for item in page_items:
            bi = item.get("block_index")
            pg = item.get("page", 0)
            bt = item.get("block_type", "text")
            preview = (item.get("preview") or "").strip()
            section = _clean_section_path(item.get("section_path"))
            note_count = item.get("note_count", 0)

            # Skip empty previews (e.g. blank figures)
            if not preview and bt in ("figure", "table"):
                continue

            # Format: #N (pP) | type | §section | preview
            idx = f"#{bi}" if bi is not None else "  "
            pg_str = f"(p{pg})" if pg else ""
            type_tag = {
                "section_header": "H",
                "figure": "fig",
                "table": "tab",
                "junk": "junk",
            }.get(bt, bt)
            parts = [f"{idx} {pg_str}", type_tag]
            if section:
                parts.append(section)
            parts.append(preview)
            line = " | ".join(parts)

            if note_count:
                line += f"  [{note_count} note(s)]"
            lines.append(line)

        header = f"TOC for slug:{slug} — {total} blocks"
        if junk_count:
            header += f" ({junk_count} junk hidden)"
        if page > 1 or has_more:
            header += f" (page {page})"
        header += "\n#index (page) | type | §section | summary"
        body = header + "\n" + "\n".join(lines)

        hints = []
        if has_more:
            hints.append(
                _make_hint(hint_id, "/toc", filter, page=page + 1)
                + " — more entries"
            )
        hints.append(f"{_T}paper('{hint_id}#N') — read block N in full")
        hints.append(f"{_T}paper('{hint_id}#N/summary') — read block N summary")
        if junk_count:
            hints.append(
                f"{_T}paper('{hint_id}/toc', filter='junk') — show {junk_count} hidden junk blocks"
            )
        return body + _format_hints(hints)

    # --- chunk ---
    if view == "chunk":
        all_blocks = store.get_blocks(ident, block_type="text", supplement=supp)
        show_summary = uri.summary

        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="block_index")
            _annotate_note_counts(items, store, ref_id)

            # Compact text output
            mode_label = "summary" if show_summary else "text"
            header = (
                f"slug:{slug}#{uri.range_start}"
                + (f"-{uri.range_end}" if uri.range_end and uri.range_end != uri.range_start else "")
                + (f"{'/' + mode_label if show_summary else ''}")
                + f" — {len(items)} block{'s' if len(items) != 1 else ''}"
            )
            header += f"\nslug#index (page) | type | §section — "
            header += "enrichment summary" if show_summary else "full text"

            blocks_text = []
            for item in items:
                blocks_text.append(_format_block_line(item, slug, show_summary))

            hints = []
            if uri.is_open_range and len(items) == PAGE_SIZE:
                next_start = uri.range_start + PAGE_SIZE
                hints.append(f"{_T}paper('{hint_id}#{next_start}-') — next {PAGE_SIZE}")
            if not uri.is_single:
                if show_summary:
                    hints.append(f"{_T}paper('{hint_id}#{uri.range_start}') — read full text")
                else:
                    hints.append(f"{_T}paper('{hint_id}#{uri.range_start}/summary') — see summaries")
            for item in items:
                if item.get("note_count"):
                    bi = item.get("block_index")
                    hints.append(
                        f"{_T}paper('{hint_id}#{bi}/notes') — {item['note_count']} note(s)"
                    )

            body = header + "\n\n" + "\n\n".join(blocks_text)
            return body + _format_hints(hints)
        else:
            # No range: filter + paginate
            filtered = _filter_items(all_blocks, filter)
            items, total, has_more = _paginate(filtered, page)
            _annotate_note_counts(items, store, ref_id)

            blocks_text = []
            for item in items:
                blocks_text.append(_format_block_line(item, slug, show_summary))

            header = f"slug:{slug} — {total} blocks"
            if page > 1 or has_more:
                header += f" (page {page})"
            header += f"\nslug#index (page) | type | §section"

            hints = []
            if has_more:
                hints.append(
                    _make_hint(hint_id, "/chunk", filter, page=page + 1)
                    + f" — next {PAGE_SIZE}"
                )
            hints.append(f"{_T}paper('{hint_id}#N') — read specific block")
            for item in items:
                if item.get("note_count"):
                    bi = item.get("block_index")
                    hints.append(
                        f"{_T}paper('{hint_id}#{bi}/notes') — {item['note_count']} note(s)"
                    )

            body = header + "\n\n" + "\n\n".join(blocks_text)
            return body + _format_hints(hints)

    # --- page ---
    if view == "page":
        all_blocks = store.get_blocks(ident, supplement=supp)
        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="page")
            items = _filter_items(items, filter)

            blocks_text = []
            for item in items:
                blocks_text.append(_format_block_line(item, slug))

            header = f"slug:{slug}/page/{uri.range_start} — {len(items)} blocks"
            hints = []
            if uri.is_open_range and len(items) == PAGE_SIZE:
                next_start = uri.range_start + PAGE_SIZE
                hints.append(_make_hint(hint_id, f"/page/{next_start}-", filter))
            body = header + "\n\n" + "\n\n".join(blocks_text)
            return body + _format_hints(hints)
        else:
            return "page view requires a range, e.g. /page/3 or /page/2-4"

    # --- fig ---
    if view == "fig":
        all_blocks = store.get_blocks(ident, block_type="figure", supplement=supp)
        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="block_index")
        else:
            items = all_blocks[:PAGE_SIZE]

        blocks_text = []
        for item in items:
            blocks_text.append(_format_block_line(item, slug))

        header = f"slug:{slug}/fig — {len(items)} of {len(all_blocks)} figures"
        body = header + "\n\n" + "\n\n".join(blocks_text) if blocks_text else header
        hints = [
            f"{_T}paper('{hint_id}/toc') — browse structure",
            f"{_T}paper('{hint_id}#N') — read block N",
        ]
        return body + _format_hints(hints)

    # --- default view (no view specified) ---
    if supp:
        # Supplement overview
        all_blocks = store.get_blocks(ident, supplement=supp)
        page_count = max((b.get("page") or 0) for b in all_blocks) if all_blocks else 0
        body = f"slug:{slug}/supplement/{supp} — {len(all_blocks)} blocks, {page_count} pages"
        hints = [
            f"{_T}paper('{hint_id}{supp_prefix}/toc') — browse structure",
            f"{_T}paper('{hint_id}{supp_prefix}#0..') — read blocks",
            f"{_T}paper('{hint_id}') — back to main paper",
        ]
        return body + _format_hints(hints)

    meta = _clean_meta(paper_dict)
    abstract_blocks = store.get_blocks(ident, block_type="abstract")
    abstract_text = _clean_jats(abstract_blocks[0]["text"]) if abstract_blocks else None
    all_blocks = store.get_blocks(ident)
    page_count = max((b.get("page") or 0) for b in all_blocks) if all_blocks else 0
    has_summary = any(b["block_type"] == "paper_summary" for b in all_blocks)
    paper_notes = store.get_notes(ref_id=ref_id)
    supplements = store.get_supplements(ident)
    is_retracted = paper_dict.get("retracted", False)
    retraction_note = paper_dict.get("retraction_note", "")

    # Build text
    title = meta.get("title", slug)
    authors = meta.get("authors", "")
    year = meta.get("year", "")
    doi = meta.get("doi", "")

    lines = [f"slug:{slug} — {authors} ({year})" if year else f"slug:{slug}"]
    lines.append(title)
    if doi:
        lines.append(f"doi: {doi}")
    lines.append(f"{len(all_blocks)} blocks | {page_count} pages" + (" | has summary" if has_summary else ""))

    if is_retracted:
        warning = f"⚠ RETRACTED"
        if retraction_note:
            warning += f" — {retraction_note}"
        lines.insert(0, warning)

    if paper_notes:
        lines.append(f"{len(paper_notes)} note(s)")

    if supplements:
        lines.append(f"supplements: {', '.join(supplements)}")

    if abstract_text:
        lines.append("")
        lines.append(f"Abstract: {abstract_text}")

    hints = [
        f"{_T}paper('{hint_id}/toc') — browse structure",
        f"{_T}paper('{hint_id}#0..') — read first blocks",
        f"{_T}paper('{hint_id}/page/1') — read page 1",
        f"{_T}search('...') — find related content",
        f"{_T}note('{hint_id}', content='...') — add a note",
    ]
    if paper_notes:
        hints.insert(0, f"{_T}paper('{hint_id}/notes') — {len(paper_notes)} note(s)")
    if supplements:
        for s in supplements:
            hints.append(f"{_T}paper('{hint_id}/supplement/{s}') — supplement {s}")

    return "\n".join(lines) + _format_hints(hints)


def _clean_meta(paper_dict: dict) -> dict:
    """Extract clean metadata fields from paper dict."""
    keys = (
        "ref_id",
        "title",
        "authors",
        "year",
        "doi",
        "arxiv_id",
        "s2_id",
        "journal",
        "entry_type",
        "keywords",
        "slug",
        "verified",
        "ingested_at",
        "source",
    )
    return {k: paper_dict.get(k) for k in keys if paper_dict.get(k) is not None}


# ---------------------------------------------------------------------------
# search() helpers
# ---------------------------------------------------------------------------


def _parse_year_filter(year: str) -> tuple[int | None, int | None]:
    """Parse year filter string into (min_year, max_year) inclusive.

    Formats: "2020" (exact), "..2020" (≤2020), "2020.." (≥2020), "2020..2022" (range).
    Returns (None, None) if empty or unparseable.
    """
    year = year.strip()
    if not year:
        return None, None
    if year.startswith(".."):
        try:
            return None, int(year[2:])
        except ValueError:
            return None, None
    if year.endswith(".."):
        try:
            return int(year[:-2]), None
        except ValueError:
            return None, None
    if ".." in year:
        parts = year.split("..", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None, None
    try:
        y = int(year)
        return y, y
    except ValueError:
        return None, None


def _truncate(text: str | None, max_chars: int = 120) -> str:
    """Truncate text to max_chars, adding ellipsis if needed."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _resolve_scope(store: Store, scope: str) -> list[str]:
    """Resolve comma-separated slugs/DOIs to paper_id strings (ref_ids)."""
    paper_ids: list[str] = []
    for token in scope.split(","):
        token = token.strip()
        if not token:
            continue
        paper = store.get(token)
        if paper:
            rid = paper.get("ref_id") or paper.get("id")
            if rid is not None:
                paper_ids.append(str(rid))
    return paper_ids


# ---------------------------------------------------------------------------
# search() tool
# ---------------------------------------------------------------------------


_REF_SECTION_KEYWORDS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
    "citations",
}


def _is_reference_block(hit: dict[str, Any]) -> bool:
    """True if the hit comes from a references/bibliography section."""
    sp_raw = hit.get("metadata", {}).get("section_path", "[]")
    try:
        sections = json.loads(sp_raw) if isinstance(sp_raw, str) else sp_raw
    except (json.JSONDecodeError, TypeError):
        sections = []
    for sec in sections:
        if any(kw in str(sec).lower() for kw in _REF_SECTION_KEYWORDS):
            return True
    text = hit.get("text", "")
    if text and text.lstrip()[:1] == "(" and text.lstrip()[1:4].isdigit():
        return True
    return False


def _get_paper_summary(store: "Store", slug: str) -> str:
    """Look up the paper_summary block for a slug. Returns empty string if none."""
    blocks = store.get_blocks(slug, block_type="paper_summary")
    if blocks:
        return blocks[0].get("text", "")
    return ""


def search(
    query: str,
    top_k: int = 5,
    kinds: list[str] | None = None,
    scope: str = "",
    year: str = "",
    style: str = "summary",
) -> str:
    """Find papers and passages in your library by meaning, not just keywords.

    Use for: finding relevant papers, discovering connections, answering
    questions from the stored literature.

    Args:
        query: Natural language search query.
        top_k: Number of results (default 5).
        kinds: Block type filter (e.g. ["text"], ["abstract"]).
        scope: Restrict to specific slugs or DOIs (comma-separated).
        year: Year filter — "2020", "..2020", "2020..", "2020..2022".
        style: "summary" (default, one line per paper) or "chunk" (raw passages).
    """
    store = _get_store()
    where: dict[str, Any] = {}
    if kinds:
        where["block_type"] = {"$in": kinds} if len(kinds) > 1 else kinds[0]

    # Resolve scope to paper_id filter
    if scope:
        paper_ids = _resolve_scope(store, scope)
        if not paper_ids:
            return "No papers matched the scope filter."
        where["paper_id"] = {"$in": paper_ids} if len(paper_ids) > 1 else paper_ids[0]

    # Over-fetch to compensate for post-search filters
    year_min, year_max = _parse_year_filter(year)
    overfetch = 3 if (year_min or year_max) else 2
    fetch_k = top_k * overfetch

    hits = store.search_text(query, top_k=fetch_k, where=where or None)

    # Filter reference-section blocks
    hits = [h for h in hits if not _is_reference_block(h)]

    # Year filter (post-search — year is on ref, not in vector metadata)
    if year_min or year_max:
        filtered = []
        for hit in hits:
            y = (hit.get("paper") or {}).get("year")
            if y is None:
                continue
            if year_min and y < year_min:
                continue
            if year_max and y > year_max:
                continue
            filtered.append(hit)
        hits = filtered

    if not hits:
        parts = [f'0 results for "{_truncate(query, 60)}"']
        parts.append(f"{_T}search('{query}', top_k={top_k + 5}) — broaden search")
        return "\n".join(parts)

    query_display = _truncate(query, 60)

    if style == "chunk":
        return _format_chunk_results(hits[:top_k], query_display, query, top_k)

    return _format_summary_results(
        hits, store, query_display, query, top_k
    )


def _format_summary_results(
    hits: list[dict[str, Any]],
    store: "Store",
    query_display: str,
    query: str,
    top_k: int,
) -> str:
    """Default mode: dedup by slug, show paper_summary snippet."""
    # Dedup by slug, keep first (best) hit per paper + count
    seen: dict[str, dict[str, Any]] = {}
    hit_counts: dict[str, int] = {}
    for hit in hits:
        slug = (hit.get("paper") or {}).get("slug", "?")
        hit_counts[slug] = hit_counts.get(slug, 0) + 1
        if slug not in seen:
            seen[slug] = hit

    papers = list(seen.values())[:top_k]

    lines = [
        f'{len(papers)} paper{"s" if len(papers) != 1 else ""} for "{query_display}"',
        "slug | title | snippet (✦=generated summary) | hits",
    ]

    for hit in papers:
        paper_info = hit.get("paper") or {}
        slug = paper_info.get("slug", "?")
        title = _truncate(paper_info.get("title", ""), 50)
        count = hit_counts.get(slug, 1)

        # Snippet: prefer paper_summary, fall back to hit text
        summary = _get_paper_summary(_get_store(), slug)
        if summary:
            snippet = "✦ " + _truncate(summary, 100)
        else:
            snippet = _truncate(hit.get("text", ""), 100)

        count_str = f"{count} hit{'s' if count != 1 else ''}"
        lines.append(f"{slug} | {title} | {snippet} | {count_str}")

    # Hints
    lines.append("")
    lines.append("Next:")
    top_slug = (papers[0].get("paper") or {}).get("slug") if papers else None
    if top_slug:
        lines.append(f"{_T}paper('slug:{top_slug}/abstract') — read abstract")
        lines.append(f"{_T}paper('slug:{top_slug}/toc') — browse structure")
    lines.append(
        f"{_T}search('{_truncate(query, 40)}', style='chunk') — see raw matched passages"
    )
    lines.append(f"{_T}search('{_truncate(query, 40)}', top_k={top_k + 5}) — broaden")

    return "\n".join(lines)


def _format_chunk_results(
    hits: list[dict[str, Any]],
    query_display: str,
    query: str,
    top_k: int,
) -> str:
    """Chunk mode: raw matched passages, one per hit."""
    lines = [
        f'{len(hits)} hit{"s" if len(hits) != 1 else ""} for "{query_display}"',
        "slug#index (page) | title | snippet (✦=generated)",
    ]

    for hit in hits:
        paper_info = hit.get("paper") or {}
        slug = paper_info.get("slug", "?")
        title = _truncate(paper_info.get("title", ""), 50)
        meta = hit.get("metadata", {})
        bi = meta.get("block_index")
        page = meta.get("page")
        text = _truncate(hit.get("text", ""), 100)
        bt = meta.get("block_type", meta.get("type", "text"))
        prov = "✦ " if bt in ("paper_summary", "block_summary") else ""

        chunk_ref = f"{slug}#{bi}" if bi is not None else slug
        page_str = f" (p{page})" if page else ""
        lines.append(f"{chunk_ref}{page_str} | {title} | {prov}{text}")

    # Hints
    lines.append("")
    lines.append("Next:")
    top_hit = hits[0] if hits else None
    if top_hit:
        top_slug = (top_hit.get("paper") or {}).get("slug")
        top_bi = (top_hit.get("metadata") or {}).get("block_index")
        if top_slug:
            if top_bi is not None:
                lines.append(f"{_T}paper('slug:{top_slug}#{top_bi}') — read this block")
            lines.append(f"{_T}paper('slug:{top_slug}/toc') — browse structure")
    lines.append(
        f"{_T}search('{_truncate(query, 40)}', style='summary') — see paper summaries"
    )
    lines.append(f"{_T}search('{_truncate(query, 40)}', top_k={top_k + 5}) — broaden")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# note() tool
# ---------------------------------------------------------------------------


def note(
    id: str,
    content: str = "",
    title: str = "",
    tags: list[str] | None = None,
    delete: bool = False,
) -> str:
    """Annotate papers with your own notes — attach to whole papers or specific passages.

    Args:
        id: URI target — scheme:ident (paper-level), scheme:ident#N (block-level),
            or note:N (existing note by id).
        content: Note text. If provided → write/update. If empty → read.
        title: Optional note title.
        tags: Optional tags list.
        delete: If True → delete the note.
    """
    store = _get_store()
    uri = parse(id)

    # --- note:N → specific note by id ---
    if uri.scheme == "note":
        note_id = int(uri.ident)
        if delete:
            ok = store.delete_note(note_id)
            return f"Deleted note {note_id}: {'ok' if ok else 'not found'}"
        if content:
            ok = store.update_note(
                note_id, content=content, title=title or None, tags=tags
            )
            hints = [
                f"{_T}note('note:{note_id}') — read this note",
                f"{_T}note('note:{note_id}', delete=True) — delete",
            ]
            return f"Updated note {note_id}: {'ok' if ok else 'not found'}" + _format_hints(hints)
        # Read single note by id
        all_notes = store.get_notes()
        found = [n for n in all_notes if n.get("id") == note_id]
        if found:
            n = found[0]
            body = f"[{n.get('id')}] {n.get('content', '')}"
        else:
            body = f"Note {note_id} not found"
        hints = [
            f"{_T}note('note:{note_id}', content='...') — update",
            f"{_T}note('note:{note_id}', delete=True) — delete",
        ]
        return body + _format_hints(hints)

    # Resolve paper
    ident = _resolve_identifier(store, uri)
    paper_dict = store.get(ident)
    if paper_dict is None:
        hints = [f"{_T}search('...') — try searching"]
        return f"Not found: {id}" + _format_hints(hints)

    ref_id = paper_dict.get("ref_id") or paper_dict.get("id")
    bid = _base_id(uri)
    slug = paper_dict.get("slug", "")
    hint_id = f"slug:{slug}" if slug else bid

    # Determine if block-level (chunk/N specified)
    block_node_id = None
    if uri.view == "chunk" and uri.range_start is not None:
        blocks = store.get_blocks(ident, block_type="text")
        target = [b for b in blocks if b.get("block_index") == uri.range_start]
        if target:
            block_node_id = target[0]["node_id"]
        else:
            return f"Chunk {uri.range_start} not found"

    # --- delete ---
    if delete:
        if block_node_id:
            notes = store.get_notes(block_node_id=block_node_id)
            for n in notes:
                store.delete_note(n["id"])
            return f"Deleted {len(notes)} note(s)"
        else:
            notes = store.get_notes(ref_id=ref_id)
            for n in notes:
                store.delete_note(n["id"])
            return f"Deleted {len(notes)} note(s)"

    # --- write ---
    if content:
        if block_node_id:
            nid = store.add_note(
                content, block_node_id=block_node_id, title=title or None, tags=tags
            )
        else:
            nid = store.add_note(content, ref_id=ref_id, title=title or None, tags=tags)
        hints = [
            f"{_T}paper('{hint_id}/notes') — read all notes",
            f"{_T}note('note:{nid}', delete=True) — delete this note",
        ]
        return f"Note {nid} created" + _format_hints(hints)

    # --- read ---
    if block_node_id:
        notes = store.get_notes(block_node_id=block_node_id)
    else:
        notes = store.get_notes(ref_id=ref_id)

    if notes:
        note_lines = [f"[{n.get('id')}] {n.get('content', '')}" for n in notes]
        body = f"{len(notes)} note(s) for {hint_id}\n" + "\n".join(note_lines)
    else:
        body = f"No notes for {hint_id}"

    hints = [
        f"{_T}note('{hint_id}', content='...') — add a note",
        f"{_T}paper('{hint_id}') — view paper",
    ]
    for n in notes:
        nid = n.get("id")
        hints.append(f"{_T}note('note:{nid}', content='...') — edit note {nid}")
        hints.append(f"{_T}note('note:{nid}', delete=True) — delete note {nid}")
    return body + _format_hints(hints)
