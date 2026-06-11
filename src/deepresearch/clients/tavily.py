from typing import Protocol

from tavily import TavilyClient

from deepresearch.errors import SearchError
from deepresearch.state import SearchResult


class SearchClient(Protocol):
    def search(self, query: str, *, subquestion_id: str, max_results: int) -> list[SearchResult]:
        ...


class TavilySearchClient:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, *, subquestion_id: str, max_results: int) -> list[SearchResult]:
        try:
            response = self._client.search(query=query, max_results=max_results)
            items = response.get("results", [])
            return [
                SearchResult(
                    subquestion_id=subquestion_id,
                    title=item.get("title") or "Untitled",
                    url=item.get("url") or "",
                    content=item.get("content") or "",
                    score=item.get("score"),
                    published_date=item.get("published_date"),
                )
                for item in items
                if item.get("url")
            ]
        except Exception as exc:
            raise SearchError(str(exc)) from exc
