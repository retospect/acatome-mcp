"""MCP tool implementations for acatome.

Three tools:
  ``paper``  — read paper content via URI addressing
  ``search`` — semantic search with provenance
  ``note``   — read / write / delete user notes
"""

from __future__ import annotations

from typing import Any

from acatome_store.store import Store

from acatome_mcp.uri import PAGE_SIZE, ParsedURI, parse

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


def _make_hint(base_id: str, suffix: str, filter_str: str = "") -> str:
    """Build a hint string for the next action."""
    call = f"paper('{base_id}{suffix}'"
    if filter_str:
        call += f", filter='{filter_str}'"
    call += ")"
    return call


def _base_id(uri: ParsedURI) -> str:
    """Reconstruct scheme:ident portion."""
    return f"{uri.scheme}:{uri.ident}"


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


def paper(id: str, filter: str = "", page: int = 1) -> dict[str, Any]:
    """Read paper content via URI addressing.

    Args:
        id: URI — scheme:identifier[/view[/range]]
            Schemes: slug, doi, arxiv, s2, ref
            Views: meta, abstract, summary, toc, chunk, page, fig
            Range: N, N-M, N- (open)
        filter: Case-insensitive substring match on block text.
        page: Result page (1-indexed) for filtered results.

    Returns:
        Dict with view-specific data + hints for next actions.
    """
    uri = parse(id)
    store = _get_store()
    ident = _resolve_identifier(store, uri)
    bid = _base_id(uri)

    paper_dict = store.get(ident)
    if paper_dict is None:
        return {
            "error": f"Paper not found: {id}",
            "hints": ["search('your query') — try searching"],
        }

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
                return {"error": f"Chunk {uri.range_start} not found"}
        if block_node_id:
            notes = store.get_notes(block_node_id=block_node_id)
        else:
            notes = store.get_notes(ref_id=ref_id)
        hints = [
            f"note('{hint_id}', content='...') — add a note",
            f"paper('{hint_id}') — view paper",
        ]
        for n in notes:
            nid = n.get("id")
            hints.append(f"note('note:{nid}', content='...') — edit note {nid}")
            hints.append(f"note('note:{nid}', delete=True) — delete note {nid}")
        return {"notes": notes, "hints": hints}

    # --- meta ---
    if view == "meta":
        return {
            "meta": _clean_meta(paper_dict),
            "hints": [
                f"paper('{hint_id}/abstract') — read abstract",
                f"paper('{hint_id}/toc') — browse structure",
                f"paper('{hint_id}/notes') — read notes",
            ],
        }

    # --- abstract ---
    if view == "abstract":
        blocks = store.get_blocks(ident, block_type="abstract", supplement=supp)
        text = blocks[0]["text"] if blocks else None
        return {
            "abstract": text,
            "hints": [
                f"paper('{hint_id}/toc') — browse structure",
                f"paper('{hint_id}/chunk') — read chunks",
                f"search('{(text or '')[:40]}') — find related",
            ],
        }

    # --- summary ---
    if view == "summary":
        blocks = store.get_blocks(ident, block_type="paper_summary", supplement=supp)
        text = blocks[0]["text"] if blocks else None
        provenance = "generated" if text else None
        return {
            "summary": text,
            "provenance": provenance,
            "hints": [
                f"paper('{hint_id}/abstract') — original abstract",
                f"paper('{hint_id}/toc') — browse structure",
            ],
        }

    # --- toc ---
    if view == "toc":
        toc = store.get_toc(ident, supplement=supp)
        toc = _filter_items(toc, filter, fields=("preview", "section_path"))
        items, total, has_more = _paginate(toc, page)
        _annotate_note_counts(items, store, ref_id)
        hints = []
        if has_more:
            hints.append(
                _make_hint(hint_id, "/toc", filter) + f" page={page + 1} — more entries"
            )
        hints.append(f"paper('{hint_id}/chunk/N') — read specific chunk")
        return {"items": items, "total": total, "page": page, "hints": hints}

    # --- chunk ---
    if view == "chunk":
        all_blocks = store.get_blocks(ident, block_type="text", supplement=supp)
        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="block_index")
            _annotate_note_counts(items, store, ref_id)
            hints = []
            if uri.is_open_range and len(items) == PAGE_SIZE:
                next_start = uri.range_start + PAGE_SIZE
                hints.append(_make_hint(hint_id, f"/chunk/{next_start}-", filter))
            if not uri.is_single and items:
                hints.append(f"note('{hint_id}/chunk/N', content='...') — annotate")
            # Add note hints for items with notes
            for item in items:
                if item.get("note_count"):
                    bi = item.get("block_index")
                    hints.append(
                        f"paper('{hint_id}/chunk/{bi}/notes') — {item['note_count']} note(s)"
                    )
            return {"items": items, "total": len(all_blocks), "hints": hints}
        else:
            # No range: filter + paginate
            filtered = _filter_items(all_blocks, filter)
            items, total, has_more = _paginate(filtered, page)
            _annotate_note_counts(items, store, ref_id)
            hints = []
            if has_more:
                h = f"paper('{hint_id}/chunk'"
                if filter:
                    h += f", filter='{filter}'"
                h += f", page={page + 1}) — next {PAGE_SIZE}"
                hints.append(h)
            hints.append(f"note('{hint_id}/chunk/N', content='...') — annotate")
            # Add note hints for items with notes
            for item in items:
                if item.get("note_count"):
                    bi = item.get("block_index")
                    hints.append(
                        f"paper('{hint_id}/chunk/{bi}/notes') — {item['note_count']} note(s)"
                    )
            return {"items": items, "total": total, "page": page, "hints": hints}

    # --- page ---
    if view == "page":
        all_blocks = store.get_blocks(ident, supplement=supp)
        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="page")
            items = _filter_items(items, filter)
            hints = []
            if uri.is_open_range and len(items) == PAGE_SIZE:
                next_start = uri.range_start + PAGE_SIZE
                hints.append(_make_hint(hint_id, f"/page/{next_start}-", filter))
            return {"items": items, "total": len(all_blocks), "hints": hints}
        else:
            return {"error": "page view requires a range, e.g. /page/3 or /page/2-4"}

    # --- fig (future) ---
    if view == "fig":
        all_blocks = store.get_blocks(ident, block_type="figure", supplement=supp)
        if uri.has_range:
            items = _range_slice(all_blocks, uri, index_key="block_index")
        else:
            items = all_blocks[:PAGE_SIZE]
        return {"items": items, "total": len(all_blocks), "hints": []}

    # --- default view (no view specified) ---
    if supp:
        # Supplement overview
        all_blocks = store.get_blocks(ident, supplement=supp)
        page_count = max((b.get("page") or 0) for b in all_blocks) if all_blocks else 0
        return {
            "supplement": supp,
            "block_count": len(all_blocks),
            "page_count": page_count,
            "hints": [
                f"paper('{hint_id}{supp_prefix}/toc') — browse structure",
                f"paper('{hint_id}{supp_prefix}/chunk') — read chunks",
                f"paper('{hint_id}') — back to main paper",
            ],
        }

    abstract_blocks = store.get_blocks(ident, block_type="abstract")
    abstract_text = abstract_blocks[0]["text"] if abstract_blocks else None
    all_blocks = store.get_blocks(ident)
    page_count = max((b.get("page") or 0) for b in all_blocks) if all_blocks else 0
    has_summary = any(b["block_type"] == "paper_summary" for b in all_blocks)
    paper_notes = store.get_notes(ref_id=ref_id)
    supplements = store.get_supplements(ident)
    is_retracted = paper_dict.get("retracted", False)
    retraction_note = paper_dict.get("retraction_note", "")
    result: dict[str, Any] = {
        "meta": _clean_meta(paper_dict),
        "abstract": abstract_text,
        "block_count": len(all_blocks),
        "page_count": page_count,
        "has_summary": has_summary,
        "hints": [
            f"paper('{hint_id}/toc') — browse structure",
            f"paper('{hint_id}/chunk') — read first chunks",
            f"paper('{hint_id}/page/1') — read page 1",
            f"search('...') — find related content",
            f"note('{hint_id}', content='...') — add a note",
        ],
    }
    if is_retracted:
        warning = f"⚠ RETRACTED"
        if retraction_note:
            warning += f" — {retraction_note}"
        result["retracted"] = True
        result["retraction_note"] = retraction_note
        result["hints"].insert(0, warning)
    if supplements:
        result["supplement_count"] = len(supplements)
        for s in supplements:
            result["hints"].append(
                f"paper('{hint_id}/supplement/{s}') — supplement {s}"
            )
    if paper_notes:
        result["note_count"] = len(paper_notes)
        result["hints"].insert(
            0, f"paper('{hint_id}/notes') — {len(paper_notes)} note(s)"
        )
    return result


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


