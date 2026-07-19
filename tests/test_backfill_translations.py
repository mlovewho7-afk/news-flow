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
