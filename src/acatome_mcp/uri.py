"""URI parser for acatome MCP tool addressing.

Grammar::

    id     := scheme ":" ident [ "#" chunk_range ] [ "/supplement/" name ]
              [ "/" view ] [ "/summary" ] [ "/notes" ]
    view   := "meta" | "abstract" | "toc" | "page" [ "/" range ]
            | "fig" [ "/" range ] | "summary"
    chunk_range := INT | INT ".." INT | INT ".."
    range  := INT | INT ".." INT | INT ".."
    scheme := "slug" | "doi" | "arxiv" | "s2" | "ref" | "note"

Trailing modifiers ``/summary`` and ``/notes`` are stripped early and set
boolean flags on ParsedURI. They can follow any view path or stand alone.

``#N`` is the canonical chunk addressing syntax. ``/chunk/N`` is accepted
as an alias for backward compatibility.

Examples::

    slug:smith2024quantum              -- default overview
    slug:smith2024quantum/abstract     -- abstract
    slug:smith2024quantum#38           -- chunk 38 full text
    slug:smith2024quantum#38..42       -- chunks 38–42
    slug:smith2024quantum#38..          -- chunks 38+, paginated
    slug:smith2024quantum#38/summary   -- chunk 38 enrichment summary
    slug:smith2024quantum/summary      -- paper-level summary
    slug:smith2024quantum/toc          -- table of contents
    slug:smith2024quantum#38/notes     -- block-level notes
    slug:smith2024quantum/notes        -- paper-level notes
    slug:smith2024quantum/supplement/s1        -- supplement overview
    slug:smith2024quantum/supplement/s1#4      -- supplement chunk
    doi:10.1038/s41567-024-1234-5/toc
    ref:42/page/3
    note:42
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

PAGE_SIZE = 10

SCHEMES = {"slug", "doi", "arxiv", "s2", "ref", "note"}
VIEWS = {"meta", "abstract", "summary", "toc", "chunk", "page", "fig"}


@dataclass
class ParsedURI:
    scheme: str
    ident: str
    view: str = ""  # empty = default view
    range_start: Optional[int] = None
    range_end: Optional[int] = None  # None with range_start set = open range
    notes: bool = False  # trailing /notes modifier
    summary: bool = False  # trailing /summary modifier
    supplement: str | None = None  # /supplement/{name} segment
    raw: str = ""

    @property
    def is_single(self) -> bool:
        """True if range selects exactly one item."""
        return self.range_start is not None and self.range_start == self.range_end

    @property
    def has_range(self) -> bool:
        return self.range_start is not None

    @property
    def is_open_range(self) -> bool:
        """True for '11-' style (start set, end is None)."""
        return self.range_start is not None and self.range_end is None


# DOIs always start with 10.NNNN/ — used to detect where the DOI ends
# and a view path begins.
_DOI_PREFIX = re.compile(r"^10\.\d{4,}/")

# Matches #N, #N-M, #N- at any position
_CHUNK_HASH = re.compile(r"#(\d+(?:\.\.\d*)?)")


def _parse_range(raw: str) -> tuple[Optional[int], Optional[int]]:
    """Parse range string: '4', '4..6', '11..'."""
    if not raw:
        return None, None
    if ".." in raw:
        left, _, right = raw.partition("..")
        start = int(left)
        end = int(right) if right else None
        return start, end
    return int(raw), int(raw)


def _split_doi_path(rest: str) -> tuple[str, str]:
    """Split '10.1038/s41567-024-1234-5/toc' into DOI + view path.

    DOIs contain '/' so we can't naively split. Instead, we try
    removing known view keywords from the end.
    """
    # Try stripping /view or /view/range from the end
    parts = rest.rsplit("/", 2)
    if len(parts) >= 2 and parts[-2] in VIEWS:
        # e.g. ['10.1038/s41567', 'page', '3']
        ident = "/".join(parts[:-2])
        view_path = "/".join(parts[-2:])
        return ident, view_path
    if len(parts) >= 2 and parts[-1] in VIEWS:
        # e.g. ['10.1038/s41567-024-1234-5', 'toc']
        return "/".join(parts[:-1]), parts[-1]
    # No view found — entire rest is the DOI
    return rest, ""


def parse(raw: str) -> ParsedURI:
    """Parse a URI string into a ParsedURI.

    Raises ValueError on invalid input.
    """
    if ":" not in raw:
        raise ValueError(f"Missing scheme in URI: {raw!r}")

    scheme, _, rest = raw.partition(":")
    scheme = scheme.lower()
    if scheme not in SCHEMES:
        raise ValueError(f"Unknown scheme {scheme!r}, expected one of {SCHEMES}")

    if not rest:
        raise ValueError(f"Empty identifier in URI: {raw!r}")

    # Strip trailing /notes modifier early (before DOI path splitting)
    notes = False
    if rest.endswith("/notes"):
        notes = True
        rest = rest[: -len("/notes")]

    # Strip trailing /summary modifier early (before DOI path splitting)
    summary_flag = False
    if rest.endswith("/summary"):
        # Distinguish: slug:x/summary (paper-level view) vs slug:x#38/summary (modifier)
        # If there's a #N before /summary, it's a modifier on chunks
        # If there's no #N, it might be the paper-level summary view
        # We'll handle this after parsing #N below
        summary_flag = True
        rest = rest[: -len("/summary")]

    if not rest:
        raise ValueError(f"Empty identifier in URI: {raw!r}")

    # Extract #N chunk range early (before supplement and DOI path splitting)
    chunk_range_str = ""
    chunk_match = _CHUNK_HASH.search(rest)
    if chunk_match:
        chunk_range_str = chunk_match.group(1)
        rest = rest[: chunk_match.start()] + rest[chunk_match.end() :]

    # Strip /supplement/{name} early (before DOI path splitting)
    supplement = None
    supp_marker = "/supplement/"
    supp_idx = rest.find(supp_marker)
    if supp_idx != -1:
        after_marker = rest[supp_idx + len(supp_marker) :]
        # supplement name is the next path segment
        if "/" in after_marker:
            supplement, _, remaining = after_marker.partition("/")
            rest = rest[:supp_idx] + "/" + remaining
        else:
            supplement = after_marker
            rest = rest[:supp_idx]
        supplement = supplement.lower()
        if not supplement:
            raise ValueError(f"Empty supplement name in URI: {raw!r}")

    if not rest:
        raise ValueError(f"Empty identifier in URI: {raw!r}")

    # DOI special case: identifier contains '/'
    if scheme == "doi":
        ident, view_path = _split_doi_path(rest)
    else:
        # For other schemes, first '/' starts the view path
        if "/" in rest:
            ident, _, view_path = rest.partition("/")
        else:
            ident = rest
            view_path = ""

    # Parse view + optional range from view_path
    view = ""
    range_str = ""
    if view_path:
        vparts = view_path.split("/")
        if vparts[0] in VIEWS:
            view = vparts[0]
            range_str = vparts[1] if len(vparts) > 1 else ""
        else:
            raise ValueError(
                f"Unknown view {vparts[0]!r} in URI: {raw!r}. "
                f"Expected one of {VIEWS}"
            )

    # Handle #N chunk addressing — sets view=chunk and range
    if chunk_range_str:
        if view and view != "chunk":
            raise ValueError(
                f"Cannot combine #N chunk address with /{view} view in: {raw!r}"
            )
        view = "chunk"
        range_str = chunk_range_str

    # Handle /chunk/N alias (backward compat) — already parsed as view=chunk + range_str

    # Handle /summary: if summary_flag was set and there's no chunk address,
    # treat it as the paper-level summary view. If there IS a chunk address,
    # it's a modifier flag (show enrichment summary instead of text).
    summary = False
    if summary_flag:
        if view == "chunk":
            # slug:x#38/summary — modifier on chunk
            summary = True
        elif not view:
            # slug:x/summary — paper-level summary view
            view = "summary"
        else:
            # slug:x/toc/summary or similar — treat as modifier
            summary = True

    range_start, range_end = _parse_range(range_str)

    return ParsedURI(
        scheme=scheme,
        ident=ident,
        view=view,
        range_start=range_start,
        range_end=range_end,
        notes=notes,
        summary=summary,
        supplement=supplement,
        raw=raw,
    )
