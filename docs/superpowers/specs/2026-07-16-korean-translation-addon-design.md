# 한글 번역 기능 추가 — 설계

**날짜:** 2026-07-16
**상태:** 설계 승인 대기
**선행 문서:** `2026-07-16-financialjuice-news-flow-design.md` (이미 배포된 v1 위에 얹는 증분 기능)

## 배경 (Why)

배포된 news-flow 사이트는 FinancialJuice 뉴스 제목을 영어 원문 그대로 보여준다. 사용자가 한글
번역을 요청함 — 수집 단계(서버측)에서 DeepL API로 번역해 저장하고, 화면엔 한글만 보여주는
방식으로 브레인스토밍에서 합의함.

## 확정된 결정 (대화 중 사용자가 직접 선택)

- **번역 시점:** 서버측(수집 단계) — GitHub Actions가 10분마다 새 항목을 수집할 때 함께 번역
- **번역 API:** DeepL API Free (`DEEPL_API_KEY`를 GitHub repository secret으로 이미 등록 완료,
  2026-07-16 04:36 UTC 확인됨 — `gh secret list` 출력으로 존재만 확인, 값은 확인하지 않음)
- **화면 표시:** 한글 제목만 표시(영어 원문 병기 안 함). 원문은 데이터에 그대로 보존되고
  링크는 항상 원문 기사로 연결됨(변경 없음)
- **기존 데이터 처리:** 이미 수집된 100여 개 항목도 1회 일괄 백필 번역
- **번역 실패 시:** FAIL-LOUD 아님 — 번역이 실패해도 수집 자체(뉴스 저장)는 계속 진행하고,
  해당 항목은 원문 제목으로 폴백 표시. v1의 "fetch/parse 실패는 FAIL-LOUD" 원칙과는 별개
  트레이드오프로 둔다 — 번역은 부가 기능이므로 번역 API 장애가 뉴스 수집 자체를 막아서는
  안 된다는 게 이 결정의 취지다. 단, "실패해도 계속 진행한다"는 것이 "그 실패를 아무도 모르게
  둔다"는 뜻은 아니다 — 아래 아키텍처 절에서 최소한의 로그 가시성을 둔다
- **DeepL 무료 한도 초과 리스크:** 실측 데이터(`data/news.json` 102건, 약 8시간분)로 계산하면
  하루 약 306건·29,292자, 월 환산 약 87.9만자로 무료 한도(월 50만자)의 약 1.76배다. **이
  리스크를 알고도 그대로 진행하기로 사용자가 결정함** — 한도를 넘으면 그 달 남은 기간은
  번역 API 호출이 실패하고(과금되는 게 아니라 요청이 거부됨) 위 폴백 규칙에 따라 그냥 영어
  제목으로 보인다. 실제로 문제가 되는지는 운영해보고 판단한다(MEASURE-FIRST) — 지금 카테고리
  제한이나 유료 전환 같은 대응을 미리 설계하지 않는다(YAGNI)

## ⚠️ 확인이 필요한 가정 (구현 착수 시 반드시 실측 검증)

DeepL API의 정확한 요청/응답 스펙(엔드포인트 URL, 인증 헤더 형식, 요청 바디 필드명, 응답
JSON 구조)은 이 세션에서 라이브 호출로 검증하지 않았다 — 아래는 일반적으로 알려진 사양을
근거로 한 설계이며, **구현 첫 태스크에서 실제 DeepL API를 한 번 호출해 이 가정이 맞는지
확인하고, 다르면 여기 반영을 수정한다.**

가정하는 사양:
- 엔드포인트: `POST https://api-free.deepl.com/v2/translate`
- 인증: 헤더 `Authorization: DeepL-Auth-Key {API_KEY}`
- 요청 바디(form-encoded): `text={원문}&target_lang=KO`
- 응답: `{"translations": [{"text": "번역문", "detected_source_language": "EN"}]}`
- 무료 플랜 요청 URL은 `api-free.deepl.com`이지 `api.deepl.com`(유료)이 아님 — 무료 키로
  유료 엔드포인트를 호출하면 인증 실패가 나므로 이 구분이 중요함

## 아키텍처

### 신규: `scripts/translate.py`

