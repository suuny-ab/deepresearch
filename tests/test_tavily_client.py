from deepresearch.clients.tavily import TavilySearchClient


class FakeTavilySDK:
    def __init__(self):
        self.search_calls = []
        self.extract_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {
            "results": [
                {"title": "Title", "url": "https://example.com/a", "content": "Summary", "score": 0.9}
            ]
        }

    def extract(self, urls, **kwargs):
        self.extract_calls.append({"urls": urls, **kwargs})
        return {
            "results": [
                {"title": "Title", "url": "https://example.com/a", "raw_content": "Full markdown"}
            ],
            "failed_results": [],
        }


def test_tavily_search_client_uses_v02_search_defaults():
    client = TavilySearchClient(api_key="dummy")
    client._client = FakeTavilySDK()

    results = client.search("query", subquestion_id="q1", max_results=3)

    assert results[0].query == "query"
    assert client._client.search_calls[0]["search_depth"] == "basic"
    assert client._client.search_calls[0]["include_raw_content"] is False
    assert client._client.search_calls[0]["include_answer"] is False
    assert client._client.search_calls[0]["include_usage"] is True


def test_tavily_search_client_extracts_sources():
    client = TavilySearchClient(api_key="dummy")
    client._client = FakeTavilySDK()

    extracted = client.extract(["https://example.com/a"], subquestion_id="q1")

    assert extracted[0].url == "https://example.com/a"
    assert extracted[0].raw_content == "Full markdown"
    assert client._client.extract_calls[0]["format"] == "markdown"
    assert client._client.extract_calls[0]["extract_depth"] == "basic"
    assert client._client.extract_calls[0]["include_usage"] is True
