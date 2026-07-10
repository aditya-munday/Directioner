"""Built-in web search tool.

Uses DuckDuckGo's public instant-answer endpoint to return lightweight web
results without requiring API credentials.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .registry import ToolSpec

_SEARCH_ENDPOINT = "https://api.duckduckgo.com/"
_DEFAULT_TIMEOUT_SECONDS = 8.0
_MAX_RESULTS = 8


class WebSearchToolError(ValueError):
    """Raised when search input is invalid or the HTTP request fails."""


def _extract_results(payload: dict[str, Any], max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    abstract = payload.get("AbstractText")
    abstract_url = payload.get("AbstractURL")
    if isinstance(abstract, str) and abstract.strip():
        results.append(
            {
                "title": str(payload.get("Heading") or "Instant answer"),
                "url": str(abstract_url or ""),
                "snippet": abstract.strip(),
            }
        )

    related = payload.get("RelatedTopics")
    if isinstance(related, list):
        for item in related:
            if len(results) >= max_results:
                break
            if not isinstance(item, dict):
                continue

            # DuckDuckGo can nest topic groups inside {"Name": ..., "Topics": [...]}.
            nested = item.get("Topics")
            if isinstance(nested, list):
                for sub_item in nested:
                    if len(results) >= max_results:
                        break
                    parsed = _parse_related_topic(sub_item)
                    if parsed is not None:
                        results.append(parsed)
                continue

            parsed = _parse_related_topic(item)
            if parsed is not None:
                results.append(parsed)

    return results[:max_results]


def _parse_related_topic(item: dict[str, Any]) -> dict[str, str] | None:
    text = item.get("Text")
    url = item.get("FirstURL")
    if not isinstance(text, str) or not text.strip():
        return None
    return {
        "title": text.split(" - ", 1)[0].strip() or "Result",
        "url": str(url or ""),
        "snippet": text.strip(),
    }


async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise WebSearchToolError("A non-empty string 'query' argument is required")

    requested_limit = arguments.get("max_results", 5)
    if not isinstance(requested_limit, int):
        raise WebSearchToolError("'max_results' must be an integer")
    max_results = max(1, min(requested_limit, _MAX_RESULTS))

    params = urlencode(
        {
            "q": query.strip(),
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
            "no_redirect": "1",
        }
    )
    url = f"{_SEARCH_ENDPOINT}?{params}"

    try:
        with urlopen(url, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network/runtime branch
        raise WebSearchToolError(f"Search request failed: {exc}") from exc

    if not isinstance(data, dict):
        raise WebSearchToolError("Unexpected search response payload")

    return {
        "query": query.strip(),
        "results": _extract_results(data, max_results),
    }


def web_search_tool() -> ToolSpec:
    """Return a built-in web search tool."""

    return ToolSpec(
        name="web_search",
        description=(
            "Search the public web for recent information and return short result "
            "snippets with URLs. Arguments: query, optional max_results."
        ),
        handler=_handle,
    )
