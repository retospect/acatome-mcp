"""acatome-mcp — DEPRECATED. Use precis-mcp instead."""

import warnings

__version__ = "0.4.0"

warnings.warn(
    "acatome-mcp is deprecated. Use precis-mcp instead: pip install precis-mcp",
    DeprecationWarning,
    stacklevel=2,
)
