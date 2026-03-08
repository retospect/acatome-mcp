# acatome-mcp

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that exposes the acatome paper library to LLMs. Provides tools for reading papers, searching the library, and managing notes.

## Features

- **3 tools** — `paper`, `search`, `notes`
- **URI addressing** — `slug:`, `doi:`, `arxiv:`, `s2:` schemes with view routing
- **Paginated views** — toc, chunk, page, figure, abstract, summary
- **Semantic search** — query across all ingested papers
- **Notes CRUD** — annotate papers, chunks, and figures
- **Supplement support** — scoped views for supplementary materials

## Installation

```bash
uv pip install -e .
```

## Usage

Run as an MCP server:

```bash
acatome-mcp
```

## URI Examples

```
slug:abc12                    # paper overview
slug:abc12/toc                # table of contents
slug:abc12/chunk/5            # block 5
doi:10.1234/paper/abstract    # abstract by DOI
slug:abc12/notes              # all notes on paper
slug:abc12/supplement/s1/toc  # supplement TOC
```

## Dependencies

- **acatome-store** — paper storage and search backend

## Testing

```bash
uv run python -m pytest tests/ -v
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
