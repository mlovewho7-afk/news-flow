import re

TICKER_PATTERN = re.compile(r"\$[A-Z]{1,6}\b")

CATEGORY_KEYWORDS = {
    "Breaking": ["strike", "explosion", "sirens", "military", "attack", "war"],
    "Macro": ["fed", "cpi", "ppi", "gdp", "central bank", "rate", "inflation"],
    "Bonds": ["yield", "treasury", "bond", "curve"],
    "FX": ["usd", "eur", "jpy", "yuan", "forex", "fx"],
    "Corporate": ["earnings", "m&a"],
}
CATEGORY_ORDER = ["Breaking", "Macro", "Bonds", "FX", "Corporate"]


def _compile_keyword_pattern(keywords: list[str]) -> re.Pattern:
    # \b...\b(단어 경계 양쪽)로 "war"가 "software"/"hardware"/"warranty" 같은 무관한
    # 단어 내부·접두사에 걸리지 않게 한다. 대신 "wars" 같은 변형은 안 걸릴 수 있음 —
    # 오분류 방향을 "놓침(Other로 빠짐)" 쪽으로 두는 게 "허위 Breaking 강조"보다 안전하다는
    # 판단(오분류 감수 정책의 구체화).
    escaped = [re.escape(keyword) for keyword in keywords]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


CATEGORY_PATTERNS = {
    category: _compile_keyword_pattern(keywords)
    for category, keywords in CATEGORY_KEYWORDS.items()
}


def categorize(title: str) -> str:
    if TICKER_PATTERN.search(title):
        return "Corporate"
    for category in CATEGORY_ORDER:
        if CATEGORY_PATTERNS[category].search(title):
            return category
    return "Other"
