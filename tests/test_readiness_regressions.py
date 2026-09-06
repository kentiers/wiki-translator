import json
from types import SimpleNamespace

import pytest

from wiki_translator.awb_genfixes import GeneralFixesEngine
from wiki_translator.gemini import GeminiTranslatorClient


@pytest.mark.parametrize('reason', ['MAX_TOKENS', 'LENGTH'])
def test_token_limited_stream_is_not_a_successful_translation(reason):
    client = GeminiTranslatorClient(auth_manager=SimpleNamespace(), thinking_level='low')
    event = {'candidates': [{'content': {'parts': [{'text': 'Kalimat terpotong'}]}, 'finishReason': reason}]}
    assert client._parse_sse_response(['data: ' + json.dumps(event), '']) == ''


@pytest.mark.parametrize('tail', ['', '\n== Pranala luar ==\n* Tautan'])
def test_appendices_do_not_discard_later_non_appendix_sections(tail):
    text = 'Pembuka.\n== Referensi ==\n<references/>\n== Riwayat penerbitan ==\nKlaim penting.' + tail
    assert GeneralFixesEngine().reorder_appendices(text) == text


@pytest.mark.parametrize('tail', [[], ['data: {invalid json}', '', 'data: [DONE]'], ['data: {"error":{"message":"failed"}}', '', 'data: [DONE]']])
def test_incomplete_or_broken_stream_is_rejected(tail):
    client = GeminiTranslatorClient(auth_manager=SimpleNamespace(), thinking_level='low')
    event = {'candidates': [{'content': {'parts': [{'text': 'Sebagian draf.'}]}}]}
    assert client._parse_sse_response(['data: ' + json.dumps(event), ''] + tail) == ''


def test_valid_json_response_with_stop_is_accepted():
    client = GeminiTranslatorClient(auth_manager=SimpleNamespace(), thinking_level='low')
    event = {'candidates': [{'content': {'parts': [{'text': '```json\n{"ok":true}\n```'}]}, 'finishReason': 'STOP'}]}
    assert client._parse_sse_response(['data: ' + json.dumps(event), '']) == '{"ok":true}'
