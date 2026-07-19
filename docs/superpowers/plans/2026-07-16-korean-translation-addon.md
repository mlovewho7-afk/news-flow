# 한글 번역 기능 추가 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 배포된 news-flow에 DeepL API 기반 서버측 한글 번역을 얹는다 — 신규 항목은
수집 시 번역, 기존 항목은 1회 백필, 화면엔 한글(실패 시 영어 폴백)만 표시한다.

**Architecture:** `scripts/translate.py`가 DeepL 호출을 캡슐화(실패 시 예외 없이 `None`).
`scripts/fetch_news.py`는 merge 전에 "진짜 신규" 항목만 추려 번역해 예산을 아낀다.
`scripts/backfill_translations.py`는 기존 데이터를 1회성으로 채우는 멱등 스크립트.
`index.html`은 `title_ko || title`로 렌더링하고 영어 폴백에만 `lang="en"`을 단다.

**Tech Stack:** Python 3.11(기존과 동일, `requests` 재사용), pytest, GitHub Actions.

## Global Constraints

(설계 문서 `docs/superpowers/specs/2026-07-16-korean-translation-addon-design.md`에서 그대로
가져옴)

- 번역은 서버측(수집 단계)에서 DeepL API Free로 수행
- 화면엔 한글만 표시(`title_ko || title` 폴백), 영어 폴백 요소에만 `lang="en"`을 단다 —
  페이지 전역 `<html lang>`을 동적으로 바꾸지 않는다(접근성 리그레션 방지, 이미 설계 리뷰에서
  제외 확정됨)
- 매 10분 fetch에서 **진짜 신규 항목만** 번역한다 — 매번 피드 전체(~100개)를 재번역하지 않는다
  (예산 보호가 이 동작에 달려있으므로 반드시 지켜야 함)
- 번역 실패는 FAIL-LOUD가 아니다 — 실패해도 수집은 계속되고 원문으로 폴백하되, 성공/실패
  개수를 로그에 남긴다(`N/M translated`)
- `translate_to_ko(text: str) -> str | None`은 어떤 이유로든 예외를 밖으로 내보내지 않는다
- DeepL 무료 한도(월 50만자) 초과 가능성을 사용자가 인지하고 그대로 진행하기로 했다 — 한도
  대응(카테고리 제한, 유료 전환 등)은 지금 만들지 않는다
- DeepL API의 정확한 요청/응답 스펙은 이 세션에서 라이브 검증되지 않은 가정이다 — 실제 배포
  단계(Task 6)에서 처음으로 실제 API를 호출해 확인하고, 다르면 그 자리에서 수정한다
- `backfill_translations.py`는 멱등(이미 성공한 항목은 재번역 안 함, 실패한 항목은 재시도)
- 두 워크플로우(`fetch-news.yml`, `backfill-translations.yml`)는 같은 concurrency 그룹
  (`fetch-news`)을 써서 git push 경합을 막는다
- `backfill_translations.py`의 API 호출 사이 `time.sleep(0.5)`는 검증되지 않은 보수적
  기본값일 뿐, DeepL의 실제 rate-limit에 근거한 값이 아니다(문서화된 한계로 취급)

---

### Task 1: 번역 모듈 (`scripts/translate.py`)

**Files:**
- Create: `scripts/translate.py`
- Create: `tests/test_translate.py`

**Interfaces:**
- Produces: `translate.translate_to_ko(text: str) -> str | None` — Task 2·3이 이 함수를
  그대로 씀. 계약: 어떤 이유로도 예외를 던지지 않음. `DEEPL_API_KEY` 환경변수가 없으면 API
  호출 자체를 시도하지 않고 즉시 `None`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_translate.py` 새로 작성:

```python
from unittest.mock import Mock, patch

import requests

from scripts import translate


