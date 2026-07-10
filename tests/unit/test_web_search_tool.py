from __future__ import annotations

import json

import pytest

from directioner.tools.web_search import WebSearchToolError, web_search_tool


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb


@pytest.mark.asyncio
async def test_web_search_tool_requires_query() -> None:
    spec = web_search_tool()
    with pytest.raises(WebSearchToolError):
        await spec.handler({"query": ""})


@pytest.mark.asyncio
async def test_web_search_tool_parses_results(monkeypatch) -> None:
    def fake_urlopen(url: str, timeout: float):  # noqa: ANN001
        _ = url, timeout
        return _FakeResponse(
            {
                "Heading": "Directioner",
                "AbstractText": "Directioner is an assistant.",
                "AbstractURL": "https://example.com/abstract",
                "RelatedTopics": [
                    {
                        "Text": "Directioner docs - Project documentation",
                        "FirstURL": "https://example.com/docs",
                    }
                ],
            }
        )

    monkeypatch.setattr("directioner.tools.web_search.urlopen", fake_urlopen)
    spec = web_search_tool()

    result = await spec.handler({"query": "directioner", "max_results": 2})

    assert result["query"] == "directioner"
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "Directioner"
    assert result["results"][1]["url"] == "https://example.com/docs"
