# FinancialJuice 뉴스 플로우 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FinancialJuice의 공개 RSS(`feed.ashx`)를 10분마다 GitHub Actions로 수집해 다크 실시간
티커 UI(`index.html`)로 보여주는 독립 GitHub Pages 사이트를 만든다.

**Architecture:** Python 스크립트가 RSS를 fetch·파싱·중복제거해 `data/news.json`에 누적 저장한다.
새 항목이 있을 때만 git commit+push한다. `index.html`은 순수 정적 페이지로, 클라이언트 JS가
`data/news.json`을 60초마다 fetch해 화면을 갱신한다. GitHub Actions 크론이 10분마다 스크립트를
실행하고 결과를 같은 저장소에 push해 GitHub Pages가 자동 재배포한다.

**Tech Stack:** Python 3.11 (표준 라이브러리 + `requests`), pytest, 순수 HTML/CSS/JS(빌드 도구
없음), GitHub Actions, GitHub Pages.

## Global Constraints

(설계 문서 `docs/superpowers/specs/2026-07-16-financialjuice-news-flow-design.md`에서 그대로 가져옴)

- 데이터 소스는 `https://www.financialjuice.com/feed.ashx` 단일 소스만 (다른 소스 확장은 범위 밖)
- `data/news.json`에는 상한(캡)을 두지 않는다 — MEASURE-FIRST/REVERSIBLE
- fetch 실패·파싱 실패 시 기존 `data/news.json`을 절대 건드리지 않는다 — FAIL-LOUD
- 신규 항목이 하나도 없으면 git commit 자체를 건너뛴다 (빈 diff 커밋으로 인한 실패 소음 방지)
- 비밀번호는 `kiwoom77` 재사용, SHA-256 해시 `8f441163451b35a7cf6d9b6c205776e18d7278b9e528b73e4267bb870ae31b5b`
  (기존 macro-dashboard의 `agent_06_html_report.py`에서 실제 값 확인·검증됨), `localStorage`
  플래그로 최초 1회만 입력
- GitHub Actions 크론은 `*/10 * * * *`, `concurrency` 그룹으로 겹침 실행 방지
- 저장소명 `news-flow`는 가제 — Task 7(원격 저장소 생성) 실행 전 사용자에게 실제 이름을 재확인
  해야 한다
- 카테고리는 best-effort이며 오분류를 감수한다(설계 문서 참고) — 완벽한 분류 로직을 만들려
  하지 않는다
- "상한 없음" 결정(위 참고)은 `data/news.json` 파일 크기뿐 아니라, 신규 항목이 생길 때마다
  전체 파일을 다시 커밋하는 이 plan의 구현 방식상 **git 저장소 히스토리 자체도 함께
  누적된다는 것**까지 포함해 감수한 리스크다 — plan 단계에서 새로 발견된 게 아니라 spec의
  MEASURE-FIRST/REVERSIBLE 판단 범위 안에 있는 것으로 명시해둔다

---

### Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `scripts/__init__.py`
- Create: `scripts/sources/__init__.py`
- Create: `data/news.json`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `data/news.json`가 빈 배열 `[]`로 커밋되어, 이후 모든 태스크가 `git diff -- data/news.json`을
  안전하게 쓸 수 있는 baseline이 생김

- [ ] **Step 1: `requirements.txt` 작성**

```
requests>=2.31,<3
pytest>=8,<9
```

- [ ] **Step 2: `pytest.ini` 작성**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: `.gitignore` 작성**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

- [ ] **Step 4: 패키지 초기화 파일 생성**

`scripts/__init__.py` — 빈 파일.
`scripts/sources/__init__.py` — 빈 파일.

- [ ] **Step 5: `data/news.json`을 빈 배열로 생성**

```json
[]
```

- [ ] **Step 6: 가상환경 준비 및 의존성 설치 확인**

```bash
cd /Users/sunggeunmoon/Desktop/news-flow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: 에러 없이 설치 완료.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini .gitignore scripts/__init__.py scripts/sources/__init__.py data/news.json
git commit -m "chore: scaffold news-flow project"
```

---

### Task 2: 카테고리 태깅 (`scripts/sources/financialjuice.py`의 `categorize`)

**Files:**
- Create: `scripts/sources/financialjuice.py`
- Test: `tests/test_financialjuice.py`