def test_translate_to_ko_returns_none_when_key_missing(monkeypatch):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_translation_on_success(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.json.return_value = {
        "translations": [{"text": "안녕하세요", "detected_source_language": "EN"}]
    }
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    result = translate.translate_to_ko("Hello")

    assert result == "안녕하세요"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"]["text"] == "Hello"
    assert call_kwargs["data"]["target_lang"] == "KO"
    assert call_kwargs["headers"]["Authorization"] == "DeepL-Auth-Key fake-key:fx"


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_http_error(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("456 quota exceeded")
    mock_post.return_value = mock_response

    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_network_exception(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_post.side_effect = requests.ConnectionError("network down")

    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_malformed_response(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {"unexpected": "shape"}
    mock_post.return_value = mock_response

    assert translate.translate_to_ko("Hello") is None
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
source .venv/bin/activate
pytest tests/test_translate.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.translate'`

- [ ] **Step 3: `translate_to_ko` 구현**

`scripts/translate.py` 새로 작성:

```python
import os

import requests

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"


def translate_to_ko(text: str) -> str | None:
    api_key = os.environ.get("DEEPL_API_KEY")
    if not api_key:
        return None
    try:
        response = requests.post(
            DEEPL_API_URL,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            data={"text": text, "target_lang": "KO"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data["translations"][0]["text"]
    except Exception:
        # 의도적으로 광범위하게 잡는다 — 이 함수는 어떤 이유로도 예외를 밖으로
        # 내보내지 않는다는 게 호출자와의 계약이다(설계 문서에서 명시적으로
        # 결정된 사항이지, 실수로 넓게 잡은 게 아니다). 원인별로 다르게 처리하지
        # 않고 전부 None으로 뭉개는 대신, 호출자가 성공/실패 개수를 세어 로그로
        # 남긴다(Task 2 참고).
        return None
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/test_translate.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/translate.py tests/test_translate.py
git commit -m "feat: add DeepL translation module with fail-safe None fallback"
```

---

### Task 2: `fetch_news.py` 통합 — 신규 항목만 번역

**Files:**
- Modify: `scripts/fetch_news.py`
- Modify: `tests/test_fetch_news.py`

**Interfaces:**
- Consumes: Task 1의 `translate.translate_to_ko(text: str) -> str | None`
- Produces: `main()`의 동작이 바뀜 — 이제 `truly_new` 항목마다 `item["title_ko"]`를 채우고,
  로그에 번역 성공/실패 개수를 포함한다. `load_existing`/`merge_new`/`save`의 시그니처는
  변경 없음. 단, 재사용 범위는 태스크마다 다르다 — Task 3(백필)은 `DATA_PATH`/`load_existing`/
  `save`만 재사용하고 `merge_new`는 쓰지 않는다(백필은 병합이 아니라 기존 항목의 필드를
  제자리에서 채우는 것이므로 병합 로직이 필요 없음). Task 4는 이 세 함수를 직접 import하지
  않고 `python -m scripts.fetch_news`/`python -m scripts.backfill_translations`를 CLI로
  실행할 뿐이다.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_fetch_news.py` 상단 import에 다음을 추가:

```python
from scripts import translate
```

기존 `test_main_writes_file_when_new_items_found` 테스트를 아래로 **교체**(번역 mock 추가):

```python
@patch("scripts.fetch_news.translate.translate_to_ko")
@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_writes_file_when_new_items_found(mock_fetch_raw, mock_parse_items, mock_translate, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    mock_parse_items.return_value = [ITEM_A, ITEM_B]
    mock_translate.return_value = "번역됨"

    exit_code = fetch_news.main()

    assert exit_code == 0
    saved = fetch_news.load_existing(data_path)
    assert [item["guid"] for item in saved] == ["2", "1"]
    saved_b = next(item for item in saved if item["guid"] == "2")
    assert saved_b["title_ko"] == "번역됨"
```

다음 테스트를 새로 추가:

```python
@patch("scripts.fetch_news.translate.translate_to_ko")
@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_translates_only_truly_new_items(mock_fetch_raw, mock_parse_items, mock_translate, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])  # guid "1"은 이미 존재
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    # 피드가 기존 항목(ITEM_A)과 신규 항목(ITEM_B)을 모두 반환 — 흔한 경우(매 fetch가
    # 최신 스냅샷 전체를 반환)
    mock_parse_items.return_value = [ITEM_A, ITEM_B]
    mock_translate.return_value = "번역됨"

    fetch_news.main()

    mock_translate.assert_called_once_with(ITEM_B["title"])  # ITEM_A는 번역 대상 아님


@patch("scripts.fetch_news.translate.translate_to_ko")
@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_sets_title_ko_none_when_translation_fails(mock_fetch_raw, mock_parse_items, mock_translate, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    mock_parse_items.return_value = [ITEM_A, ITEM_B]
    mock_translate.return_value = None  # 번역 실패

    exit_code = fetch_news.main()

    assert exit_code == 0  # 번역 실패가 파이프라인을 막지 않음
    saved = fetch_news.load_existing(data_path)
    saved_b = next(item for item in saved if item["guid"] == "2")
    assert saved_b["title_ko"] is None


@patch("scripts.fetch_news.translate.translate_to_ko")
@patch("scripts.fetch_news.financialjuice.parse_items")
@patch("scripts.fetch_news.financialjuice.fetch_raw")
def test_main_logs_translation_count(mock_fetch_raw, mock_parse_items, mock_translate, tmp_path, monkeypatch, capsys):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_A])
    monkeypatch.setattr(fetch_news, "DATA_PATH", data_path)
    mock_fetch_raw.return_value = "<rss/>"
    mock_parse_items.return_value = [ITEM_A, ITEM_B]
    mock_translate.return_value = "번역됨"

    fetch_news.main()

    captured = capsys.readouterr()
    assert "1/1 translated" in captured.out
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/test_fetch_news.py -v
```

Expected: FAIL — `AttributeError: <module 'scripts.fetch_news' ...> does not have the attribute 'translate'` (혹은 `title_ko` 관련 `KeyError`/`AssertionError`)

- [ ] **Step 3: `scripts/fetch_news.py`의 `main()` 수정**

파일 상단 import에 추가:

```python
from scripts import translate
```

기존 `main()` 함수 전체를 아래로 교체:

```python
def main() -> int:
    try:
        raw = financialjuice.fetch_raw()
        new_items = financialjuice.parse_items(raw)
    except Exception as exc:  # noqa: BLE001 — fetch/parse 실패는 전부 FAIL-LOUD 대상
        print(f"fetch_news: failed to fetch/parse feed: {exc}", file=sys.stderr)
        return 1

    existing = load_existing(DATA_PATH)
    existing_guids = {item["guid"] for item in existing}
    truly_new = [item for item in new_items if item["guid"] not in existing_guids]

    if not truly_new:
        print("fetch_news: no new items, nothing to do")
        return 0

    translated_count = 0
    for item in truly_new:
        item["title_ko"] = translate.translate_to_ko(item["title"])
        if item["title_ko"] is not None:
            translated_count += 1

    merged, changed = merge_new(existing, truly_new)
    save(DATA_PATH, merged)
    print(
        f"fetch_news: wrote {len(merged)} items ({len(truly_new)} new, "
        f"{translated_count}/{len(truly_new)} translated)"
    )
    return 0
```

`load_existing`, `_sort_key`, `merge_new`, `save` 함수는 변경하지 않는다 — 그대로 둔다.

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/ -v
```

Expected: PASS (전체 28개 — Task1까지 25개 + 이번에 추가 3개 + 기존 1개 교체는 개수 불변)

- [ ] **Step 5: 로컬 스모크 테스트 (키 없이) — 회귀 확인**

```bash
unset DEEPL_API_KEY
python -m scripts.fetch_news
```

Expected: 종료 코드 0. `DEEPL_API_KEY`가 없으므로 `translate_to_ko`가 즉시 `None`을 반환하고,
신규 항목이 있다면 `title_ko: null`로 저장되며 로그에 `0/N translated`가 찍힌다(실제 DeepL
호출은 Task 6에서 시크릿이 있는 GitHub Actions 환경에서 처음 검증한다).

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_news.py tests/test_fetch_news.py data/news.json
git commit -m "feat: translate only truly-new items during fetch, log success/failure counts"
```

---

### Task 3: 백필 스크립트 (`scripts/backfill_translations.py`)

**Files:**
- Create: `scripts/backfill_translations.py`
- Create: `tests/test_backfill_translations.py`

**Interfaces:**
- Consumes: Task 1의 `translate.translate_to_ko`, 기존 `fetch_news.DATA_PATH`/`load_existing`/`save`
- Produces: `backfill_translations.main() -> int`, `backfill_translations.DATA_PATH`(테스트에서
  monkeypatch 가능하도록 모듈 레벨 이름으로 재노출)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_backfill_translations.py` 새로 작성:

```python
from unittest.mock import patch

import pytest

from scripts import backfill_translations, fetch_news

ITEM_TRANSLATED = {
    "guid": "1", "title": "A", "link": "http://x/1",
    "pubDate": "Wed, 15 Jul 2026 10:00:00 GMT", "category": "Macro", "title_ko": "가",
}
ITEM_MISSING_FIELD = {
    "guid": "2", "title": "B", "link": "http://x/2",
    "pubDate": "Wed, 15 Jul 2026 11:00:00 GMT", "category": "Bonds",
}
ITEM_FAILED = {
    "guid": "3", "title": "C", "link": "http://x/3",
    "pubDate": "Wed, 15 Jul 2026 12:00:00 GMT", "category": "FX", "title_ko": None,
}


@patch("scripts.backfill_translations.time.sleep")
@patch("scripts.backfill_translations.translate.translate_to_ko")
def test_main_translates_only_items_missing_title_ko(mock_translate, mock_sleep, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_TRANSLATED, ITEM_MISSING_FIELD, ITEM_FAILED])
    monkeypatch.setattr(backfill_translations, "DATA_PATH", data_path)
    mock_translate.return_value = "번역됨"

    exit_code = backfill_translations.main()

    assert exit_code == 0
    assert mock_translate.call_count == 2  # ITEM_MISSING_FIELD, ITEM_FAILED만
    saved = fetch_news.load_existing(data_path)
    saved_by_guid = {item["guid"]: item for item in saved}
    assert saved_by_guid["1"]["title_ko"] == "가"  # 원래 값 그대로
    assert saved_by_guid["2"]["title_ko"] == "번역됨"
    assert saved_by_guid["3"]["title_ko"] == "번역됨"


@patch("scripts.backfill_translations.time.sleep")
@patch("scripts.backfill_translations.translate.translate_to_ko")
def test_main_returns_early_when_nothing_pending(mock_translate, mock_sleep, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_TRANSLATED])
    monkeypatch.setattr(backfill_translations, "DATA_PATH", data_path)

    exit_code = backfill_translations.main()

    assert exit_code == 0
    mock_translate.assert_not_called()


@patch("scripts.backfill_translations.time.sleep")
@patch("scripts.backfill_translations.translate.translate_to_ko")
def test_main_is_idempotent_for_already_succeeded_items(mock_translate, mock_sleep, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_MISSING_FIELD])
    monkeypatch.setattr(backfill_translations, "DATA_PATH", data_path)
    mock_translate.return_value = "첫번역"

    backfill_translations.main()  # 1차 실행
    mock_translate.reset_mock()
    mock_translate.return_value = "두번째번역"

    backfill_translations.main()  # 2차 실행

    mock_translate.assert_not_called()  # 이미 번역된 항목은 다시 안 부름
    saved = fetch_news.load_existing(data_path)
    assert saved[0]["title_ko"] == "첫번역"


@patch("scripts.backfill_translations.time.sleep")
@patch("scripts.backfill_translations.translate.translate_to_ko")
def test_main_saves_progress_incrementally_on_interruption(mock_translate, mock_sleep, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    items = [
        {
            "guid": str(i), "title": f"T{i}", "link": f"http://x/{i}",
            "pubDate": "Wed, 15 Jul 2026 10:00:00 GMT", "category": "Macro",
        }
        for i in range(1, 13)  # 12개 — SAVE_EVERY(10)보다 많게 만들어 중간 저장을 유도
    ]
    fetch_news.save(data_path, items)
    monkeypatch.setattr(backfill_translations, "DATA_PATH", data_path)
    mock_translate.return_value = "번역됨"
    # 10번째 항목까지는 정상 진행되다가, 11번째 항목 처리 후 sleep 도중 강제 중단됐다고 가정
    mock_sleep.side_effect = [None] * 10 + [KeyboardInterrupt()]

    with pytest.raises(KeyboardInterrupt):
        backfill_translations.main()

    saved = fetch_news.load_existing(data_path)
    translated_so_far = [item for item in saved if item.get("title_ko")]
    assert len(translated_so_far) >= 10  # 중단 전 10개(SAVE_EVERY 주기)는 이미 저장돼 있어야 함
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/test_backfill_translations.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_translations'`

- [ ] **Step 3: `scripts/backfill_translations.py` 구현**

```python
import sys
import time

from scripts import translate
from scripts.fetch_news import DATA_PATH, load_existing, save

# 검증되지 않은 보수적 기본값 — DeepL의 실제 rate-limit에 근거한 값이 아니다(설계 문서
# "확인이 필요한 가정" 참고). 그래도 rate-limit에 걸려 번역이 실패하면 아래 멱등 재시도
# 설계 덕에 다음 실행 때 자연 복구된다.
SLEEP_BETWEEN_CALLS_SECONDS = 0.5

# 중간 저장 주기. 100여 개를 순차 처리하는 동안 GitHub Actions 러너가 강제 종료되는 등으로
# 중단돼도, 끝까지 기다리지 않고 주기적으로 저장해 이미 번역된 만큼은 보존한다(전부 끝나야만
# 저장되는 구조였다면 중단 시 그때까지 소비한 번역 예산이 통째로 유실됨).
SAVE_EVERY = 10


def main() -> int:
    items = load_existing(DATA_PATH)
    pending = [item for item in items if not item.get("title_ko")]

    if not pending:
        print("backfill_translations: nothing to backfill")
        return 0

    translated_count = 0
    for index, item in enumerate(pending, start=1):
        item["title_ko"] = translate.translate_to_ko(item["title"])
        if item["title_ko"] is not None:
            translated_count += 1
        if index % SAVE_EVERY == 0:
            save(DATA_PATH, items)
        time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    save(DATA_PATH, items)  # SAVE_EVERY로 안 나눠떨어진 나머지분 마무리 저장
    print(
        f"backfill_translations: attempted {len(pending)} items, "
        f"{translated_count}/{len(pending)} translated"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
pytest tests/ -v
```

Expected: PASS (전체 32개 — Task2까지 28개 + 이번에 4개 추가)

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_translations.py tests/test_backfill_translations.py
git commit -m "feat: add idempotent one-time backfill script for existing news items"
```

---

### Task 4: GitHub Actions 워크플로우

**Files:**
- Modify: `.github/workflows/fetch-news.yml`
- Create: `.github/workflows/backfill-translations.yml`

**Interfaces:**
- Consumes: Task 2의 `python -m scripts.fetch_news`(이제 `DEEPL_API_KEY` 환경변수를 읽음),
  Task 3의 `python -m scripts.backfill_translations`
- Produces: 없음 (인프라 파일)

- [ ] **Step 1: `fetch-news.yml`의 "Fetch news" 스텝에 시크릿 주입**

기존 스텝:

```yaml
      - name: Fetch news
        run: python -m scripts.fetch_news
```

을 아래로 교체:

```yaml
      - name: Fetch news
        env:
          DEEPL_API_KEY: ${{ secrets.DEEPL_API_KEY }}
        run: python -m scripts.fetch_news
```

파일의 나머지 부분(트리거, concurrency, 커밋 스텝 등)은 변경하지 않는다.

- [ ] **Step 2: `backfill-translations.yml` 신규 작성**

```yaml
name: Backfill Translations

on:
  workflow_dispatch: {}

concurrency:
  group: fetch-news
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  backfill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Backfill translations
        env:
          DEEPL_API_KEY: ${{ secrets.DEEPL_API_KEY }}
        run: python -m scripts.backfill_translations

      - name: Commit and push if changed
        run: |
          if ! git diff --quiet -- data/news.json; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add data/news.json
            git commit -m "chore: backfill Korean translations"
            git push
          else
            echo "Nothing to backfill"
          fi
```

- [ ] **Step 3: YAML 문법 검증**

이 프로젝트에는 `pyyaml`이 상시 의존성으로 설치돼 있지 않다(requirements.txt에 없음, 의도적
— 검증 스크립트 실행 시에만 필요). `.venv`에 없으면 임시로 설치한다:

```bash
source .venv/bin/activate
python3 -c "import yaml" 2>/dev/null || pip install --quiet pyyaml
python3 -c "
import yaml
yaml.safe_load(open('.github/workflows/fetch-news.yml'))
yaml.safe_load(open('.github/workflows/backfill-translations.yml'))
print('valid yaml')
"
```

Expected: `valid yaml` 출력. `pyyaml`은 검증용 임시 도구일 뿐이므로 `requirements.txt`에는
추가하지 않는다(이 프로젝트의 상시 의존성이 아님).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/fetch-news.yml .github/workflows/backfill-translations.yml
git commit -m "ci: inject DEEPL_API_KEY into fetch workflow, add one-time backfill workflow"
```

(실제 동작 검증은 Task 6에서 원격 저장소에 push한 뒤 진행한다 — 로컬에서는 시크릿을 쓸 수
없다.)

---

### Task 5: 프론트엔드 — 한글 제목 표시 + 폴백

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `data/news.json`의 각 항목에 새로 추가된 `title_ko` 필드(있을 수도 없을 수도,
  값이 `null`일 수도 있음)
- Produces: 없음 (화면)

- [ ] **Step 1: 제목 렌더링 로직 수정**

`render()` 함수 안의 `filtered.forEach(function(item){ ... })` 블록에서, 아래 부분을:

```js
      title.style.textDecoration = 'none';
      title.textContent = item.title;
```

아래로 교체:

```js
      title.style.textDecoration = 'none';
      if (item.title_ko) {
        title.textContent = item.title_ko;
      } else {
        title.textContent = item.title;
        title.lang = 'en';
      }
```

파일의 나머지 부분(가림막, 카테고리 탭, KST 변환, 60초 폴링, visibilitychange 등)은 변경하지
않는다.

- [ ] **Step 2: 로컬 브라우저로 수동 확인**

```bash
python3 -m http.server 8000
```

`data/news.json`에 있는 실제 데이터로(아직 `title_ko`가 없는 기존 항목들이 대부분일 것) 확인:

Expected 체크리스트:
- 아직 번역 안 된 항목(→ Task 6에서 백필 전)은 영어 원문이 그대로 보임
- 브라우저 개발자 도구로 해당 `<a class="title">` 요소를 확인해 `lang="en"`이 실제로 붙어
  있는지 확인 (Elements 탭에서 직접 확인)
- 기존 체크리스트(가림막·카테고리 필터·KST 시간·마지막 갱신)가 여전히 정상 동작하는지 재확인
  (이번 변경이 그 부분들을 건드리지 않았으므로 회귀 없어야 함)

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: display Korean title with English fallback and lang attribute"
```

(`title_ko`가 채워진 상태에서 실제로 한글이 보이는지는 Task 6에서 실제 번역 데이터가 들어온
뒤 배포된 페이지로 확인한다.)

---

### Task 6: 배포 — 실제 DeepL API 검증 + 백필 실행

**Files:** 없음 (배포 태스크)

**Interfaces:**
- Consumes: Task 1~5에서 만든 전체 변경사항
- Produces: 없음 (기존 운영 중인 news-flow 저장소·Pages에 반영)

**참고:** 이 태스크는 `docs/superpowers/plans/2026-07-16-financialjuice-news-flow.md`의
"Task 7: 원격 저장소 생성 및 배포"와 다르다 — 그건 새 공개 저장소를 만드는 태스크였고, 이건
이미 존재하고 10분마다 크론이 도는 **라이브** `news-flow` 저장소의 `main`에 새 커밋을 얹고
push하는 작업이다.

**⚠️ Step 3(push) 전에는 반드시 사용자에게 진행 상황을 알리고 확인받는다.** 새 저장소를
만드는 것만큼 되돌리기 어려운 건 아니지만, 이 push부터 DeepL 무료 한도(월 50만자)를 실제로
소비하기 시작하고, 이미 자동으로 도는 10분 크론에 즉시 영향을 준다는 점에서 나름의 비가역성이
있다 — Task 1~5(로컬 커밋까지)는 자유롭게 진행해도 되지만, Step 3의 push는 별도 확인
지점으로 둔다. subagent 실행자는 "Task 1~5를 로컬에 커밋했다"는 사실 보고만으로 Step 3을
자동 진행하지 말 것 — 실제로 사용자의 응답을 받은 뒤에만 push한다.

- [ ] **Step 1: 로컬 main에 병합**

```bash
git checkout main
git merge --ff-only <이 계획을 구현한 브랜치>
```

(구현을 별도 브랜치/worktree에서 진행했다면 병합, 같은 브랜치에서 바로 진행했다면 스킵)

- [ ] **Step 2: 전체 테스트 재확인**

```bash
source .venv/bin/activate
pytest tests/ -v
```

Expected: 전체 통과(32개).

- [ ] **Step 3: 사용자에게 확인받은 뒤 push**

사용자에게 "Task 1~5 로컬 커밋 완료, 이제 라이브 저장소에 push해 DeepL 번역을 실제로
가동해도 될지" 확인받는다. 이 태스크를 실행하는 주체가 subagent라면 여기서 멈추고 상위
세션에 확인을 요청한다(자동 진행 금지).

```bash
git push
```

- [ ] **Step 4: `fetch-news.yml` 수동 트리거 — 실제 DeepL API 첫 검증**

먼저 트리거 직후의 실행을 특정해 run id를 확보한다(트리거 이후 10분 크론이 끼어들어도 엉뚱한
실행의 로그를 보지 않도록):

```bash
gh workflow run fetch-news.yml
sleep 5  # 새 실행이 목록에 등록될 시간
RUN_ID=$(gh run list --workflow=fetch-news.yml --limit 1 --json databaseId --jq '.[0].databaseId')
echo "watching run: $RUN_ID"
for i in $(seq 1 12); do
  run_status=$(gh run view "$RUN_ID" --json status --jq '.status')
  echo "attempt $i: status=$run_status"
  if [ "$run_status" = "completed" ]; then break; fi
  sleep 10
done
RUN_CONCLUSION=$(gh run view "$RUN_ID" --json conclusion --jq '.conclusion')
echo "conclusion: $RUN_CONCLUSION"
gh run view "$RUN_ID" --log | grep -i "translated\|no new items\|title_ko\|Error"
```

Expected: **먼저 `$RUN_CONCLUSION`이 `success`인지 확인한다 — 이게 판정의 1차 근거다.**
그 다음 로그를 보되, 두 가지 정상 케이스를 구분한다: (a) 로그에 `N/M translated`가 보이면
번역이 실제로 시도된 것 — 이때 `N`이 1 이상이면 스펙 가정이 맞다는 뜻. (b) 로그에
`no new items, nothing to do`만 보이고 `translated` 문구가 없으면, 트리거 시점에 마침 새
뉴스가 없어서 번역 자체가 시도되지 않은 것뿐이다 — **이건 정상이지 실패가 아니다.** 이
경우 최대 2회까지만 몇 분 간격으로 재트리거해본다(`gh workflow run fetch-news.yml`부터
반복). 그래도 계속 "no new items"만 나오면 무한정 재시도하지 말고, 자동 크론이 다음 주기에
새 뉴스를 잡을 때까지 기다렸다가 `gh run list --workflow=fetch-news.yml --json
conclusion,createdAt --limit 5`로 최근 자동 실행들의 로그를 나중에 확인하는 쪽으로 전환한다
— 이건 실패 처리 루프가 아니라 그냥 "지금 당장 신규 뉴스가 없을 뿐"이므로 서두를 이유가
없다.

- **`$RUN_CONCLUSION`이 `success`가 아니거나, 신규 항목이 있었는데도 번역 개수가 계속
  `0/N`이면**(후자는 "확인이 필요한 가정"이 틀렸다는 뜻 — (a)/(b) 중 어느 쪽인지 로그로 먼저
  구분한 다음에만 이 분기로 온다): `gh run view "$RUN_ID" --log`로 상세 에러를 확인해 DeepL의
  실제 요청/응답 스펙과
  `scripts/translate.py`의 가정이 어디서 다른지 찾는다. 흔한 후보는 엔드포인트 URL
  (`api-free` vs `api`), 인증 헤더 형식, `target_lang` 값 표기. **TDD 순서를 지킨다** —
  먼저 `tests/test_translate.py`의 모킹을 실제로 확인된 새 스펙에 맞게 고쳐 그 테스트가
  기존 구현으로는 실패하는지 확인한 뒤, `scripts/translate.py`를 고쳐 통과시킨다. 커밋·push
  후 이 스텝을 재시도한다. **이 수정-재시도는 최대 2회까지만 자체적으로 진행한다** — 그래도
  같은 문제가 반복되면 자체 판단으로 계속 시도하지 말고 사용자에게 상황을 보고하고 중단한다
  (라이브 크론이 10분마다 도는 상태에서 원인 불명인 채로 반복 수정을 push하는 것 자체가
  위험이므로).

- [ ] **Step 5: `backfill-translations.yml` 수동 트리거**

```bash
gh workflow run backfill-translations.yml
for i in $(seq 1 30); do
  run_status=$(gh run list --workflow=backfill-translations.yml --limit 1 --json status --jq '.[0].status')
  echo "attempt $i: status=$run_status"
  if [ "$run_status" = "completed" ]; then break; fi
  sleep 10
done
gh run list --workflow=backfill-translations.yml --limit 1 --json status,conclusion
```

Expected: `completed`/`success`. 100여 개 항목을 순차 번역하므로(호출당 0.5초+API 응답
시간) 수 분 걸릴 수 있다 — 최대 300초까지 기다린다(루프 30회×10초).

- [ ] **Step 6: 배포된 페이지에서 실제 확인**

```bash
git pull
curl -s https://mlovewho7-afk.github.io/news-flow/data/news.json | python3 -c "
import json, sys
items = json.load(sys.stdin)
with_ko = [i for i in items if i.get('title_ko')]
print(f'{len(with_ko)}/{len(items)} items have title_ko')
print('sample:', with_ko[0]['title_ko'] if with_ko else 'NONE')
"
```

Expected: 대부분(전부는 아닐 수 있음 — 개별 실패 가능) 항목에 `title_ko`가 채워져 있고,
샘플이 실제 한글 문장으로 보임.

브라우저로 `https://mlovewho7-afk.github.io/news-flow/` 접속해 실제로 한글 제목이 보이는지,
Task 5에서 다 못 했던 "번역된 상태에서의" 육안 확인을 마무리한다.

- [ ] **Step 7: 원장에 기록**

이 세션이 subagent-driven-development로 진행 중이라면 `.superpowers/sdd/progress.md`에
Task 6 완료를 기록하고, DeepL 스펙 가정이 실제로 맞았는지/수정이 필요했는지도 함께 남긴다
(다음에 비슷한 통합을 할 때 참고할 수 있도록).

---

## 실행 순서 요약

Task 1 → (Task 2, Task 3 병행 가능, 둘 다 Task 1에만 의존) → Task 4(Task 2·3의 파일명을
참조하므로 그 둘이 끝난 뒤) → Task 5(독립적이라 Task 1 이후 아무 때나 가능하지만 편의상 Task 4
다음에 배치) → Task 6(반드시 마지막, 1~5가 모두 로컬에 커밋된 뒤).

<!-- spec-review: passed lenses=3 date=2026-07-16 -->
