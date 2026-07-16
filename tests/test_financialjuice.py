import pytest

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
