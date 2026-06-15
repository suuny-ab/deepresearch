import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from deepresearch.clients.tavily import SearchClient
from deepresearch.errors import SearchError
from deepresearch.state import ResearchState, SearchResult

_CHINESE_CHAR = re.compile(r"[一-鿿]")


def _queries_for(subquestion) -> list[str]:
    return subquestion.search_queries or [subquestion.search_query]


def _is_chinese_topic(question: str) -> bool:
    """Check if the research question is primarily in Chinese."""
    return bool(_CHINESE_CHAR.search(question))


def _skip_english_query(query: str) -> bool:
    """Skip a query if it's English-only on a Chinese topic (reduces ~30% Tavily calls)."""
    return not _CHINESE_CHAR.search(query)


def make_search_web_node(search_client: SearchClient, results_per_query: int):
    def search_web(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        results: list[SearchResult] = []
        subquestions = state.get("subquestions", [])
        question = state.get("question", "")
        chinese_topic = _is_chinese_topic(question)

        # Build flat list of (sq_id, query) tasks
        tasks = []
        for subquestion in subquestions:
            for query in _queries_for(subquestion):
                # Skip English-only queries on Chinese topics to save Tavily quota
                if chinese_topic and _skip_english_query(query):
                    continue
                tasks.append((subquestion.id, query))

        if not tasks:
            return {**state, "search_results": [], "errors": errors}

        if len(tasks) == 1:
            # Single search — no parallelism benefit
            sq_id, query = tasks[0]
            try:
                results.extend(search_client.search(query, subquestion_id=sq_id, max_results=results_per_query))
            except SearchError as exc:
                errors.append(f"Search failed for {sq_id}: {exc}")
        else:
            def _search_one(sq_id, query):
                thread_errors: list[str] = []
                try:
                    return search_client.search(query, subquestion_id=sq_id, max_results=results_per_query), thread_errors
                except SearchError as exc:
                    thread_errors.append(f"Search failed for {sq_id}: {exc}")
                    return [], thread_errors

            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = {executor.submit(_search_one, sq_id, query): (sq_id, query) for sq_id, query in tasks}
                for future in as_completed(futures):
                    batch, thread_errors = future.result()
                    results.extend(batch)
                    errors.extend(thread_errors)

        if not results:
            raise SearchError("All searches failed or returned no usable results")
        return {**state, "search_results": results, "errors": errors}

    return search_web
