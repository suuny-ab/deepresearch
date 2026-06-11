from deepresearch.utils.urls import extract_domain, normalize_url


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


def test_extract_domain_returns_lower_host_without_www():
    assert extract_domain("https://www.Example.com/article") == "example.com"
    assert extract_domain("https://arxiv.org/abs/1234") == "arxiv.org"
    assert extract_domain("http://WWW.GOV.CN/policy") == "gov.cn"


def test_extract_domain_handles_scheme_less_url():
    assert extract_domain("example.com/article") == "example.com"


def test_extract_domain_handles_subdomains():
    assert extract_domain("https://blog.openai.com/research") == "blog.openai.com"
