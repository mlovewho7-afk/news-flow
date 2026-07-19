from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import pytest

from scripts import backfill_translations, fetch_news


def _pubdate(minutes_ago):
    return format_datetime(datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), usegmt=True)


ITEM_TRANSLATED = {
    "guid": "1", "title": "A", "link": "http://x/1",
    "pubDate": _pubdate(5), "category": "Macro", "title_ko": "가",
}
ITEM_MISSING_FIELD = {
    "guid": "2", "title": "B", "link": "http://x/2",
    "pubDate": _pubdate(5), "category": "Bonds",
}
ITEM_FAILED = {
    "guid": "3", "title": "C", "link": "http://x/3",
    "pubDate": _pubdate(5), "category": "FX", "title_ko": None,
}
ITEM_OLD_UNTRANSLATED = {
    "guid": "4", "title": "D", "link": "http://x/4",
    "pubDate": _pubdate(45), "category": "Macro",  # BACKFILL_WINDOW_MINUTES(30분) 밖
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
            "pubDate": _pubdate(5), "category": "Macro",
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


@patch("scripts.backfill_translations.time.sleep")
@patch("scripts.backfill_translations.translate.translate_to_ko")
def test_main_excludes_items_outside_backfill_window(mock_translate, mock_sleep, tmp_path, monkeypatch):
    data_path = tmp_path / "news.json"
    fetch_news.save(data_path, [ITEM_MISSING_FIELD, ITEM_OLD_UNTRANSLATED])
    monkeypatch.setattr(backfill_translations, "DATA_PATH", data_path)
    mock_translate.return_value = "번역됨"

    exit_code = backfill_translations.main()

    assert exit_code == 0
    mock_translate.assert_called_once_with(ITEM_MISSING_FIELD["title"])  # 오래된 항목은 대상 아님
    saved = fetch_news.load_existing(data_path)
    saved_by_guid = {item["guid"]: item for item in saved}
    assert saved_by_guid["2"]["title_ko"] == "번역됨"
    assert saved_by_guid["4"].get("title_ko") is None  # 30분 밖이라 그대로 남음
