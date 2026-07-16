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