def search(
    query: str,
    top_k: int = 5,
    kinds: list[str] | None = None,
    scope: str = "",
) -> dict[str, Any]:
    """Semantic search over stored papers.

    Args:
        query: Natural language search query.
        top_k: Number of results to return.
        kinds: Optional block_type filter (e.g. ["text"], ["abstract"]).
        scope: Comma-separated slugs or DOIs to restrict search to.

    Returns:
        Dict with items (including provenance) and hints.
    """
    store = _get_store()
    where: dict[str, Any] = {}
    if kinds:
        where["block_type"] = {"$in": kinds} if len(kinds) > 1 else kinds[0]

    # Resolve scope to paper_id filter
    if scope:
        paper_ids = _resolve_scope(store, scope)
        if not paper_ids:
            return {
                "items": [],
                "hints": ["No papers matched the scope filter."],
            }
        where["paper_id"] = {"$in": paper_ids} if len(paper_ids) > 1 else paper_ids[0]

    hits = store.search_text(query, top_k=top_k, where=where or None)

    # Enrich with provenance
    for hit in hits:
        bt = hit.get("metadata", {}).get("block_type", "text")
        hit["block_type"] = bt
        hit["provenance"] = (
            "generated" if bt in ("paper_summary", "block_summary") else "original"
        )

    hints = []
    if hits:
        # Suggest drilling into top result
        top = hits[0]
        slug = (top.get("paper", {}) or {}).get("slug")
        if slug:
            hints.append(f"paper('slug:{slug}/toc') — browse top result")
            hints.append(f"paper('slug:{slug}/abstract') — read abstract")
    hints.append(f"search('{query}', top_k={top_k + 5}) — broaden search")

    return {"items": hits, "hints": hints}