**Interfaces:**
- Produces: `financialjuice.categorize(title: str) -> str` — Task 3·4가 이 함수를 그대로 씀.
  반환값은 `"Breaking"`, `"Macro"`, `"Bonds"`, `"FX"`, `"Corporate"`, `"Other"` 중 하나.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_financialjuice.py` 새로 작성:

```python
import pytest

from scripts.sources import financialjuice as fj


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Bank of Korea Base Rate Actual 2.75% (Forecast 2.75%, Previous 2.50%)", "Macro"),
        ("Sirens sound in Bahrain: Interior Ministry", "Breaking"),
        ("Nvidia and Kawasaki Heavy Industries to be powered by AI - Nikkei $NVDA", "Corporate"),
        ("Thursday FX Options Expiries", "FX"),
        ("US 10Y Treasury yield curve steepens further", "Bonds"),
        ("Completely unrelated headline about nothing financial", "Other"),
    ],
)
def test_categorize(title, expected):
    assert fj.categorize(title) == expected
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
cd /Users/sunggeunmoon/Desktop/news-flow
source .venv/bin/activate
pytest tests/test_financialjuice.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sources.financialjuice'`

- [ ] **Step 3: `categorize` 최소 구현**

`scripts/sources/financialjuice.py` 새로 작성 (이 파일은 Task 3에서 계속 채워짐):

```python
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
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/test_financialjuice.py -v
```

Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/sources/financialjuice.py tests/test_financialjuice.py
git commit -m "feat: add best-effort category tagging"
```

---

### Task 3: RSS fetch + 파싱 (`financialjuice.py`의 `fetch_raw`, `parse_items`)

**Files:**
- Modify: `scripts/sources/financialjuice.py`
- Modify: `tests/test_financialjuice.py`

**Interfaces:**
- Consumes: Task 2의 `categorize(title: str) -> str`
- Produces:
  - `financialjuice.FEED_URL: str`
  - `financialjuice.fetch_raw() -> str` — 실패 시 `requests.RequestException`(또는 하위 클래스)을 raise
  - `financialjuice.parse_items(xml_text: str) -> list[dict]` — 각 dict는
    `{"guid": str, "title": str, "link": str, "pubDate": str, "category": str}`. 유효하지
    않은 XML이면 `ValueError`를 raise. Task 4의 `fetch_news.py`가 이 두 함수를 그대로 씀.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_financialjuice.py`에 추가:

```python
from unittest.mock import Mock, patch

import requests

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>FinancialJuice</title>
<item>
<title>FinancialJuice: Bank of Korea Base Rate Actual 2.75% (Forecast 2.75%, Previous 2.50%)</title>
<link>https://www.financialjuice.com/News/9680097/a.aspx?xy=rss</link>
<pubDate>Thu, 16 Jul 2026 00:50:03 GMT</pubDate>
<guid isPermaLink="false">9680097</guid>
</item>
<item>
<title>Sirens sound in Bahrain: Interior Ministry</title>
<link>https://www.financialjuice.com/News/9680031/b.aspx?xy=rss</link>
<pubDate>Wed, 15 Jul 2026 23:10:31 GMT</pubDate>
<guid isPermaLink="false">9680031</guid>
</item>
</channel></rss>"""


def test_parse_items_extracts_all_fields():
    items = fj.parse_items(SAMPLE_RSS)
    assert len(items) == 2
    assert items[0] == {
        "guid": "9680097",
        "title": "FinancialJuice: Bank of Korea Base Rate Actual 2.75% (Forecast 2.75%, Previous 2.50%)",
        "link": "https://www.financialjuice.com/News/9680097/a.aspx?xy=rss",
        "pubDate": "Thu, 16 Jul 2026 00:50:03 GMT",
        "category": "Macro",
    }
    assert items[1]["category"] == "Breaking"


def test_parse_items_rejects_invalid_xml():
    with pytest.raises(ValueError):
        fj.parse_items("<not><valid</rss>")


def test_parse_items_rejects_missing_channel():
    with pytest.raises(ValueError):
        fj.parse_items("<rss version=\"2.0\"></rss>")


def test_parse_items_raises_on_item_missing_required_field():
    broken_rss = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Missing pubDate and guid</title></item>
</channel></rss>"""
    with pytest.raises(ValueError):
        fj.parse_items(broken_rss)


@patch("scripts.sources.financialjuice.requests.get")
def test_fetch_raw_returns_body_on_success(mock_get):
    mock_response = Mock()
    mock_response.text = SAMPLE_RSS
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response

    result = fj.fetch_raw()

    assert result == SAMPLE_RSS
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == fj.FEED_URL


@patch("scripts.sources.financialjuice.requests.get")
def test_fetch_raw_raises_on_http_error(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("500 error")
    mock_get.return_value = mock_response

    with pytest.raises(requests.HTTPError):
        fj.fetch_raw()
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/test_financialjuice.py -v
```

