"""CSP helpers for legacy inline HTML attributes.

The application authorizes inline ``style=`` and ``on*=`` attributes by their
per-response SHA-256 hashes instead of enabling blanket ``'unsafe-inline'``.
A newly injected attribute therefore has no matching hash and remains blocked.
"""
from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser


_MAX_ATTRIBUTE_LENGTH = 4096
_MAX_UNIQUE_ATTRIBUTES = 256


class _InlineAttributeCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_attributes: set[str] = set()
        self.style_attributes: set[str] = set()
        self.overflow = False

    def _collect(self, attrs: list[tuple[str, str | None]]) -> None:
        for raw_name, value in attrs:
            if value is None:
                continue
            name = raw_name.lower()
            target = None
            if name == "style":
                target = self.style_attributes
            elif name.startswith("on"):
                target = self.script_attributes
            if target is None:
                continue
            if len(value) > _MAX_ATTRIBUTE_LENGTH:
                self.overflow = True
                continue
            target.add(value)
            if len(target) > _MAX_UNIQUE_ATTRIBUTES:
                self.overflow = True

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(attrs)

    def handle_startendtag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(attrs)


def _hash_source(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("ascii")
    return f"'sha256-{encoded}'"


def _directive(name: str, values: set[str], *, overflow: bool) -> str:
    if overflow or not values:
        return f"{name} 'none'"
    hashes = " ".join(sorted(_hash_source(value) for value in values))
    return f"{name} 'unsafe-hashes' {hashes}"


def inline_attribute_directives(html: str) -> tuple[str, str]:
    """Return strict ``style-src-attr`` and ``script-src-attr`` directives.

    ``HTMLParser`` supplies decoded DOM attribute values, which are the values
    CSP hashes. If parsing or bounded collection ever fails, both directives
    fail closed with ``'none'`` rather than falling back to ``unsafe-inline``.
    """
    collector = _InlineAttributeCollector()
    try:
        collector.feed(html)
        collector.close()
    except (TypeError, ValueError):
        return "style-src-attr 'none'", "script-src-attr 'none'"
    return (
        _directive(
            "style-src-attr",
            collector.style_attributes,
            overflow=collector.overflow,
        ),
        _directive(
            "script-src-attr",
            collector.script_attributes,
            overflow=collector.overflow,
        ),
    )
