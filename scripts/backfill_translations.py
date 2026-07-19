import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from scripts import translate
from scripts.fetch_news import DATA_PATH, load_existing, save

# 검증되지 않은 보수적 기본값 — DeepL의 실제 rate-limit에 근거한 값이 아니다(설계 문서
# "확인이 필요한 가정" 참고). 그래도 rate-limit에 걸려 번역이 실패하면 아래 멱등 재시도
# 설계 덕에 다음 실행 때 자연 복구된다.
SLEEP_BETWEEN_CALLS_SECONDS = 0.5

# 중간 저장 주기. 많은 항목을 순차 처리하는 동안 GitHub Actions 러너가 강제 종료되는 등으로
# 중단돼도, 끝까지 기다리지 않고 주기적으로 저장해 이미 번역된 만큼은 보존한다(전부 끝나야만
# 저장되는 구조였다면 중단 시 그때까지 소비한 번역 예산이 통째로 유실됨).
SAVE_EVERY = 10

# 사용자 요청으로 추가된 제한 — 오래된 이력 전체(수백 건)를 한꺼번에 번역하지 않고, 최근
# 게시된 항목만 백필 대상으로 삼는다. 이 창을 벗어난 미번역 항목은 원문 영어로 남는다(의도된
# 동작이지, 버그가 아니다). 이후 발행되는 새 기사는 fetch_news.py의 10분 주기 파이프라인이
# 알아서 번역하므로, 이 스크립트는 "최근에 놓친 것만 메꾸는" 좁은 역할로 축소됐다.
BACKFILL_WINDOW_MINUTES = 30


def main() -> int:
    items = load_existing(DATA_PATH)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=BACKFILL_WINDOW_MINUTES)
    pending = [
        item
        for item in items
        if not item.get("title_ko") and parsedate_to_datetime(item["pubDate"]) >= cutoff
    ]

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
