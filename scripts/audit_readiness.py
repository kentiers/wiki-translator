"""Offline readiness probes; never reads real credentials or calls a service."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wiki_translator.auth import AuthManager
from wiki_translator.article_reviewer import ArticleReviewer
from wiki_translator.awb_genfixes import GeneralFixesEngine, RegExTypoFixEngine
from wiki_translator.cli import WikiTranslatorCLI
from wiki_translator.gemini import GeminiTranslatorClient
from wiki_translator.syntax_balancer import WikitextSyntaxBalancer


def run():
    results = {}
    client = GeminiTranslatorClient(auth_manager=SimpleNamespace(), thinking_level="low")
    event = {"candidates": [{"content": {"parts": [{"text": "Kalimat belum selesai"}]}, "finishReason": "MAX_TOKENS"}]}
    results["max_tokens_returned_as_success"] = bool(client._parse_sse_response([
        "data: " + json.dumps(event), "",
    ]))
    cli = WikiTranslatorCLI.__new__(WikiTranslatorCLI)
    cli.syntax_balancer = WikitextSyntaxBalancer()
    section = SimpleNamespace(title="Lead", full_source="She opposed the proposal.", translated_content="Ia mendukung usulan tersebut.")
    results["reversed_meaning_passes_gate"] = cli._quality_gate([section])[0]
    review = ArticleReviewer().audit_translation_quality(section.translated_content, section.full_source, 'Uji lokal')
    results['reversed_meaning_review'] = {'score': review.overall_score, 'verdict': review.verdict}
    before = 'Pembuka.\n== Karier ==\nIa mendirikan koperasi. Ia memperjuangkan pendidikan perempuan.'
    after = 'Pembuka.\n== Karier ==\nIa mendirikan koperasi.'
    try:
        cli._check_saved_integrity(before, after)
        results["claim_loss_passes_save_gate"] = True
    except ValueError:
        results["claim_loss_passes_save_gate"] = False
    article = 'Pembuka.\n== Referensi ==\n<references/>\n== Riwayat penerbitan ==\nKLAIM_PENTING\n== Pranala luar ==\n* Tautan\n'
    results["appendix_reorder_loses_intervening_section"] = "KLAIM_PENTING" not in GeneralFixesEngine().reorder_appendices(article)
    results["automatic_spelling_output"] = RegExTypoFixEngine().fix_typos('Unta mempelajari tata bahasa secara sistematik.')
    with tempfile.TemporaryDirectory(dir="output") as tmp:
        db = Path(tmp) / "fake-auth.db"
        with sqlite3.connect(db) as connection:
            connection.execute('CREATE TABLE auth_credentials (id INTEGER, provider TEXT, data TEXT, updated_at INTEGER)')
            for i in (1, 2):
                data = {"access": "fake", "refresh": "fake", "projectId": "fake", "expires": int((time.time()+3600)*1000)}
                connection.execute('INSERT INTO auth_credentials VALUES (?, ?, ?, 0)', (i, 'google-antigravity', json.dumps(data)))
        connection.close()
        auth = AuthManager(db_path=db)
        client = GeminiTranslatorClient(auth_manager=auth, thinking_level="low")
        client.api_key = None
        attempts = []
        def request(**kwargs):
            attempts.append(kwargs['cred'].id)
            if kwargs['cred'].id == 1:
                raise HTTPError('https://example.invalid', 429, 'fake quota', None, None)
            return 'Terjemahan lengkap.'
        with patch.object(client, '_translate_antigravity', side_effect=request):
            client.translate_section('First')
            client.translate_section('Second')
        results['account_attempts_across_two_requests'] = attempts
    return results


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
