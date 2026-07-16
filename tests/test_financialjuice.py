import pytest
from unittest.mock import Mock, patch

import requests

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
