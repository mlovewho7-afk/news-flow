from unittest.mock import Mock, patch

import requests

from scripts import translate


def test_translate_to_ko_returns_none_when_key_missing(monkeypatch):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_translation_on_success(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.json.return_value = {
        "translations": [{"text": "안녕하세요", "detected_source_language": "EN"}]
    }
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    result = translate.translate_to_ko("Hello")

    assert result == "안녕하세요"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"]["text"] == "Hello"
    assert call_kwargs["data"]["target_lang"] == "KO"
    assert call_kwargs["headers"]["Authorization"] == "DeepL-Auth-Key fake-key:fx"


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_http_error(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("456 quota exceeded")
    mock_post.return_value = mock_response

    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_network_exception(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_post.side_effect = requests.ConnectionError("network down")

    assert translate.translate_to_ko("Hello") is None


@patch("scripts.translate.requests.post")
def test_translate_to_ko_returns_none_on_malformed_response(mock_post, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key:fx")
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {"unexpected": "shape"}
    mock_post.return_value = mock_response

    assert translate.translate_to_ko("Hello") is None
