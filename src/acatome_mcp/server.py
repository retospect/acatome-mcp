"""MCP server for acatome.

Three tools:
  ``paper``  — read paper content via URI addressing
  ``search`` — semantic search with provenance
  ``note``   — read / write / delete user notes
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from acatome_mcp import tools

mcp = FastMCP("acatome")


@mcp.tool()
def paper(id: str, filter: str = "", page: int = 1) -> str:
    """Read paper content via URI addressing.

    id format: scheme:identifier[#chunk][/view][/summary][/notes]
      Schemes: slug, doi, arxiv, s2, ref
      Views: meta, abstract, summary, toc, page, fig
      #N selects chunk N, #N-M for range, #N- for open range (next 10)

    Examples:
      slug:smith2024quantum          — overview + hints
      slug:smith2024quantum/abstract — abstract text
      slug:smith2024quantum/toc      — table of contents with summaries
      slug:smith2024quantum#38       — chunk 38 full text
      slug:smith2024quantum#38-42    — chunks 38–42
      slug:smith2024quantum#38-      — chunks 38+, paginated
      slug:smith2024quantum#38/summary — chunk 38 enrichment summary
      slug:smith2024quantum/summary  — paper-level summary
      doi:10.1038/s41567-024-1234-5/toc — via DOI

    filter: case-insensitive substring match on block text
    page: result page (1-indexed) for filtered results
    """
    return tools.paper(id=id, filter=filter, page=page)


@mcp.tool()
def search(
    query: str,
    top_k: int = 5,
    kinds: list[str] | None = None,
    scope: str = "",
    year: str = "",
    style: str = "summary",
) -> str:
    """Semantic search over stored papers.

    query: natural language search query
    top_k: number of results (default 5)
    kinds: optional block_type filter, e.g. ["text"], ["abstract"]
    scope: comma-separated slugs or DOIs to restrict search to
    year: year filter — "2020" (exact), "-2020" (up to), "2020-" (from),
          "2020-2022" (range)
    style: "summary" (default) — one line per paper, deduped, with generated
           summary. "chunk" — raw matched passages, one per hit.

    Returns compact one-line-per-result format.
    Use paper(slug/abstract) or paper(slug/toc) to drill deeper.
    """
    return tools.search(
        query=query, top_k=top_k, kinds=kinds, scope=scope, year=year, style=style
    )


@mcp.tool()
def note(
    id: str,
    content: str = "",
    title: str = "",
    tags: list[str] | None = None,
    delete: bool = False,
) -> str:
    """Read, write, or delete notes on papers or blocks.

    id: URI target (same scheme as paper tool)
      slug:smith2024quantum           — paper-level note
      slug:smith2024quantum#4         — block-level note
      note:42                         — specific note by id

    content provided → write (creates new note)
    content empty    → read notes
    delete=True      → delete note(s)
    """
    return tools.note(id=id, content=content, title=title, tags=tags, delete=delete)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
