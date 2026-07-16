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
