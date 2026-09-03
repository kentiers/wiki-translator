"""
Unit tests for StubGenerator (wiki_translator/stub_generator.py).
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.stub_generator import (
    StubGenerator,
    default_stub_generator,
)


class TestStubGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = StubGenerator()
        self.generator._translator_initialized = True
        self.generator.translator_client = None
    @patch("urllib.request.urlopen")
    def test_fetch_en_lead_wikitext(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "pages": [
                    {
                        "title": "Kevin Macdonald (director)",
                        "revisions": [
                            {
                                "slots": {
                                    "main": {
                                        "content": "{{Infobox person\n| name = Kevin Macdonald\n}}\n'''Kevin Macdonald''' (born 28 October 1967) is a Scottish director.<ref>Source</ref>"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        lead = self.generator.fetch_en_lead_wikitext("Kevin Macdonald (director)")
        self.assertIn("Kevin Macdonald", lead)
        self.assertIn("Scottish director", lead)

    def test_extract_infobox(self):
        wikitext = (
            "{{Infobox film\n| title = Touching the Void\n| director = Kevin Macdonald\n}}\n"
            "'''Touching the Void''' is a 2003 docudrama film."
        )
        infobox = self.generator.extract_infobox(wikitext)
        self.assertIn("{{Infobox film", infobox)
        self.assertIn("Touching the Void", infobox)

    def test_extract_lead_paragraphs(self):
        wikitext = (
            "{{Infobox person\n| name = Kevin\n}}\n\n"
            "'''Kevin Macdonald''' (born 28 October 1967) is a Scottish director.<ref>Ref 1</ref>\n\n"
            "He won the Academy Award for Best Documentary Feature.<ref>Ref 2</ref>\n\n"
            "== Early life ==\nSome text."
        )
        paras = self.generator.extract_lead_paragraphs(wikitext)
        self.assertEqual(len(paras), 2)
        self.assertIn("Kevin Macdonald", paras[0])
        self.assertIn("Academy Award", paras[1])

    def test_determine_stub_template(self):
        t1 = self.generator.determine_stub_template("Kevin Macdonald", "sutradara film terkenal")
        self.assertEqual(t1, "{{sutradara-stub}}")

        t2 = self.generator.determine_stub_template("The Mauritanian", "film drama hukum tahun 2021")
        self.assertEqual(t2, "{{film-stub}}")

        t3 = self.generator.determine_stub_template("John Doe", "pemeran dalam berbagai serial televisi")
        self.assertEqual(t3, "{{pemeran-stub}}")

        t4 = self.generator.determine_stub_template("Sample Book", "novel fiksi ilmiah karya...")
        self.assertEqual(t4, "{{buku-stub}}")

        t5 = self.generator.determine_stub_template("Random Topic", "artikel ringkas lainnya")
        self.assertEqual(t5, "{{stub}}")

    def test_determine_target_title_bare_priority(self):
        with patch.object(self.generator, "determine_target_title", wraps=self.generator.determine_target_title) as mock_m:
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps({
                    "query": {
                        "pages": {
                            "-1": {"title": "Kevin Macdonald", "missing": ""},
                            "-2": {"title": "Kevin Macdonald (sutradara)", "missing": ""},
                        }
                    }
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                # If bare title does not exist, use bare title!
                target = self.generator.determine_target_title("Kevin Macdonald (director)")
                self.assertEqual(target, "Kevin Macdonald")

    def test_determine_target_title_uses_disambiguator_when_existing(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "query": {
                    "pages": {
                        "123": {
                            "title": "Kevin Macdonald",
                            "pageprops": {"disambiguation": ""},
                        }
                    }
                }
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
    def test_stub_generator_connected_with_qa_pipeline(self):
        custom_lead = (
            "{{Infobox person\n| name = Test Person\n}}\n\n"
            "'''Test Person''' adalah seorang tokoh dan sutradara yang telah memenangkan berbagai penghargaan perfilman "
            "dan menghasilkan berbagai karya penting di industri perfilman internasional selama beberapa dekade terakhir. "
            "Karya-karyanya meliputi berbagai film dokumenter dan film naratif yang mendapatkan sambutan positif dari para kritikus film dunia.\n\n"
            "== Referensi ==\n{{reflist}}"
        )
        res = self.generator.generate_stub(
            en_title="Test Person",
            id_title="Test Person",
            custom_lead=custom_lead,
        )
        self.assertIn("qa_report", res)
        self.assertIsNotNone(res["qa_report"])
        self.assertTrue(res["is_qa_approved"])

    def test_determine_categories(self):
        cats = self.generator.determine_categories(
            "Kevin Macdonald",
            "sutradara film skotlandia {{Birth date and age|df=yes|1967|10|28}}\n[[Category:Scottish film directors]]",
        )
        self.assertIn("[[Kategori:Kelahiran 1967]]", cats)
        self.assertIn("[[Kategori:Orang hidup]]", cats)
        self.assertIn("[[Kategori:Sutradara film Skotlandia]]", cats)
    def test_translate_lead_prose(self):
        en_lead = "'''Kevin Macdonald''' (born 28 October 1967) is a Scottish director. He won the Academy Award."
        # Test offline rule-based fallback specifically
        offline_gen = StubGenerator(translator_client=None)
        offline_gen._translator_initialized = True
        id_lead = offline_gen.translate_lead_prose(en_lead, "Kevin Macdonald")
        self.assertIn("'''Kevin Macdonald'''", id_lead)
        self.assertIn("(lahir 28 Oktober 1967)", id_lead)
        self.assertTrue(
            "adalah seorang sutradara asal Skotlandia" in id_lead
            or "adalah seorang sutradara Skotlandia" in id_lead
        )
        self.assertIn("Ia memenangkan", id_lead)

    def test_translate_lead_prose_offline_token_and_year_gap(self):
        offline_gen = StubGenerator(translator_client=None)
        offline_gen._translator_initialized = True
        raw = "a documentary about the 1972 [[Munich massacre|murder of 11 Israeli athletes]], which won him the [[Academy Award for Best Documentary Feature]]"
        result = offline_gen.translate_lead_prose(raw, "Kevin Macdonald")
        self.assertIn("tentang [[Pembantaian München|pembunuhan 11 atlet Israel]] pada tahun 1972", result)
        self.assertNotIn("tentang 1972", result)

    def test_translate_lead_prose_with_llm_client(self):
        mock_client = MagicMock()
        mock_client.translate_section.return_value = (
            "'''Kevin Macdonald''' (lahir 28 Oktober 1967) adalah seorang sutradara film asal Skotlandia. "
            "Film-film karyanya meliputi ''[[One Day in September]]'' (1999), sebuah film dokumenter tentang "
            "pembunuhan 11 atlet Israel pada tahun 1972 yang memenangkannya [[Academy Award untuk Film Dokumenter Terbaik]]."
        )
        llm_gen = StubGenerator(translator_client=mock_client)
        raw = "'''Kevin Macdonald''' (born 28 October 1967) is a Scottish film director. His films include ''[[One Day in September]]'' (1999), a documentary about the 1972 [[Munich massacre|murder of 11 Israeli athletes]], which won him the [[Academy Award for Best Documentary Feature]]."
        res = llm_gen.translate_lead_prose(raw, "Kevin Macdonald")
        mock_client.translate_section.assert_called_once()
        self.assertIn("tentang pembunuhan 11 atlet Israel pada tahun 1972 yang memenangkannya", res)
        self.assertNotIn("tentang 1972 pembunuhan", res)
    def test_generate_stub_with_custom_lead(self):
        custom_lead = (
            "{{Infobox filmmaker\n| name = Kevin Macdonald\n}}\n\n"
            "'''Kevin Macdonald''' (born 28 October 1967) is a Scottish film director.<ref>Citation</ref>\n\n"
            "His films include ''One Day in September''."
        )
        res = self.generator.generate_stub(
            en_title="Kevin Macdonald (director)",
            id_title="Kevin Macdonald (sutradara)",
            topic="film",
            custom_lead=custom_lead,
        )
        self.assertEqual(res["id_title"], "Kevin Macdonald (sutradara)")
        self.assertEqual(res["en_title"], "Kevin Macdonald (director)")
        self.assertEqual(res["stub_template"], "{{sutradara-stub}}")
        self.assertIn("{{reflist}}", res["wikitext"])
        self.assertIn("{{sutradara-stub}}", res["wikitext"])
        self.assertIn("[[Kategori:Sutradara film Skotlandia]]", res["wikitext"])
        self.assertGreater(res["word_count"], 10)

    def test_extract_filmography_section(self):
        wikitext = (
            "== Biography ==\n"
            "Some bio text.\n\n"
            "== Selected filmography ==\n"
            "* [[One Day in September]] (1999)\n"
            "* [[The Last King of Scotland (film)|The Last King of Scotland]] (2006)\n\n"
            "== References ==\n"
            "{{reflist}}\n"
        )
        filmo = self.generator.extract_filmography_section(wikitext)
        self.assertIsNotNone(filmo)
        self.assertEqual(filmo["header"], "== Filmografi ==")
        self.assertIn("One Day in September", filmo["content"])
        self.assertIn("The Last King of Scotland", filmo["content"])

    def test_extract_works_section(self):
        wikitext = (
            "== Biography ==\nBio text.\n\n"
            "== Selected works ==\n"
            "* Novel A (2010)\n"
            "* Novel B (2015)\n\n"
            "== References ==\n"
        )
        works = self.generator.extract_filmography_section(wikitext)
        self.assertIsNotNone(works)
        self.assertEqual(works["header"], "== Karya pilihan ==")
        self.assertIn("Novel A", works["content"])

    def test_extract_works_sections_individual(self):
        # Test Bibliography
        wikitext_bib = "== Early life ==\nEarly life info.\n\n== Selected bibliography ==\n* Book One (2001)\n\n== References ==\n"
        secs = self.generator.extract_works_sections(wikitext_bib)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Bibliografi ==")
        self.assertIn("Book One (2001)", secs[0]["content"])

        # Test Discography
        wikitext_disco = "== Discography ==\n* Album A (2010)\n* Album B (2012)\n\n== Awards ==\n"
        secs = self.generator.extract_works_sections(wikitext_disco)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Diskografi ==")
        self.assertIn("Album A", secs[0]["content"])

        # Test Publications
        wikitext_pub = "== Publications ==\n* Paper A (2015)\n\n== External links ==\n"
        secs = self.generator.extract_works_sections(wikitext_pub)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Publikasi ==")
        self.assertIn("Paper A", secs[0]["content"])

        # Test Books
        wikitext_books = "== Books ==\n* Novel X (2020)\n"
        secs = self.generator.extract_works_sections(wikitext_books)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Buku ==")
        self.assertIn("Novel X", secs[0]["content"])
        # Test Theatre / Theater
        wikitext_theatre = "== Theatre ==\n* Play A (2018)\n"
        secs = self.generator.extract_works_sections(wikitext_theatre)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Teater ==")
        self.assertIn("Play A", secs[0]["content"])

        wikitext_theater = "== Theater ==\n* Play B (2019)\n"
        secs = self.generator.extract_works_sections(wikitext_theater)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Teater ==")
        self.assertIn("Play B", secs[0]["content"])

        # Test Audio
        wikitext_audio = "== Audio ==\n=== Video games ===\n* Game 1\n=== Audiobooks ===\n* Book 1\n=== Audio dramas ===\n* Drama 1\n"
        secs = self.generator.extract_works_sections(wikitext_audio)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Audio ==")
        self.assertIn("=== Permainan video ===", secs[0]["content"])
        self.assertIn("=== Buku audio ===", secs[0]["content"])
        self.assertIn("=== Drama audio ===", secs[0]["content"])

        # Test Awards and nominations / Accolades / Awards
        for head in ["Awards and nominations", "Accolades", "Awards"]:
            w = f"== {head} ==\n* Award 1\n"
            secs = self.generator.extract_works_sections(w)
            self.assertEqual(len(secs), 1)
            self.assertEqual(secs[0]["header"], "== Penghargaan dan nominasi ==")

        # Test Radio
        wikitext_radio = "== Radio ==\n* Show 1\n"
        secs = self.generator.extract_works_sections(wikitext_radio)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Radio ==")

        # Test Exhibitions
        wikitext_exhib = "== Exhibitions ==\n* Exhibit 1\n"
        secs = self.generator.extract_works_sections(wikitext_exhib)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Pameran ==")

        # Test Concert tours
        wikitext_tours = "== Concert tours ==\n* Tour 1\n"
        secs = self.generator.extract_works_sections(wikitext_tours)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0]["header"], "== Tur konser ==")


    def test_extract_multiple_works_sections(self):
        wikitext = (
            "== Biography ==\nBio text.\n\n"
            "== Selected filmography ==\n"
            "* Film 1 (2000)\n\n"
            "== Books ==\n"
            "* Memoir 1 (2010)\n\n"
            "== References ==\n"
        )
        secs = self.generator.extract_works_sections(wikitext)
        self.assertEqual(len(secs), 2)
        self.assertEqual(secs[0]["header"], "== Filmografi ==")
        self.assertIn("Film 1 (2000)", secs[0]["content"])
        self.assertEqual(secs[1]["header"], "== Buku ==")
        self.assertIn("Memoir 1 (2010)", secs[1]["content"])

    def test_generate_stub_with_multiple_works_sections(self):
        full_wikitext = (
            "{{Infobox writer\n| name = Jane Doe\n}}\n"
            "'''Jane Doe''' is an English author and academic.\n\n"
            "== Bibliography ==\n"
            "* Novel One (2005)\n"
            "* Novel Two (2008)\n\n"
            "== Publications ==\n"
            "* Academic Essay A (2012)\n\n"
            "== References ==\n"
        )
        res = self.generator.generate_stub(
            en_title="Jane Doe (writer)",
            id_title="Jane Doe (penulis)",
            custom_full_wikitext=full_wikitext,
        )
        self.assertTrue(res["has_works"])
        self.assertEqual(len(res["works_sections"]), 2)
        wikitext = res["wikitext"]
        self.assertIn("== Bibliografi ==", wikitext)
        self.assertIn("== Publikasi ==", wikitext)
        bib_pos = wikitext.find("== Bibliografi ==")
        pub_pos = wikitext.find("== Publikasi ==")
        ref_pos = wikitext.find("== Referensi ==")
        self.assertTrue(bib_pos < pub_pos < ref_pos)
    def test_generate_stub_with_infobox_and_filmography(self):
        full_wikitext = (
            "{{Infobox person\n| name = Kevin Macdonald\n| birth_date = 28 October 1967\n}}\n"
            "'''Kevin Macdonald''' (born 28 October 1967) is a Scottish film director.\n\n"
            "== Selected filmography ==\n"
            "* [[One Day in September]] (1999)\n"
            "* [[The Last King of Scotland (film)|The Last King of Scotland]] (2006)\n\n"
            "== References ==\n"
        )
        res = self.generator.generate_stub(
            en_title="Kevin Macdonald (director)",
            id_title="Kevin Macdonald (sutradara)",
            custom_full_wikitext=full_wikitext,
        )
        self.assertTrue(res["has_infobox"])
        self.assertTrue(res["has_filmography"])
        wikitext = res["wikitext"]
        self.assertIn("{{Infobox person", wikitext)
        self.assertIn("== Filmografi ==", wikitext)
        self.assertIn("== Referensi ==", wikitext)
        self.assertIn("{{sutradara-stub}}", wikitext)
        self.assertIn("[[Kategori:Sutradara film Skotlandia]]", wikitext)
        infobox_pos = wikitext.find("{{Infobox person")
        lead_pos = wikitext.find("'''Kevin Macdonald'''")
        filmo_pos = wikitext.find("== Filmografi ==")
        ref_pos = wikitext.find("== Referensi ==")
        stub_pos = wikitext.find("{{sutradara-stub}}")
        self.assertTrue(infobox_pos < lead_pos < filmo_pos < ref_pos < stub_pos)

    def test_save_stub(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir)
            stub_info = {
                "id_title": "Kevin Macdonald (sutradara)",
                "wikitext": "'''Kevin Macdonald''' adalah seorang sutradara.\n\n{{sutradara-stub}}",
            }
            saved_file = self.generator.save_stub(stub_info, out_path)
            self.assertTrue(saved_file.exists())
            self.assertEqual(saved_file.name, "Kevin_Macdonald_(sutradara).wikitext")
            self.assertEqual(
                saved_file.read_text(encoding="utf-8"),
                "'''Kevin Macdonald''' adalah seorang sutradara.\n\n{{sutradara-stub}}",
            )

    def test_extract_works_sections_localization(self):
        wikitext = (
            "== Filmography ==\n"
            "=== Documentary works ===\n"
            "=== Documentary ===\n"
            "=== Feature films ===\n"
            "=== Film ===\n"
            "=== Films ===\n"
            "=== Television ===\n"
            "=== Theatre ===\n"
            "=== Video games ===\n"
            "=== Audio ===\n\n"
            '{| class="wikitable sortable"\n'
            "! Year\n"
            "! Title\n"
            "! Role\n"
            "! Director\n"
            "! Producer\n"
            "! Writer\n"
            '! class="unsortable" | Notes\n'
            "! Character\n"
            "! Episodes\n"
            "! Episode\n"
            "! Series\n"
            "! Medium\n"
            "! Award\n"
            "! Category\n"
            "! Nominated work\n"
            "! Work\n"
            "! Result\n"
            "! Ref\n"
            "! Ref.\n"
            "! Venue\n"
            "! Theatre\n"
            "! Theater\n"
            "! Author\n"
            "! Production\n"
            "|-\n"
            "| 2005\n"
            "| ''Sample Movie''\n"
            "| Credited as John Doe\n"
            "| Co-directed with Jane Smith\n"
            "| Post-production\n"
            "|-\n"
            "| 2015\n"
            "| Award 1\n"
            "| Category 1\n"
            "| Work 1\n"
            "| Nominated\n"
            "|-\n"
            "| 2016\n"
            "| Award 2\n"
            "| Category 2\n"
            "| Work 2\n"
            "| Won\n"
            "|-\n"
            "| 2017\n"
            "| Award 3\n"
            "| Category 3\n"
            "| Work 3\n"
            "| Pending\n"
            "== References ==\n"
        )
        sections = self.generator.extract_works_sections(wikitext)
        self.assertEqual(len(sections), 1)
        sec = sections[0]
        self.assertEqual(sec["header"], "== Filmografi ==")
        content = sec["content"]

        # Verify subheadings
        self.assertIn("=== Karya dokumenter ===", content)
        self.assertIn("=== Dokumenter ===", content)
        self.assertIn("=== Film layar lebar ===", content)
        self.assertIn("=== Film ===", content)
        self.assertIn("=== Televisi ===", content)
        self.assertIn("=== Teater ===", content)
        self.assertIn("=== Permainan video ===", content)
        self.assertIn("=== Audio ===", content)

        # Verify table headers
        self.assertIn("! Tahun", content)
        self.assertIn("! Judul", content)
        self.assertIn("! Peran", content)
        self.assertIn("! Sutradara", content)
        self.assertIn("! Produser", content)
        self.assertIn("! Penulis", content)
        self.assertIn('! class="unsortable" | Catatan', content)
        self.assertIn("! Karakter", content)
        self.assertIn("! Episode", content)
        self.assertIn("! Serial", content)
        self.assertIn("! Media", content)
        self.assertIn("! Penghargaan", content)
        self.assertIn("! Kategori", content)
        self.assertIn("! Hasil", content)
        self.assertIn("! Karya yang dinominasikan", content)
        self.assertIn("! Ref.", content)
        self.assertIn("! Lokasi / Panggung", content)
        self.assertIn("! Pengarang", content)
        self.assertIn("! Produksi", content)

        # Verify award terms
        self.assertIn("Nominasi", content)
        self.assertIn("Menang", content)
        self.assertIn("Menunggu", content)

        # Verify common notes
        self.assertIn("Dikreditkan sebagai John Doe", content)
        self.assertIn("Disutradarai bersama Jane Smith", content)
        self.assertIn("Pascaproduksi", content)

    def test_extract_works_sections_roles_and_notes(self):
        wikitext = (
            "== Filmography ==\n"
            "=== Television ===\n"
            '{| class="wikitable"\n'
            "! Year !! Title !! Role !! Notes\n"
            "|-\n"
            '| 2014 || Title 1 || Main role || {{ill|season 1|en|Show season 1}}–{{ill|3|en|Show season 3}}\n'
            "|-\n"
            '| 2018 || Title 2 || Guest role || {{ill|season 4|en|Show season 4}}\n'
            "|-\n"
            '| 2020 || Title 3 || Recurring role || 12 episodes\n'
            "|-\n"
            '| 2021 || Title 4 || Voice role || TV movie\n'
            "|-\n"
            '| 2022 || Title 5 || Himself || Television special\n'
            "|-\n"
            '| 2023 || Title 6 || Ted || Netflix series\n'
            "|-\n"
            '| 2024 || Title 7 || Alex || Episode "The Rabbit Hole"\n'
            "|}\n"
        )
        sections = self.generator.extract_works_sections(wikitext)
        self.assertEqual(len(sections), 1)
        content = sections[0]["content"]
        self.assertIn("Peran utama", content)
        self.assertIn("Peran tamu", content)
        self.assertIn("Peran berulang", content)
        self.assertIn("Peran suara", content)
        self.assertIn("Film televisi", content)
        self.assertIn("Spesial televisi", content)
        self.assertIn("Serial Netflix", content)
        self.assertIn("12 episode", content)
        self.assertIn("musim 1", content)
        self.assertIn("musim 4", content)
        self.assertNotIn("{{ill|season", content)
    def test_extract_works_sections_table_cell_translation(self):
        wikitext = (
            "== Theatre ==\n"
            '{| class="wikitable"\n'
            "! Year !! Title !! Role !! Notes\n"
            "|-\n"
            "| 2012 || ''Happy New'' || Danny || Made professional London stage debut at the Old Red Lion.\n"
            "|-\n"
            "| 2021 || ''Watch on the Rhine'' || David || Broadway's Best Shows (U.S) (Online)\n"
            "|-\n"
            "| 2022 || ''Shades of Blue'' || {{n/a}} || Dramaturg only. Sadler's Wells Theatre\n"
            "|}\n\n"
            "== Awards and nominations ==\n"
            '{| class="wikitable sortable"\n'
            "! Year !! Award !! Category !! Nominated work !! Result\n"
            "|-\n"
            "| 2015 || NAACP Image Award || Outstanding Supporting Actor in a Drama Series || ''How to Get Away with Murder'' || Nominated\n"
            "|-\n"
            "| 2018 || IARA AWARDS || Best Young Actor || || Nominated\n"
            "|-\n"
            "| 2021 || FESTin || Best Actor Award || ''Executive Order'' || Won\n"
            "|-\n"
            "| 2023 || BBC Audio || Best Actor || ''Darkness'' || Nominated\n"
            "|}\n"
        )
        secs = self.generator.extract_works_sections(wikitext, title="Alfred Enoch")
        self.assertEqual(len(secs), 2)
        theatre_content = secs[0]["content"]
        awards_content = secs[1]["content"]

        # Verify Theatre cell translations
        self.assertIn("Memulai debut panggung profesionalnya di London di Old Red Lion", theatre_content)
        self.assertIn("(Daring)", theatre_content)
        self.assertIn("Hanya sebagai dramaturg. Sadler's Wells Theatre", theatre_content)

        # Verify Awards cell translations
        self.assertIn("Aktor Pendukung Luar Biasa dalam Seri Drama", awards_content)
        self.assertIn("Aktor Muda Terbaik", awards_content)
        self.assertIn("Penghargaan Aktor Terbaik", awards_content)
        self.assertIn("Aktor Terbaik", awards_content)

    def test_extract_works_sections_clean_broken_ill_nested_language(self):
        wikitext = (
            "== Awards and nominations ==\n"
            '{| class="wikitable"\n'
            "! Year !! Award !! Result\n"
            "|-\n"
            "| 2021 || {{ill|FESTin|en|:pt:Festival de Cinema Itinerante da Língua Portuguesa}} || Won\n"
            "|-\n"
            "| 2022 || {{ill|Paris Award|en|:fr:Festival de Paris}} || Won\n"
            "|}\n"
        )
        secs = self.generator.extract_works_sections(wikitext)
        content = secs[0]["content"]
        self.assertNotIn(":pt:", content)
        self.assertNotIn(":fr:", content)

    def test_infobox_values_localization_in_stub(self):
        full_wikitext = (
            "{{Infobox person\n"
            "| name = Test Actor\n"
            "| caption = Test in 2024\n"
            "| occupation = Actor\n"
            "| years_active = 2001–present\n"
            "| known_for = Character in Movie\n"
            "| citizenship = United Kingdom\n"
            "}}\n"
            "'''Test Actor''' (born 1 January 1990) is an English actor, best known for playing Hero in Film.\n"
        )
        self.generator._translator_initialized = True
        self.generator.translator_client = None
        stub = self.generator.generate_stub(
            en_title="Test Actor",
            custom_full_wikitext=full_wikitext,
        )
        wikitext = stub["wikitext"]
        self.assertIn("| occupation = Pemeran", wikitext)
        self.assertIn("| years_active = 2001–sekarang", wikitext)
        self.assertIn("| caption = Test pada tahun 2024", wikitext)
        self.assertIn("| known_for = Character dalam Movie", wikitext)
        self.assertIn("| citizenship = Britania Raya", wikitext)
        self.assertIn("adalah seorang pemeran asal Inggris yang dikenal luas karena memerankan", wikitext)
        self.assertNotIn("Inggris, yang", wikitext)

    def test_stub_orphan_ref_resolution_from_full_wikitext(self):
        full_wikitext = (
            "'''Alfred Enoch'''<ref name=\"TV Guide\" /> is an English actor.\n\n"
            "== Early life ==\n"
            "He was born in London.<ref name=\"TV Guide\">{{cite web|title=TV Guide Reference}}</ref>\n"
        )
        stub = self.generator.generate_stub(
            en_title="Alfred Enoch",
            custom_full_wikitext=full_wikitext,
        )
        wikitext = stub["wikitext"]
        # TV Guide should be defined in the stub
        self.assertIn('<ref name="TV Guide">{{cite web|title=TV Guide Reference}}</ref>', wikitext)
        # Should NOT contain orphan citation error
        issues = self.generator.syntax_balancer.check_balance(wikitext)
        self.assertFalse(any(i["tag_type"] == "ref" and i["severity"] == "error" for i in issues))
    def test_extract_external_links_section(self):
        wikitext = (
            "== External links ==\n"
            "{{commons category}}\n"
            "* {{Official website|https://example.com}}\n"
            "* {{official|https://example.org}}\n"
            "* {{IMDb title|123456}}\n"
            "* {{IMDb name|789012}}\n"
            "* {{Rotten Tomatoes|example_movie}}\n"
            "* {{AllMusic|artist/mn0001}}\n"
            "* [https://somelink.com Custom Link]\n"
            "\n"
            "{{SomeNavbox}}\n"
        )
        ext_links = self.generator.extract_external_links_section(wikitext)
        self.assertIsNotNone(ext_links)
        self.assertIn("* {{Situs web resmi|https://example.com}}", ext_links)
        self.assertIn("* {{Situs web resmi|https://example.org}}", ext_links)
        self.assertIn("* {{IMDb title|123456}}", ext_links)
        self.assertIn("* {{IMDb name|789012}}", ext_links)
        self.assertIn("* {{Rotten Tomatoes|example_movie}}", ext_links)
        self.assertIn("* {{AllMusic|artist/mn0001}}", ext_links)
        self.assertIn("* [https://somelink.com Custom Link]", ext_links)
        self.assertNotIn("{{commons category}}", ext_links)
        self.assertNotIn("{{SomeNavbox}}", ext_links)

    def test_extract_bottom_navboxes(self):
        wikitext = (
            "== External links ==\n"
            "* {{IMDb name|12345}}\n"
            "\n"
            "{{Kevin Macdonald}}\n"
            "{{Harry Potter}}\n"
            "{{NonExistentNavbox123}}\n"
            "{{Authority control}}\n"
            "{{DEFAULTSORT:Macdonald, Kevin}}\n"
            "[[Category:1967 births]]\n"
        )
        mock_mapper = MagicMock()
        mock_mapper.check_id_wiki_templates_exist.return_value = {
            "Kevin Macdonald": True,
            "Harry Potter": True,
            "NonExistentNavbox123": False,
        }
        gen = StubGenerator(template_mapper=mock_mapper)
        navboxes = gen.extract_bottom_navboxes(wikitext)
        self.assertEqual(len(navboxes), 3)
        self.assertIn("{{Kevin Macdonald}}", navboxes)
        self.assertIn("{{Harry Potter}}", navboxes)
        self.assertIn("<!-- Templat belum tersedia di id.wiki: {{NonExistentNavbox123}} -->", navboxes)

    def test_has_authority_control(self):
        self.assertTrue(self.generator.has_authority_control("Some text\n{{Authority control}}\n"))
        self.assertTrue(self.generator.has_authority_control("Some text\n{{Pengawasan otoritas}}\n"))
        self.assertFalse(self.generator.has_authority_control("Some text without auth\n{{Kevin Macdonald}}\n"))

    def test_generate_stub_end_of_article_layout(self):
        wikitext = (
            "{{Infobox person\n| name = Sample Director\n}}\n"
            "'''Sample Director''' (born 1970) is a film director.<ref>Source</ref>\n\n"
            "== Filmography ==\n"
            "{| class=\"wikitable\"\n"
            "|-\n"
            "| 2000 || Sample Film\n"
            "|}\n\n"
            "== References ==\n"
            "{{reflist}}\n\n"
            "== External links ==\n"
            "* {{Official website|http://sample.com}}\n"
            "* {{IMDb name|1234}}\n\n"
            "{{Kevin Macdonald}}\n"
            "{{NonExistentNavboxXYZ}}\n"
            "{{Authority control}}\n"
            "[[Category:Living people]]\n"
        )
        mock_mapper = MagicMock()
        mock_mapper.check_id_wiki_templates_exist.return_value = {
            "Kevin Macdonald": True,
            "NonExistentNavboxXYZ": False,
        }
        gen = StubGenerator(template_mapper=mock_mapper)
        res = gen.generate_stub("Sample Director", custom_full_wikitext=wikitext)
        content = res["wikitext"]

        # Verify order of components:
        idx_infobox = content.index("{{Infobox person")
        idx_body = content.index("'''Sample Director'''")
        idx_filmography = content.index("== Filmografi ==")
        idx_reflist = content.index("== Referensi ==\n{{reflist}}")
        idx_external = content.index("== Pranala luar ==")
        idx_nav_exist = content.index("{{Kevin Macdonald}}")
        idx_nav_missing = content.index("<!-- Templat belum tersedia di id.wiki: {{NonExistentNavboxXYZ}} -->")
        idx_auth = content.index("{{Pengawasan otoritas}}")
        idx_stub = content.index("{{sutradara-stub}}")
        idx_cat = content.index("[[Kategori:")

        self.assertTrue(
            idx_infobox < idx_body < idx_filmography < idx_reflist < idx_external
            < idx_nav_exist < idx_nav_missing < idx_auth < idx_stub < idx_cat
        )
        self.assertIn("* {{Situs web resmi|http://sample.com}}", content)
        self.assertIn("* {{IMDb name|1234}}", content)

    def test_generate_stub_runs_typography_sanitizer(self):
        mock_sanitizer = MagicMock()
        mock_sanitizer.sanitize_wikitext.side_effect = lambda wt: wt + "\n<!-- sanitized -->"
        gen = StubGenerator(typography_sanitizer=mock_sanitizer)
        res = gen.generate_stub(
            "Sample Subject",
            custom_lead="'''Sample Subject''' is a person.<ref>Ref</ref>",
        )
        mock_sanitizer.sanitize_wikitext.assert_called_once()
        self.assertIn("<!-- sanitized -->", res["wikitext"])
    def test_default_instance(self):
        self.assertIsInstance(default_stub_generator, StubGenerator)


if __name__ == "__main__":
    unittest.main()
