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
def paper(id: str, filter: str = "", page: int = 1) -> dict:
    """Read paper content via URI addressing.

    id format: scheme:identifier[/view[/range]]
      Schemes: slug, doi, arxiv, s2, ref
      Views: meta, abstract, summary, toc, chunk, page, fig
      Range: N (single), N-M (closed), N- (open, next 10)

    Examples:
      slug:smith2024quantum          — overview + hints
      slug:smith2024quantum/abstract — abstract text
      slug:smith2024quantum/toc      — summaries of each block
      slug:smith2024quantum/chunk    — first 10 text chunks
      slug:smith2024quantum/chunk/4  — single chunk
      slug:smith2024quantum/chunk/11- — chunks 11-20
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
) -> dict:
    """Semantic search over stored papers.

    query: natural language search query
    top_k: number of results (default 5)
    kinds: optional block_type filter, e.g. ["text"], ["abstract"]
    scope: comma-separated slugs or DOIs to restrict search to
           e.g. "zimmerman2016engineering" or "zimmerman2016engineering,smith2024quantum"

    Results include provenance (original vs generated).
    """
    return tools.search(query=query, top_k=top_k, kinds=kinds, scope=scope)


@mcp.tool()
def note(
    id: str,
    content: str = "",
    title: str = "",
    tags: list[str] | None = None,
    delete: bool = False,
) -> dict:
    """Read, write, or delete notes on papers or blocks.

    id: URI target (same scheme as paper tool)
      slug:smith2024quantum           — paper-level note
      slug:smith2024quantum/chunk/4   — block-level note
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
