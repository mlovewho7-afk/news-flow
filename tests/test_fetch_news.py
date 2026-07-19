import json
from unittest.mock import patch

from scripts import fetch_news
from scripts import translate

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
