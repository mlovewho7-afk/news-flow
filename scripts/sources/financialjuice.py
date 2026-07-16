import re
from xml.etree import ElementTree

import requests

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


FEED_URL = "https://www.financialjuice.com/feed.ashx"
USER_AGENT = "Mozilla/5.0 (compatible; news-flow/1.0; personal use)"


def fetch_raw() -> str:
    response = requests.get(FEED_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    return response.text


def parse_items(xml_text: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"invalid RSS XML: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS missing <channel> element")

    items = []
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        if guid_el is None or title_el is None or pubdate_el is None:
            # 항목 하나가 스키마를 벗어나도 조용히 건너뛰지 않는다(FAIL-LOUD) — 피드
            # 스키마가 부분적으로 바뀌면 그 사실을 즉시 드러내, 일부 기사가 소리 없이
            # 영구 유실되는 것을 막는다. main()의 호출부가 이 예외를 잡아 기존
            # data/news.json은 건드리지 않고 실패로 종료한다.
            raise ValueError(f"RSS item missing required field (guid/title/pubDate): {ElementTree.tostring(item, encoding='unicode')[:200]}")
            # 참고(운영상 한계, 신규 기능 아님): 피드가 특정 항목에 대해 계속 이 필드를
            # 누락시키면 매 실행이 반복적으로 실패한다. 이 경우 별도 알림 없이 GitHub
            # Actions의 실패 표시(빨간 X)로만 드러난다 — "우선 샘플 테스트" 스코프에서는
            # 이 정도 가시성으로 충분하다고 보고, 별도 알림 채널은 만들지 않는다(YAGNI).
        title = title_el.text or ""
        items.append(
            {
                "guid": guid_el.text,
                "title": title,
                "link": link_el.text if link_el is not None else "",
                "pubDate": pubdate_el.text,
                "category": categorize(title),
            }
        )
    return items
