from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    stripped = url.strip()
    if not urlsplit(stripped).scheme and "." in stripped.split("/", 1)[0]:
        stripped = f"https://{stripped}"

    parsed = urlsplit(stripped)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in _TRACKING_KEYS or any(lowered.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(query_items)
    return urlunsplit((scheme, netloc, path, query, ""))


def extract_domain(url: str) -> str:
    """Extract normalized domain from a URL for diversity comparison."""
    stripped = url.strip()
    if not urlparse(stripped).scheme and "." in stripped.split("/", 1)[0]:
        stripped = f"https://{stripped}"
    parsed = urlparse(stripped)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host.lower()
