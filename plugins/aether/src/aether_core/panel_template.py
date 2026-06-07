"""Loader for the Aether panel HTML template.

The actual markup lives in :mod:`aether_core.panel.index_html` so editors
can syntax-highlight it and ``git diff`` reviews do not have to wade
through a multi-thousand-line Python raw string. This module exposes the
same ``PANEL_HTML`` constant that downstream code (``panel.py``,
``panel_server.py``) imports, so callers do not need to change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_PANEL_DIR = Path(__file__).parent / "panel"
_PANEL_INDEX = _PANEL_DIR / "index.html"


@lru_cache(maxsize=1)
def _load_panel_html() -> str:
    """Read ``panel/index.html`` from disk and cache the result.

    Caching the read keeps ``PanelRequestHandler.do_GET`` cheap and
    avoids re-parsing the file on every panel refresh. Tests that need
    to inject custom markup should call :func:`load_panel_html` with
    ``use_cache=False``.
    """
    return _PANEL_INDEX.read_text(encoding="utf-8")


def load_panel_html(*, use_cache: bool = True) -> str:
    """Return the panel HTML, optionally bypassing the module-level cache."""
    if use_cache:
        return _load_panel_html()
    return _PANEL_INDEX.read_text(encoding="utf-8")


def panel_html_path() -> Path:
    """Return the absolute path of the panel HTML file (for tooling/tests)."""
    return _PANEL_INDEX


PANEL_HTML = load_panel_html()


__all__ = ["PANEL_HTML", "load_panel_html", "panel_html_path"]