# ---------------------------------------------------------------------------
# note() tool
# ---------------------------------------------------------------------------


def note(
    id: str,
    content: str = "",
    title: str = "",
    tags: list[str] | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Read, write, or delete notes on papers or blocks.

    Args:
        id: URI target — scheme:ident for paper-level,
            scheme:ident/chunk/N for block-level,
            note:N for a specific note by id.
        content: Note content. If provided → write.
                 If empty → read.
        title: Optional note title (write only).
        tags: Optional tags (write only).
        delete: If True → delete the note(s).

    Returns:
        Dict with notes or confirmation + hints.
    """
    store = _get_store()
    uri = parse(id)

    # --- note:N → specific note by id ---
    if uri.scheme == "note":
        note_id = int(uri.ident)
        if delete:
            ok = store.delete_note(note_id)
            return {"deleted": ok, "hints": []}
        if content:
            ok = store.update_note(
                note_id, content=content, title=title or None, tags=tags
            )
            return {
                "updated": ok,
                "hints": [
                    f"note('note:{note_id}') — read this note",
                    f"note('note:{note_id}', delete=True) — delete",
                ],
            }
        # Read single note by id
        all_notes = store.get_notes()
        found = [n for n in all_notes if n.get("id") == note_id]
        return {
            "notes": found,
            "hints": [
                f"note('note:{note_id}', content='...') — update",
                f"note('note:{note_id}', delete=True) — delete",
            ],
        }

    # Resolve paper
    ident = _resolve_identifier(store, uri)
    paper_dict = store.get(ident)
    if paper_dict is None:
        return {"error": f"Not found: {id}", "hints": ["search('...') — try searching"]}

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
            return {"error": f"Chunk {uri.range_start} not found"}

    # --- delete ---
    if delete:
        if block_node_id:
            notes = store.get_notes(block_node_id=block_node_id)
            for n in notes:
                store.delete_note(n["id"])
            return {"deleted": len(notes), "hints": []}
        else:
            notes = store.get_notes(ref_id=ref_id)
            for n in notes:
                store.delete_note(n["id"])
            return {"deleted": len(notes), "hints": []}

    # --- write ---
    if content:
        if block_node_id:
            nid = store.add_note(
                content, block_node_id=block_node_id, title=title or None, tags=tags
            )
        else:
            nid = store.add_note(content, ref_id=ref_id, title=title or None, tags=tags)
        return {
            "note_id": nid,
            "hints": [
                f"paper('{hint_id}/notes') — read all notes",
                f"note('note:{nid}', delete=True) — delete this note",
            ],
        }

    # --- read ---
    if block_node_id:
        notes = store.get_notes(block_node_id=block_node_id)
    else:
        notes = store.get_notes(ref_id=ref_id)

    hints = [
        f"note('{hint_id}', content='...') — add a note",
        f"paper('{hint_id}') — view paper",
    ]
    for n in notes:
        nid = n.get("id")
        hints.append(f"note('note:{nid}', content='...') — edit note {nid}")
        hints.append(f"note('note:{nid}', delete=True) — delete note {nid}")
    return {"notes": notes, "hints": hints}