```python
def translate_to_ko(text: str) -> str | None:
    """DeepL로 한글 번역. 실패하면 예외를 던지지 않고 None을 반환한다
    (호출자가 원문 폴백 처리 — 번역 실패가 뉴스 수집을 막지 않는다는
    설계 결정의 구현)."""
```

- `DEEPL_API_KEY` 환경변수가 없거나 비어있으면 즉시 `None` 반환(API 호출 자체를 시도하지 않음
  — 로컬 개발 환경에서 키 없이도 나머지 파이프라인이 동작하게 함)
- API 호출 중 발생하는 모든 예외(`requests.RequestException`, 타임아웃, 4xx/5xx, 예상과 다른
  응답 JSON 구조, 한도 초과 포함)를 잡아 `None`으로 변환. 이 함수는 절대 예외를 밖으로 내보내지
  않는다(계약: 호출자는 이 함수가 항상 `str | None`을 반환한다고 믿을 수 있다). 실패 원인을
  세분화해 다르게 처리하지 않는다(YAGNI) — 대신 호출자가 성공/실패 "개수"를 세어 로그로
  남긴다(아래 참고), 원인 구분 없이도 "요즘 번역이 잘 안 되고 있다"는 신호는 로그에 남게 하는
  최소한의 가시성 장치다

### 수정: `scripts/fetch_news.py`

**신규 항목 식별 방법 (v1 함수 계약과의 접점):** v1의 `merge_new(existing, new_items) ->
tuple[list[dict], bool]`은 병합된 전체 리스트와 "변경 여부" bool만 반환하고, 어떤 항목이
새로 추가됐는지는 노출하지 않는다. 매 10분 fetch는 피드의 최신 스냅샷 전체(약 100개)를 다시
받아오므로, 만약 그 스냅샷 전체를 번역 대상으로 삼으면 이미 저장된 항목까지 매번 재번역
시도하게 되어 위에서 계산한 예산을 몇 배로 더 초과시킨다. 따라서 **번역은 `merge_new` 호출
전에, `main()`이 직접 계산한 "진짜 신규" 목록에만 적용한다**:

```python
existing = load_existing(DATA_PATH)
existing_guids = {item["guid"] for item in existing}
truly_new = [item for item in new_items if item["guid"] not in existing_guids]

if not truly_new:
    print("fetch_news: no new items, nothing to do")
    return 0

translated_count = 0
for item in truly_new:
    item["title_ko"] = translate_to_ko(item["title"])
    if item["title_ko"] is not None:
        translated_count += 1

merged, changed = merge_new(existing, truly_new)  # merge_new의 내부 dedup은 그대로 안전망으로 유지
save(DATA_PATH, merged)
print(f"fetch_news: wrote {len(merged)} items ({len(truly_new)} new, "
      f"{translated_count}/{len(truly_new)} translated)")
```

`merge_new`의 시그니처와 내부 로직(dedup, 정렬)은 그대로 둔다 — `main()`이 번역 대상만 미리
추려내는 책임을 갖고, `merge_new`는 여전히 최종 병합·정렬을 책임진다(관심사 분리 유지). 다만
이 방식은 "이미 존재하는 guid인지" 판정 로직이 `main()`의 `truly_new` 계산과 `merge_new`
내부에 사실상 동일한 형태로 두 번 존재하게 된다는 뜻이기도 하다 — 지금은 두 로직이 우연히
같아서 문제가 없지만, 둘 중 하나만(예: `merge_new`의 dedup 기준) 나중에 바뀌면 "번역 대상
선정"과 "실제 저장되는 신규 항목"이 미묘하게 어긋날 수 있다. 최악의 경우도 번역 API 호출
낭비나 일부 신규 항목의 번역 누락 정도이지 데이터 손상은 아니므로, 지금 이 중복을 없애는
리팩터링(예: `merge_new`가 골라낸 신규 항목을 반환하도록 시그니처를 바꾸는 것)까지는 하지
않는다(YAGNI) — 두 로직이 어긋나는 게 실제로 관찰되면 그때 다룬다.

기존 항목(이미 저장된 것)은 건드리지 않는다 — 재번역하지 않음, API 호출 낭비 방지.