Expected: FAIL — `AttributeError: module 'scripts.sources.financialjuice' has no attribute 'parse_items'`
(및 `fetch_raw` 관련 동일 에러)

- [ ] **Step 3: `fetch_raw`, `parse_items` 구현**

`scripts/sources/financialjuice.py` 상단에 import 추가, 파일 맨 아래에 두 함수 추가:

```python
from xml.etree import ElementTree

import requests

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
```

(파일 상단의 `import re`는 그대로 유지, `categorize`·`CATEGORY_*`는 Task 2에서 이미 정의됨.)

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/test_financialjuice.py -v
```

Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/sources/financialjuice.py tests/test_financialjuice.py
git commit -m "feat: fetch and parse FinancialJuice RSS feed"
```

---

### Task 4: 병합·저장 오케스트레이션 (`scripts/fetch_news.py`)

**Files:**
- Create: `scripts/fetch_news.py`
- Create: `tests/test_fetch_news.py`

**Interfaces:**
- Consumes: Task 3의 `financialjuice.fetch_raw()`, `financialjuice.parse_items(xml_text)`
- Produces:
  - `fetch_news.DATA_PATH: Path`
  - `fetch_news.load_existing(path: Path) -> list[dict]`
  - `fetch_news.merge_new(existing: list[dict], new_items: list[dict]) -> tuple[list[dict], bool]`
    — bool은 "신규 항목이 하나라도 추가됐는가"
  - `fetch_news.save(path: Path, items: list[dict]) -> None`
  - `fetch_news.main() -> int` — 0(성공, 신규 유무 무관)/1(fetch·파싱 실패). GitHub Actions
    워크플로우(Task 5)가 이 종료 코드로 실패를 판정.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_fetch_news.py` 새로 작성:

```python
import json
from unittest.mock import patch

from scripts import fetch_news

ITEM_A = {"guid": "1", "title": "A", "link": "http://x/1", "pubDate": "Wed, 15 Jul 2026 10:00:00 GMT", "category": "Macro"}
ITEM_B = {"guid": "2", "title": "B", "link": "http://x/2", "pubDate": "Thu, 16 Jul 2026 09:00:00 GMT", "category": "Breaking"}


def test_merge_new_adds_only_unseen_guids_sorted_newest_first():
    merged, changed = fetch_news.merge_new([ITEM_A], [ITEM_A, ITEM_B])
    assert changed is True
    assert [item["guid"] for item in merged] == ["2", "1"]


def test_merge_new_returns_false_when_nothing_new():
    merged, changed = fetch_news.merge_new([ITEM_A], [ITEM_A])
    assert changed is False
    assert merged == [ITEM_A]


def test_load_existing_returns_empty_list_when_file_missing(tmp_path):
    missing = tmp_path / "news.json"
    assert fetch_news.load_existing(missing) == []


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "news.json"
    fetch_news.save(path, [ITEM_A])
    assert fetch_news.load_existing(path) == [ITEM_A]


