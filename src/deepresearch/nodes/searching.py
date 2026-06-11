from deepresearch.clients.tavily import SearchClient
from deepresearch.errors import SearchError
from deepresearch.state import ResearchState, SearchResult


def make_search_web_node(search_client: SearchClient, results_per_query: int):
    def search_web(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        results: list[SearchResult] = []
        for subquestion in state.get("subquestions", []):
            try:
                results.extend(
                    search_client.search(
                        subquestion.search_query,
                        subquestion_id=subquestion.id,
                        max_results=results_per_query,
                    )
                )
            except SearchError as exc:
                errors.append(f"Search failed for {subquestion.id}: {exc}")

        if not results:
            raise SearchError("All searches failed or returned no usable results")
        return {**state, "search_results": results, "errors": errors}

    return search_web
