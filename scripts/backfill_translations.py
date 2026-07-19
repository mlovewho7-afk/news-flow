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