번역 호출 실패는 파이프라인 종료 코드에 영향을 주지 않는다 — `main()`은 여전히 0으로 종료하고
데이터를 저장한다. 다만 위 로그 문구(`N/M translated`)가 GitHub Actions 실행 로그에 항상
남는다 — 이건 문제를 완전히 막는 장치가 아니라 **완화**일 뿐임을 분명히 해둔다. 이 로그는
누군가 GitHub Actions 탭을 능동적으로 열어봐야만 의미가 있는 수동적(passive) 신호다. 별도
알림 채널을 만들지는 않는다(YAGNI, 사용자가 명시적으로 "그냥 진행"을 택한 리스크 범위 안) —
그래서 "번역이 몇 주째 조용히 실패하는" 상황 자체는 여전히 가능하다. 다만 v1의 문제(원인조차
알 수 없는 침묵)와 달리, 이번엔 로그를 열어보기만 하면 "실패하고 있다"는 사실과 "몇 개나
실패했는지"는 즉시 확인 가능하다는 점에서 개선이다.

### 신규: `scripts/backfill_translations.py` (1회성)

```python
def main() -> int:
    """data/news.json의 모든 항목 중 title_ko가 없거나 None인 것만 찾아
    번역해 채운다. 이미 title_ko가 채워진 항목은 건드리지 않으므로,
    같은 스크립트를 여러 번 돌려도 이미 성공한 항목이 중복 번역되지
    않는다(IDEMPOTENT). 단, 직전 실행에서 번역이 실패해 title_ko가
    여전히 None으로 남은 항목은 재실행 시 다시 시도된다 — 이건 의도된
    재시도 동작이지, 멱등성 위반이 아니다(멱등성은 "이미 끝난 일을
    다시 안 한다"는 뜻이지 "실패한 일도 다시 안 한다"는 뜻이 아니다)."""
```

호출 사이에 짧은 지연(`time.sleep(0.5)` 정도)을 둔다. **이 값은 DeepL의 실제 요청 빈도
제한을 근거로 고른 게 아니다** — DeepL의 rate-limit 정책은 이 세션에서 조사하지 않았다(v1에서
FinancialJuice RSS 앞단 Cloudflare가 rate-limit을 건 전례가 있었지만, 그건 별개의 제3자
서비스라 DeepL에 그대로 적용할 근거가 안 된다). 그냥 "순차 호출을 조금 늦춰서 혹시 모를
제한을 피해보자"는 보수적인 기본값이다. 정교한 백오프·재시도 로직은 만들지 않는다(YAGNI) —
그래도 실패하면 위 재시도 가능한 멱등 설계로 다음 실행 때 자연스럽게 재시도된다.

`fetch_news.py`의 `load_existing`/`save`를 재사용해 원자적 쓰기를 그대로 활용한다. 이 스크립트는
10분 크론에 포함되지 않고, 아래 전용 워크플로우로 딱 한 번만 수동 실행한다.

### 신규: `.github/workflows/backfill-translations.yml`

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
      - run: pip install -r requirements.txt
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

**왜 별도 워크플로우 파일인가:** 기존 `fetch-news.yml`(10분 크론)에 조건부 모드를 넣는 대신
단일 목적 파일로 분리했다(FOCUSED). 이 파일은 백필이 끝나면 다시 쓸 일이 없지만, 나중에
번역이 실패한 항목이 쌓였을 때 재실행할 수 있는 안전한 재시도 도구로 남겨둔다(멱등이므로
몇 번을 실행해도 안전).

**왜 `fetch-news.yml`과 같은 concurrency 그룹(`fetch-news`)을 쓰는가:** 두 워크플로우 모두
`data/news.json`을 커밋+push한다. 10분 크론이 상시 도는 상태에서 백필을 수동 실행하면, 백필이
100여 건을 순차 번역하는 동안(수십 초~수 분) 크론이 먼저 push해버려 백필의 push가
non-fast-forward로 실패할 수 있다. 같은 concurrency 그룹으로 묶으면 GitHub Actions가 둘을
겹치지 않게 순서대로 실행해줘서 이 경합 자체가 발생하지 않는다.

### 수정: `.github/workflows/fetch-news.yml`

기존 "Fetch news" 스텝에 `DEEPL_API_KEY` 환경변수를 추가해야 번역이 동작한다:

```yaml
      - name: Fetch news
        env:
          DEEPL_API_KEY: ${{ secrets.DEEPL_API_KEY }}
        run: python -m scripts.fetch_news
```

### 수정: `index.html`

