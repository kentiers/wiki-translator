import json
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from wiki_translator.auth import AuthManager
from wiki_translator.gemini import GeminiTranslatorClient


@pytest.fixture
def auth(tmp_path):
    db = tmp_path / 'accounts.db'
    connection = sqlite3.connect(db)
    connection.execute('CREATE TABLE auth_credentials (id INTEGER, provider TEXT, data TEXT, updated_at INTEGER)')
    for i in (1, 2):
        data = dict(access='fake-access', refresh='fake-refresh', projectId='fake', expires=int((time.time()+3600)*1000))
        connection.execute('INSERT INTO auth_credentials VALUES (?, ?, ?, 0)', (i, 'google-antigravity', json.dumps(data)))
    connection.commit()
    connection.close()
    return AuthManager(db_path=db)


def test_quota_cooldown_survives_reload_and_recovers(auth):
    client = GeminiTranslatorClient(auth_manager=auth, thinking_level='low')
    client.api_key = None
    attempts = []
    def request(**kwargs):
        ident = kwargs['cred'].id
        attempts.append(ident)
        if ident == 1:
            raise HTTPError('https://example.invalid', 429, 'quota', {'Retry-After': '120'}, None)
        return 'Draf lengkap.'
    with patch.object(client, '_translate_antigravity', side_effect=request):
        client.translate_section('A')
        client.translate_section('B')
    assert attempts == [1, 2, 2]
    assert auth.load_credentials()[0].is_exhausted
    with patch('wiki_translator.auth.time.time', return_value=time.time()+121):
        assert not auth.load_credentials()[0].is_exhausted


@pytest.mark.parametrize('status', [401, 403, 429, 503])
def test_failure_moves_to_next_account(auth, status):
    client = GeminiTranslatorClient(auth_manager=auth, thinking_level='low')
    client.api_key = None
    error = HTTPError('https://example.invalid', status, 'fake error', {}, None)
    with patch.object(client, '_translate_antigravity', side_effect=[error, 'Draf']), patch.object(auth, 'refresh_access_token', return_value=None), patch('wiki_translator.gemini.time.sleep'):
        assert client.translate_section('A') == 'Draf'


def test_all_accounts_unavailable_fails_without_reusing_them(auth):
    client = GeminiTranslatorClient(auth_manager=auth, thinking_level='low')
    client.api_key = None
    with patch.object(client, '_translate_antigravity', side_effect=HTTPError('https://example.invalid', 429, 'quota', {}, None)) as request, patch('wiki_translator.gemini.time.sleep'):
        with pytest.raises(RuntimeError):
            client.translate_section('A')
        assert request.call_count == 2


def test_rotated_refresh_token_is_persisted(auth):
    credential = auth.load_credentials()[0]
    response = SimpleNamespace(read=lambda: json.dumps(dict(access_token='new-fake', refresh_token='rotated-fake', expires_in=3600)).encode())
    with patch('wiki_translator.auth.urllib.request.urlopen') as request:
        request.return_value.__enter__.return_value = response
        assert auth.refresh_access_token(credential) == 'new-fake'
    assert auth.load_credentials()[0].refresh_token == 'rotated-fake'


def test_omp_refresh_uses_selected_account_and_does_not_print_tokens(auth, capsys):
    auth.use_omp_refresh = True
    credential = auth.load_credentials()[1]
    def refresh(command, **kwargs):
        assert command == ['rtk', 'omp', 'token', 'google-antigravity', '--account', '2', '--force-refresh']
        assert kwargs['stdout'] is not None and kwargs['stderr'] is not None
        credential.access_token = 'updated-fake'
        auth._persist_token_update(credential)
        return SimpleNamespace(returncode=0, stdout=b'private-fake', stderr=b'')
    with patch('wiki_translator.auth.subprocess.run', side_effect=refresh):
        assert auth.refresh_access_token(credential) == 'updated-fake'
    assert capsys.readouterr().out == ''
