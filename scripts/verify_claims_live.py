"""Small live fidelity checks using the project's model and OMP auth adapter."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wiki_translator.article_quality import review_claims
from wiki_translator.gemini import GeminiTranslatorClient

source = ('Maria opposed the proposal. She mentored Anna. More than 200 women attended the course. '
          'The treatment may reduce pain. Maria also founded a publishing cooperative.')
faithful = ('Maria menentang usulan itu. Ia membimbing Anna. Lebih dari 200 perempuan mengikuti kursus tersebut. '
            'Pengobatan itu mungkin mengurangi nyeri. Maria juga mendirikan koperasi penerbitan.')
changed = ('Maria mendukung usulan itu. Anna membimbing Maria. Tepat 200 perempuan mengikuti kursus tersebut. '
           'Pengobatan itu pasti menghilangkan nyeri.')
client = GeminiTranslatorClient(preferred_model='gemini-3.8-flash', thinking_level='high')
results = {}
for name, draft in [('faithful', faithful), ('changed', changed)]:
    findings = review_claims(source, draft, client)
    results[name] = {'accepted': not findings, 'findings': findings}
print(json.dumps(results, ensure_ascii=False, indent=2))
passed = results['faithful']['accepted'] and not results['changed']['accepted']
passed = passed and any('Klaim ' in finding for finding in results['changed']['findings'])
sys.exit(0 if passed else 1)
