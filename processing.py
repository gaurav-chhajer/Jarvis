"""Request sizing and query fast paths; no model or audio quality is silently swapped."""
import re

MODEL_KEEP_ALIVE = "30m"
DEFAULT_CONTEXT = 4096


def context_size_for_request(request, history=(), use_web=False):
    # Conservative UTF-8 estimate, system/retrieval allowance, and output headroom.
    length = len(request.encode("utf-8")) + sum(len(row["content"].encode("utf-8")) for row in history)
    estimated_tokens = (length + 1600 + (6000 if use_web else 0)) // 3 + 1024
    return next((size for size in (4096, 8192, 16384, 32768) if size >= estimated_tokens), 32768)


def direct_search_query(question, history=()):
    """Only bypass rewriting for short, standalone, typed questions."""
    if not question or len(question) > 250 or "\n" in question:
        return None
    if history and (len(question.split()) < 6 or re.search(
        r"\b(it|its|he|she|his|her|they|them|their|that|this|these|those|above|previous|same)\b|^and\b|what about",
        question, re.IGNORECASE,
    )):
        return None
    return question.strip() or None


def needs_web_search(question, transcript="", history=()):
    """Route obvious live-information requests without another model inference."""
    raw = question.strip() or transcript
    text = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text).lower()
    explicit = re.search(r"\b(search (?:the )?(?:web|internet|online)|look (?:it |this )?up|browse|find .{0,60}(?:sources|documentation|docs|official|tutorial))\b|https?://", text)
    if explicit:
        return True
    # A transcript's dates or private deadlines do not justify sending it online.
    if transcript and re.search(r"\b(summariz\w*|transcript|what .{0,30}said|our (?:meeting|discussion)|action items|deadline)\b", text):
        return False
    external = re.search(
        r"\b(news|weather|forecast|stock price|share price|exchange rate|live score|election results|"
        r"current (?:president|prime minister|ceo)|who (?:is|owns|runs|leads))\b|"
        r"\b(?:latest|current|newest|recent)\b.{0,50}\b(?:version|release|api|documentation|docs|news|updates|price)\b",
        text,
    )
    if external:
        return True
    if re.search(r"\b(write|implement|debug|fix|refactor|optimize|calculate|solve|prove)\b", text):
        return False
    if not question.strip():
        return False
    if re.search(r"\b(latest|currently|today|tonight|yesterday|recently|right now|this week|this month)\b", text):
        return True
    # Short follow-ups inherit a prior live-information topic.
    if history and len(question.split()) <= 7:
        return any(needs_web_search(row.get("content", "")) for row in history[-4:] if row.get("role") == "user")
    return False
