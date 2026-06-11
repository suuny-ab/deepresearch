from deepresearch.citations import validate_citations


ALLOWED_URLS = {
    "https://example.com/a",
    "https://example.com/b",
    "https://example.com/c",
    "https://example.com/a_(test)",
}


def test_validate_numbered_citation_success():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is True
    assert result.reason is None
    assert result.body_citations == {1}
    assert result.source_citations == {1}


def test_validate_fails_when_sources_section_missing():
    report = "# Report\n\nAI search is changing discovery.[1]"

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "missing_sources_section"


def test_validate_fails_when_body_has_no_numbered_citations():
    report = """# Report

AI search is changing discovery.

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "missing_body_citations"


def test_validate_fails_for_undefined_body_citation():
    report = """# Report

AI search is changing discovery.[1][2]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "undefined_citations"
    assert result.undefined_citations == {2}


def test_validate_fails_for_unused_source_number():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://example.com/a
[2] https://example.com/b
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "unused_sources"
    assert result.unused_sources == {2}


def test_validate_fails_for_invalid_source_url():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://invalid.example/x
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "invalid_source_urls"
    assert result.invalid_source_urls == ["https://invalid.example/x"]


def test_validate_fails_for_bare_url_in_body():
    report = """# Report

AI search is changing discovery https://example.com/a [1]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "bare_urls_in_body"
    assert result.bare_body_urls == ["https://example.com/a"]


def test_validate_supports_sources_line_variants():
    report = """# Report

A.[1]
B.[2]
C.[3]

## Sources

[1] https://example.com/a
[2]: https://example.com/b
- [3] https://example.com/c - Source title
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is True
    assert result.source_urls == {
        1: "https://example.com/a",
        2: "https://example.com/b",
        3: "https://example.com/c",
    }


def test_validate_allows_source_url_ending_with_balanced_parentheses():
    report = """# Report

Balanced parenthesis URLs are valid.[1]

## Sources

[1] https://example.com/a_(test)
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is True
    assert result.source_urls == {1: "https://example.com/a_(test)"}


def test_validate_fails_for_duplicate_source_citation_numbers():
    report = """# Report

Duplicate source numbers hide earlier URLs.[1]

## Sources

[1] https://invalid.example/x
[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "duplicate_source_citations"
    assert result.duplicated_source_citations == {1}


def test_validate_reports_invalid_source_urls_before_unused_sources():
    report = """# Report

Invalid source URLs should not be masked.[1]

## Sources

[1] https://example.com/a
[2] https://invalid.example/x
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "invalid_source_urls"
    assert result.invalid_source_urls == ["https://invalid.example/x"]