각 뉴스 행 렌더링 시 `item.title_ko || item.title`을 표시한다 — `title_ko`가 없거나(기존
데이터에 필드 자체가 없는 경우) `null`이면(번역 실패) 자동으로 영어 원문으로 폴백한다. 링크
(`item.link`)는 변경 없이 항상 원문 기사를 가리킨다.

## 범위 밖

- 카테고리 태깅 로직에는 영향 없음 — `categorize()`는 `financialjuice.py`의 `parse_items()`
  안에서 영어 원문 `title`로 이미 호출되고 결과가 `item["category"]`에 저장된다(v1 코드 확인
  완료). 이번 기능의 번역 삽입은 그 이후 `fetch_news.py` 단계에서 `item["title_ko"]`라는
  새 키만 추가할 뿐 `item["title"]`이나 `item["category"]`를 건드리지 않으므로, 호출 순서상
  분류는 항상 번역보다 먼저 끝나 있다. 한글 번역문을 분류 기준으로 바꾸도록 고치지 않는다
  (기존 키워드 목록이 영어 기준으로 만들어져 있고, 지금 이걸 바꿀 이유가 없음)
- 본문/설명 번역 없음 — `financialjuice.py`의 `parse_items()`가 애초에 RSS의 `<description>`
  요소를 파싱하지 않는다(guid/title/link/pubDate만 추출, v1 설계 그대로) — 즉 "본문이 비어있어
  번역 안 한다"가 아니라 "번역할 본문 필드 자체를 이 파이프라인이 다루지 않는다"가 정확한
  이유다. 제목만 번역 대상
- 번역 캐싱/재사용 없음 — 같은 제목이 반복돼도 재번역하지 않는 이유가 없는 한(guid가 다르면
  다른 기사이므로) 별도 캐시 계층을 만들지 않음(YAGNI)

## 검증 계획

- `translate.py`를 실제 DeepL API로 1회 호출해 위 "확인이 필요한 가정" 섹션의 스펙이 맞는지
  확인 — 다르면 이 문서와 구현을 함께 수정
- `DEEPL_API_KEY`가 없는 환경에서 `translate_to_ko()`가 API를 호출하지 않고 즉시 `None`을
  반환하는지 단위테스트로 확인
- 의도적으로 잘못된 키/URL로 호출해 예외가 함수 밖으로 새지 않고 `None`으로 변환되는지 확인
- `fetch_news.py`가 번역 실패(`None`)를 받아도 정상 종료(exit 0)하고 데이터를 저장하는지, 그리고
  로그에 `N/M translated` 같은 성공/실패 개수가 실제로 찍히는지 확인
- `fetch_news.py`가 이미 존재하는(기존) 항목은 번역 대상에서 제외하는지 — 즉 매 실행마다
  피드 전체(~100개)가 아니라 진짜 신규 항목에만 번역 API를 호출하는지 단위테스트로 확인
  (예산 계산의 전제가 되는 동작이므로 반드시 검증)
- `backfill_translations.py`를 두 번 연속 실행해, 첫 번째 실행에서 이미 성공적으로 번역된
  항목(`title_ko`가 채워진 것)은 두 번째 실행에서 다시 번역되지 않는지 확인(멱등성 — 실패해서
  `None`으로 남은 항목까지 두 번째 실행에서 그대로여야 한다는 뜻은 아님, 그런 항목은 재시도
  대상이라 값이 바뀔 수 있음)
- `index.html`의 `item.title_ko || item.title` 폴백 로직을, `title_ko`가 없는 항목(백필 전
  기존 데이터)과 `title_ko`가 `null`인 항목(번역 실패) 두 경우 모두에 대해 브라우저에서 실제로
  영어 원문이 표시되는지 확인 — 이 기능의 핵심 우아한 저하 계약이므로 happy path만으로 끝내지
  않는다
- GitHub Actions 실행 컨텍스트에서 `secrets.DEEPL_API_KEY`가 실제로 주입되는지, `fetch-news.yml`
  워크플로우를 1회 수동 트리거해 신규 항목에 `title_ko`가 채워지는지 확인(유닛테스트로는
  시크릿 주입 자체를 검증할 수 없음)
- 백필 워크플로우를 실제로 1회 수동 실행해 기존 데이터에 `title_ko`가 채워지는지, 실제 배포된
  페이지에서 한글 제목이 보이는지 확인

<!-- spec-review: passed lenses=3 date=2026-07-16 -->
