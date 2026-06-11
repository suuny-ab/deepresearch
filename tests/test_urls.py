from deepresearch.utils.urls import normalize_url


def test_normalize_url_removes_www_and_trailing_slash():
    assert normalize_url("https://www.example.com/article/") == "https://example.com/article"


def test_normalize_url_removes_tracking_params():
    assert normalize_url("https://example.com/article?utm_source=x&gclid=y&id=123") == "https://example.com/article?id=123"


def test_normalize_url_lowercases_host_only():
    assert normalize_url("https://Example.com/CasePath") == "https://example.com/CasePath"


def test_normalize_url_adds_https_to_www_host_like_input():
    assert normalize_url("www.example.com/article") == "https://example.com/article"


def test_normalize_url_adds_https_to_host_like_input():
    assert normalize_url("example.com/article") == "https://example.com/article"


def test_normalize_url_removes_root_trailing_slash():
    assert normalize_url("https://example.com/") == "https://example.com"