@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_writes_file_when_new_items_found(mock_fetch_raw, mock_parse_items, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    mock_parse_items.return_value = [ITEM_A, ITEM_B]

    exit_code = fetch_news.main()

    assert exit_code == 0
    saved = fetch_news.load_existing(data_path)
    assert [item["guid"] for item in saved] == ["2", "1"]


@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_does_not_touch_file_when_no_new_items(mock_fetch_raw, mock_parse_items, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    mtime_before = data_path.stat().st_mtime_ns
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    mock_parse_items.return_value = [ITEM_A]

    exit_code = fetch_news.main()

    assert exit_code == 0
    assert data_path.stat().st_mtime_ns == mtime_before


@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_leaves_existing_file_untouched_on_fetch_failure(mock_fetch_raw, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.side_effect = ConnectionError("network down")

    exit_code = fetch_news.main()

    assert exit_code == 1
    assert fetch_news.load_existing(data_path) == [ITEM_A]


@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_leaves_existing_file_untouched_on_parse_failure(mock_fetch_raw, mock_parse_items, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<not>valid<rss"
    mock_parse_items.side_effect = ValueError("invalid RSS XML")

    exit_code = fetch_news.main()

    assert exit_code == 1
    assert fetch_news.load_existing(data_path) == [ITEM_A]
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/test_fetch_news.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.fetch_news'`

- [ ] **Step 3: `scripts/fetch_news.py` 구현**

```python
import json
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

from scripts.sources import financialjuice

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "news.json"


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sort_key(item: dict):
    return parsedate_to_datetime(item["pubDate"])


def merge_new(existing: list[dict], new_items: list[dict]) -> tuple[list[dict], bool]:
    existing_guids = {item["guid"] for item in existing}
    added = [item for item in new_items if item["guid"] not in existing_guids]
    if not added:
        return existing, False
    merged = existing + added
    merged.sort(key=_sort_key, reverse=True)
    return merged, True


def save(path: Path, items: list[dict]) -> None:
    # 임시 파일에 다 쓴 뒤 원자적으로 교체한다(os.replace 기반 Path.replace). 워크플로우
    # 러너가 쓰는 도중 타임아웃·강제종료되더라도 목적 파일은 "쓰기 전 상태" 아니면
    # "쓰기 완료 상태" 둘 중 하나만 가능 — 잘린 JSON이 남아 다음 실행의 load_existing()이
    # 깨지는 것을 막는다.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def main() -> int:
    try:
        raw = financialjuice.fetch_raw()
        new_items = financialjuice.parse_items(raw)
    except Exception as exc:  # noqa: BLE001 — fetch/parse 실패는 전부 FAIL-LOUD 대상
        print(f"fetch_news: failed to fetch/parse feed: {exc}", file=sys.stderr)
        return 1

    existing = load_existing(DATA_PATH)
    merged, changed = merge_new(existing, new_items)

    if not changed:
        print("fetch_news: no new items, nothing to do")
        return 0

    save(DATA_PATH, merged)
    print(f"fetch_news: wrote {len(merged)} items ({len(merged) - len(existing)} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/ -v
```

Expected: PASS (전체, 20 passed — Task2 6개 + Task3 6개 + Task4 8개)

- [ ] **Step 5: 로컬에서 실제 네트워크로 1회 수동 실행**

```bash
python -m scripts.fetch_news
cat data/news.json | head -c 500
```

Expected: 종료 코드 0, `fetch_news: wrote N items (N new)` 출력, `data/news.json`에 실제
FinancialJuice 기사가 채워짐.

- [ ] **Step 6: 같은 스크립트를 곧바로 2회 연속 실행 (spec 검증계획 항목 2 — 실네트워크)**

```bash
python -m scripts.fetch_news
```

Expected: 실제 뉴스 발행 간격을 감안하면 대부분 몇 초 안에는 새 기사가 없을 가능성이 높음 —
`fetch_news: no new items, nothing to do` 출력과 종료 코드 0. `git status`로 `data/news.json`이
변경되지 않았음을 확인(새 기사가 실제로 그 사이 발행됐다면 정상적으로 갱신되는 것도 정상
동작 — 그 경우 `no new items` 메시지 대신 wrote 메시지가 나오는 게 맞다).

(spec 검증계획의 "파싱 실패 시에도 훼손 안 됨" 항목은 여기서 실네트워크로 재현하지 않는다 —
Cloudflare가 challenge 페이지를 반환하는 상황은 사용자가 임의로 재현할 수 없는 제3자 서버
동작이라, 실측 대신 Task 3의 `test_parse_items_raises_on_item_missing_required_field`와
Task 4의 `test_main_leaves_existing_file_untouched_on_parse_failure` 유닛테스트로 그 경로의
로직을 검증한다. 이건 누락이 아니라 "재현 불가능한 조건은 mock으로, 재현 가능한 조건은
실네트워크로"라는 의도적 구분이다.)

- [ ] **Step 7: 접근 불가능한 URL로 1회 실행 (spec 검증계획 항목 3 — 실네트워크 실패 경로)**

```bash
python3 -c "
import sys
from scripts.sources import financialjuice
from scripts import fetch_news
financialjuice.FEED_URL = 'https://www.financialjuice.com/this-path-does-not-exist-404'
sys.exit(fetch_news.main())
"
echo "exit code: $?"
git status --porcelain data/news.json
```

Expected: `exit code: 1`, 표준에러로 `fetch_news: failed to fetch/parse feed: ...` 출력,
`git status --porcelain data/news.json`은 빈 출력(파일 변경 없음 — FAIL-LOUD 확인).

- [ ] **Step 8: Commit**

```bash
git add scripts/fetch_news.py tests/test_fetch_news.py data/news.json
git commit -m "feat: merge and persist fetched news with fail-loud handling"
```

---

### Task 5: GitHub Actions 워크플로우

**Files:**
- Create: `.github/workflows/fetch-news.yml`

**Interfaces:**
- Consumes: Task 4의 `python -m scripts.fetch_news` (CLI, 종료 코드로 성공/실패 판단),
  `requirements.txt`(Task 1)
- Produces: 없음 (터미널 태스크, 이후 태스크가 이 파일을 참조하지 않음)

- [ ] **Step 1: 워크플로우 파일 작성**

spec의 검증 계획은 "수동 트리거로 먼저 확인한 뒤 크론 스케줄을 활성화"하라고 명시적으로
요구한다. 이를 실제로 지키기 위해, 이 시점에는 **크론 트리거를 아직 넣지 않는다** —
`workflow_dispatch`만 있는 상태로 커밋·push하고, Task 7에서 수동 트리거 검증이 실제로
통과한 뒤에야 크론을 추가하는 별도 커밋을 만든다.

```yaml
name: Fetch News

on:
  workflow_dispatch: {}
  # 크론(schedule) 트리거는 아직 없음 — Task 7에서 workflow_dispatch 수동 검증을 통과한
  # 뒤에 별도 커밋으로 추가한다(spec의 "확인 후 활성화" 순서를 그대로 지키기 위함).

concurrency:
  group: fetch-news
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Fetch news
        run: python -m scripts.fetch_news

      - name: Commit and push if changed
        run: |
          if ! git diff --quiet -- data/news.json; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add data/news.json
            git commit -m "news: update $(date -u +%Y-%m-%dT%H:%M:%SZ)"
            git push
          else
            echo "No new items, skipping commit"
          fi
```

- [ ] **Step 2: YAML 문법 검증**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/fetch-news.yml'))" && echo "valid yaml"
```

Expected: `valid yaml` 출력 (에러 없음). `pyyaml`이 없으면 `pip install pyyaml`로 임시 설치 후
검증만 하고 삭제해도 무방(이 프로젝트의 상시 의존성 아님).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/fetch-news.yml
git commit -m "ci: fetch FinancialJuice news every 10 minutes"
```

(이 워크플로우의 실제 동작 확인은 Task 7에서 원격 저장소가 생긴 뒤 `workflow_dispatch`로
수동 트리거해 검증한다 — 로컬 git만으로는 GitHub Actions 자체를 실행할 수 없다.)

---

### Task 6: 프론트엔드 (`index.html`)

**Files:**
- Create: `index.html`

**Interfaces:**
- Consumes: `data/news.json` (Task 4가 생성하는 파일, 필드: `guid`/`title`/`link`/`pubDate`/`category`)
- Produces: 없음 (최종 사용자 화면)

- [ ] **Step 1: `index.html` 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>News Flow — FinancialJuice</title>
<style>
  :root{--bg:#0b0e14;--surface:#12161f;--border:#1e2530;--text:#e8ebef;--muted:#5c6b7f;
    --breaking-bg:rgba(192,57,43,0.12);--breaking-text:#ff6b5c;--tab-active:#3b82f6}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  .header{padding:14px 16px;border-bottom:1px solid var(--border);font-size:15px;font-weight:600;
    display:flex;justify-content:space-between;align-items:center}
  .last-updated{font-size:11px;font-weight:400;color:var(--muted)}
  .tabs{display:flex;gap:8px;padding:8px 10px;border-bottom:1px solid var(--border);
    overflow-x:auto}
  .tab{font-size:11px;padding:4px 10px;border-radius:3px;background:var(--surface);
    color:var(--muted);white-space:nowrap;cursor:pointer;border:none}
  .tab.active{background:var(--tab-active);color:#fff}
  .list{font-family:'SF Mono',Menlo,monospace;font-size:12px;line-height:1.5}
  .row{display:flex;gap:10px;padding:6px 12px;border-bottom:1px solid #161b24}
  .row.breaking{background:var(--breaking-bg)}
  .time{color:var(--muted);flex-shrink:0}
  .row.breaking .time{color:var(--breaking-text);font-weight:600}
  .title{color:var(--text)}
  .row.breaking .title{color:#fff;font-weight:600}
  .empty{padding:24px;text-align:center;color:var(--muted);font-size:13px}

  .gate-overlay{display:none;position:fixed;inset:0;z-index:9999;background:var(--bg);
    align-items:center;justify-content:center}
  html.gate-locked .gate-overlay{display:flex}
  html.gate-locked .app{display:none}
  .gate-box{display:flex;flex-direction:column;gap:10px;align-items:center}
  .gate-label{font-size:13px;color:var(--muted)}
  .gate-input{padding:9px 14px;border-radius:6px;border:1px solid var(--border);
    background:var(--surface);color:var(--text);font-size:14px;width:220px;text-align:center}
  .gate-btn{padding:9px 20px;border-radius:6px;border:none;background:var(--tab-active);
    color:#fff;font-size:13px;font-weight:600;cursor:pointer}
  .gate-btn:hover{opacity:.9}
  .gate-error{font-size:12px;color:var(--breaking-text);visibility:hidden}
</style>
</head>
<body>

<script>
if (localStorage.getItem('news_gate_ok') !== '1') {
  document.documentElement.classList.add('gate-locked');
}
</script>

<div class="gate-overlay">
  <div class="gate-box">
    <div class="gate-label">비밀번호를 입력하세요</div>
    <input type="password" class="gate-input" id="gate-pw" autocomplete="off">
    <button class="gate-btn" id="gate-submit">확인</button>
    <div class="gate-error" id="gate-error">비밀번호가 틀렸습니다</div>
  </div>
</div>
<script>
(function(){
  var GATE_HASH = '8f441163451b35a7cf6d9b6c205776e18d7278b9e528b73e4267bb870ae31b5b';
  async function sha256(text){
    var buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,'0');}).join('');
  }
  async function submit(){
    var pw = document.getElementById('gate-pw').value;
    var h = await sha256(pw);
    if (h === GATE_HASH) {
      localStorage.setItem('news_gate_ok','1');
      document.documentElement.classList.remove('gate-locked');
    } else {
      document.getElementById('gate-error').style.visibility = 'visible';
    }
  }
  document.getElementById('gate-submit').addEventListener('click', submit);
  document.getElementById('gate-pw').addEventListener('keydown', function(e){
    if(e.key === 'Enter') submit();
  });
})();
</script>

<div class="app">
  <div class="header">
    <span>News Flow — FinancialJuice</span>
    <span class="last-updated" id="last-updated"></span>
  </div>
  <div class="tabs" id="tabs"></div>
  <div class="list" id="list"><div class="empty">불러오는 중...</div></div>
</div>

<script>
(function(){
  var CATEGORIES = ["전체", "Breaking", "Macro", "Bonds", "FX", "Corporate", "Other"];
  var activeCategory = "전체";
  var allItems = [];

  function toKST(pubDate){
    var d = new Date(pubDate);
    if (isNaN(d.getTime())) return pubDate;
    return d.toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', hour12: false,
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
  }

  function render(){
    var tabsEl = document.getElementById('tabs');
    tabsEl.innerHTML = '';
    CATEGORIES.forEach(function(cat){
      var btn = document.createElement('button');
      btn.className = 'tab' + (cat === activeCategory ? ' active' : '');
      btn.textContent = cat;
      btn.addEventListener('click', function(){ activeCategory = cat; render(); });
      tabsEl.appendChild(btn);
    });

    var listEl = document.getElementById('list');
    var filtered = activeCategory === '전체'
      ? allItems
      : allItems.filter(function(item){ return item.category === activeCategory; });

    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="empty">표시할 뉴스가 없습니다</div>';
      return;
    }

    listEl.innerHTML = '';
    filtered.forEach(function(item){
      var row = document.createElement('div');
      row.className = 'row' + (item.category === 'Breaking' ? ' breaking' : '');
      var time = document.createElement('span');
      time.className = 'time';
      time.textContent = toKST(item.pubDate);
      var title = document.createElement('a');
      title.className = 'title';
      title.href = item.link;
      title.target = '_blank';
      title.rel = 'noopener noreferrer';
      title.style.color = 'inherit';
      title.style.textDecoration = 'none';
      title.textContent = item.title;
      row.appendChild(time);
      row.appendChild(title);
      listEl.appendChild(row);
    });
  }

  function load(){
    fetch('./data/news.json?_=' + Date.now())
      .then(function(res){ return res.json(); })
      .then(function(data){
        allItems = data;
        render();
        document.getElementById('last-updated').textContent =
          '마지막 갱신 ' + new Date().toLocaleTimeString('ko-KR', {timeZone: 'Asia/Seoul', hour12: false});
      })
      .catch(function(err){
        console.error('news-flow: failed to load data/news.json', err);
      });
  }

  load();
  setInterval(load, 60000);
  // 백그라운드 탭은 브라우저가 setInterval을 강하게 스로틀링하거나 탭을 discard할 수
  // 있어, 탭이 다시 보이는 순간 즉시 재요청해 오래된 화면을 계속 보여주는 걸 막는다.
  document.addEventListener('visibilitychange', function(){
    if (document.visibilityState === 'visible') load();
  });
})();
</script>

</body>
</html>
```

- [ ] **Step 2: 로컬 브라우저로 수동 확인**

```bash
cd /Users/sunggeunmoon/Desktop/news-flow
python3 -m http.server 8000
```

브라우저로 `http://localhost:8000/index.html` 접속.

Expected 체크리스트:
- 가림막이 먼저 뜨고, 틀린 비밀번호 입력 시 "비밀번호가 틀렸습니다" 표시
- `kiwoom77` 입력 시 가림막이 사라지고 티커 목록이 보임
- 새로고침해도 가림막이 다시 뜨지 않음(localStorage 유지 확인)
- 카테고리 탭 클릭 시 목록이 필터링됨
- Breaking 카테고리 항목이 좌측 빨간 강조로 표시됨
- 시간이 KST(UTC+9) 기준으로 표시됨(예: 피드의 `00:50 GMT` 기사가 `09:50`으로 보임)
- 헤더 우측에 "마지막 갱신 HH:MM:SS"가 표시되고, 60초 후 자동으로 갱신됨

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: add dark ticker frontend with category filter and password gate"
```

---

### Task 7: 원격 저장소 생성 및 배포 (사용자 확인 필요)

**Files:** 없음 (인프라 태스크)

**Interfaces:**
- Consumes: Task 1~6에서 만든 전체 저장소 내용
- Produces: 없음 (최종 배포)

**⚠️ 이 태스크는 공개 GitHub 저장소를 새로 만들고 인터넷에 push하는 되돌리기 어려운 작업이다.
Step 1은 명시적 정지 지점이다 — subagent 실행자는 사용자로부터 "저장소를 만들어도 된다"는
분명한 응답을 실제로 받기 전까지 Step 2로 넘어가서는 안 된다. `gh auth status` 실행만으로
Step 1을 완료 처리하고 자동으로 다음 스텝으로 진행하지 말 것.**

**이 문서(마크다운 체크리스트) 자체는 실행을 강제로 멈출 수 없다 — 최종 책임은 이 plan을
실행하는 세션(subagent-driven-development든 executing-plans든, 이걸 오케스트레이션하는
메인 세션)이 진다. 메인 세션은 자신의 운영 원칙상 "공개 저장소 생성·push"를 되돌리기 어려운
가시적 행동으로 취급해 사용자 확인 없이는 진행하지 않아야 한다 — 이 경고문은 그 판단을
대체하는 게 아니라 놓치지 않도록 상기시키는 역할이다.**

- [ ] **Step 1: 사용자에게 저장소 이름·계정 확인 — 응답 받을 때까지 대기**

터미널에서 로그인 계정 확인:

```bash
gh auth status
```

사용자에게 "저장소 이름을 `news-flow`로 만들어도 될지, GitHub Pages로 공개될 텐데 괜찮을지"
직접 질문하고, 명시적인 승인 응답을 받는다. 이 태스크를 실행하는 주체가 subagent라면, 여기서
실행을 멈추고 상위 세션에 확인을 요청해야 한다(자동 진행 금지).

- [ ] **Step 2: GitHub 저장소 생성 및 최초 push**

```bash
cd /Users/sunggeunmoon/Desktop/news-flow
gh repo create news-flow --public --source=. --remote=origin --push
```

Expected: 저장소가 생성되고 지금까지의 커밋이 모두 push됨.

- [ ] **Step 3: GitHub Pages 활성화**

```bash
gh api -X POST repos/{owner}/news-flow/pages -f "source[branch]=main" -f "source[path]=/"
```

`{owner}`는 Step 1에서 확인한 실제 계정명으로 치환. **이 API 요청 바디 스펙은 이번 계획
수립 과정에서 라이브 호출로 검증되지 않았다** — `gh api --help`로 `key[subkey]=value` 중첩
문법 자체는 확인했지만, GitHub REST API가 이 엔드포인트에 추가 필드를 요구하는지는 실제
실행 시점에 판단해야 한다.

Expected: 명령이 0으로 종료하고 JSON 응답에 `"status"` 필드가 포함됨. **실패하면(0이 아닌
종료 코드, 혹은 4xx 에러 JSON) 이 스텝을 실패로 간주하고**, GitHub 웹의 Settings → Pages에서
수동으로 `main` 브랜치 `/`(root)를 Pages 소스로 지정한 뒤에만 다음 스텝으로 진행한다 — 실패를
못 본 척 넘어가지 않는다.

- [ ] **Step 4: 워크플로우 수동 트리거로 1회 검증**

```bash
gh workflow run fetch-news.yml
for i in $(seq 1 12); do
  sleep 10
  status=$(gh run list --workflow=fetch-news.yml --limit 1 --json status,conclusion --jq '.[0].status')
  echo "attempt $i: status=$status"
  if [ "$status" = "completed" ]; then
    break
  fi
done
gh run list --workflow=fetch-news.yml --limit 1 --json status,conclusion
```

Expected: 최대 120초 안에 `status`가 `completed`로 바뀌고 `conclusion`이 `success`. 120초가
지나도 `completed`가 안 되면 `gh run view --log`로 직접 로그를 확인한다(고정된 `sleep 30`
한 번으로 끝내지 않고, 실제로 종료 상태에 도달했는지 폴링으로 확인).

- [ ] **Step 5: 수동 검증 통과 후 크론 스케줄 활성화**

Step 4가 `success`로 끝난 뒤에만 진행한다. `.github/workflows/fetch-news.yml`의 `on:` 블록을
아래 내용으로 교체(크론 트리거 추가):

```yaml
on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch: {}
```

```bash
git add .github/workflows/fetch-news.yml
git commit -m "ci: activate 10-minute cron after manual verification"
git push
```

Expected: push 성공. 이 시점부터 실제로 10분마다 자동 실행이 시작된다.

- [ ] **Step 6: Pages 배포 확인**

```bash
gh api repos/{owner}/news-flow/pages --jq .html_url
```

출력된 URL을 브라우저로 열어, Task 6의 체크리스트(가림막·티커·카테고리 필터·KST 시간)가
실제 배포본에서도 동작하는지 확인한다.

- [ ] **Step 7: 크론 동작 확인 (선택, 시간이 걸림)**

10~20분 뒤 저장소의 커밋 히스토리를 확인해 `news: update ...` 커밋이 자동으로 쌓이는지 확인:

```bash
gh api repos/{owner}/news-flow/commits --jq '.[0:3] | .[].commit.message'
```

Expected: 새 뉴스가 있었다면 `news: update <timestamp>` 커밋이 보임. 없었다면(뉴스가 뜸한
시간대) 커밋이 안 쌓이는 게 정상 동작(Task 4의 "신규 항목 없으면 스킵" 설계대로).

---

## 실행 순서 요약

Task 1 → 2 → 3 → 4는 순서대로(각자 이전 태스크의 함수에 의존). Task 5·6은 Task 4 완료 후
서로 독립적으로 병행 가능. Task 7은 반드시 마지막(1~6이 모두 로컬에서 커밋된 뒤).

<!-- spec-review: passed lenses=3 date=2026-07-16 -->
