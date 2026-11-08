"""Bounded, optional web retrieval. Audio files are never uploaded."""
from dataclasses import dataclass
from urllib.parse import urlsplit
import threading
import time

SEARCH_CACHE_SECONDS = 60
_SEARCH_CACHE = {}
_CACHE_LOCK = threading.Lock()


class WebSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchSource:
    title: str
    url: str
    excerpt: str


def clean_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def search_web(query, limit=3):
    query = clean_text(query, 300)
    if not query:
        raise WebSearchError("Type a question before searching the web.")
    key = (query, limit)
    with _CACHE_LOCK:
        cached = _SEARCH_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < SEARCH_CACHE_SECONDS:
            return list(cached[1])
    try:
        from ddgs import DDGS
        rows = DDGS(timeout=15).text(query, max_results=limit, safesearch="moderate")
    except ImportError as exc:
        raise WebSearchError("Web search needs the ddgs package. Install requirements.txt, then retry.") from exc
    except Exception as exc:
        raise WebSearchError("Web search could not connect or was rate-limited. Retry, or turn Search web off for a local answer.") from exc
    sources, seen = [], set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("href") or row.get("url") or "").strip()
        try:
            parsed = urlsplit(url)
            valid = (all(ord(char) > 32 and ord(char) != 127 for char in url)
                     and parsed.scheme in {"https", "http"} and parsed.hostname
                     and not parsed.username and not parsed.password)
        except ValueError:
            valid = False
        excerpt = clean_text(row.get("body") or row.get("description"), 1000)
        if not valid or url in seen or not excerpt:
            continue
        seen.add(url)
        sources.append(SearchSource(clean_text(row.get("title"), 180) or parsed.hostname, url, excerpt))
        if len(sources) == limit:
            break
    if not sources:
        raise WebSearchError("No usable web results were found. Try a more specific question or turn Search web off.")
    with _CACHE_LOCK:
        _SEARCH_CACHE[key] = (time.monotonic(), tuple(sources))
        while len(_SEARCH_CACHE) > 32:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
    return sources


def source_context(sources):
    return "\n\n".join(f"[{i}] {s.title}\nURL: {s.url}\nSearch excerpt: {s.excerpt}"
                        for i, s in enumerate(sources, 1))


def source_footer(sources):
    return "\n\nSearch sources\n" + "\n".join(f"[{i}] {s.title}\n{s.url}" for i, s in enumerate(sources, 1))


def recent_history(messages):
    """Keep four recent exchanges, with bounded source/answer text per message."""
    result = []
    for message in messages:
        if message.get("role") not in {"user", "assistant"}:
            continue
        content = str(message.get("content", ""))
        if len(content) > 1600:
            content = content[:800] + "\n[Earlier context shortened]\n" + content[-800:]
        result.append({"role": message["role"], "content": content})
    return result[-8:]
