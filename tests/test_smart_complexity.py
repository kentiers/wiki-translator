"""
Unit tests for SmartComplexityAnalyzer and intelligent thinking selector.
"""

import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.gemini import (
    SmartComplexityAnalyzer,
    default_complexity_analyzer,
    GeminiTranslatorClient,
)


class TestSmartComplexityAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = SmartComplexityAnalyzer()

    def test_math_quantum_text_returns_high(self):
        math_text = r"""
        The wave function of the system is given by:
        <math>\psi(x, t) = A e^{i(kx - \omega t)}</math>
        where k is the wave number.
        """
        self.assertEqual(self.analyzer.recommend_tier(math_text), "high")

        # 2. Physics / mathematics topic
        quantum_text = "The system undergoes quantum decoherence and reaches an eigenstate."
        self.assertEqual(
            self.analyzer.recommend_tier(quantum_text, topic="physics_mathematics"),
            "high",
        )
        self.assertEqual(
            self.analyzer.recommend_tier(quantum_text, topic="quantum"),
            "high",
        )

        # 3. High density of academic jargon without explicit topic
        dense_academic = (
            "In quantum field theory, the Hamiltonian operator determines the time evolution "
            "of the wave function in Hilbert space, causing superposition and quantum entanglement."
        )
        self.assertEqual(self.analyzer.recommend_tier(dense_academic), "high")

        # 4. Long compound-complex sentences (avg sentence length > 35 words)
        long_sentences = (
            "Although the initial formulations of canonical quantum gravity attempted to reconcile "
            "the geometric principles of general relativity with the probabilistic interpretations of "
            "quantum mechanics through the Wheeler DeWitt equation, subsequent developments in loop quantum "
            "gravity demonstrated that space itself might possess a discrete granular structure at the Planck scale. "
            "Furthermore, these mathematical frameworks require rigorous reinterpretation of diffeomorphism invariance "
            "under non-perturbative conditions where classical notions of continuous smooth spacetime manifolds completely "
            "break down into spin network representations."
        )
        self.assertEqual(self.analyzer.recommend_tier(long_sentences), "high")

    def test_medical_legal_text_returns_medium(self):
        # 1. Medical / biology topic
        bio_text = "Clinical trial results indicated high antibody titers and cellular immunity."
        self.assertEqual(
            self.analyzer.recommend_tier(bio_text, topic="medical_biology"),
            "medium",
        )

        # 2. History / social topic
        history_text = "During the reign of the Ming dynasty, international trade expanded across maritime routes."
        self.assertEqual(
            self.analyzer.recommend_tier(history_text, topic="history_social"),
            "medium",
        )

        # 3. Legal and jurisprudence concepts
        legal_text = (
            "The appellate court examined whether statutory interpretation precluded the plaintiff "
            "from seeking adjudication under constitutional jurisdiction, establishing precedent for future tort litigation."
        )
        self.assertEqual(self.analyzer.recommend_tier(legal_text), "medium")

        # 4. Lead sections of historical/biographical articles
        bio_lead = (
            "Alexander Hamilton was an American military officer, statesman, and Founding Father who served "
            "as the first secretary of the treasury from 1789 to 1795. Born out of wedlock in Charlestown, Nevis, "
            "he was orphaned as a child and taken in by a prosperous merchant."
        )
        self.assertEqual(
            self.analyzer.recommend_tier(bio_lead, topic="history_social", section_title=""),
            "medium",
        )

    def test_film_cast_table_text_returns_low(self):
        # 1. Film / pop culture topic
        film_text = "The movie was a massive box office hit and received nominations for best picture."
        self.assertEqual(
            self.analyzer.recommend_tier(film_text, topic="film"),
            "low",
        )
        self.assertEqual(
            self.analyzer.recommend_tier(film_text, topic="cinema"),
            "low",
        )
        self.assertEqual(
            self.analyzer.recommend_tier(film_text, topic="entertainment"),
            "low",
        )

        # 2. Cast list section
        cast_text = """
        * [[Leonardo DiCaprio]] as Dom Cobb
        * [[Joseph Gordon-Levitt]] as Arthur
        * [[Elliot Page]] as Ariadne
        * [[Tom Hardy]] as Eames
        """
        self.assertEqual(
            self.analyzer.recommend_tier(cast_text, section_title="Cast"),
            "low",
        )
        self.assertEqual(
            self.analyzer.recommend_tier(cast_text, section_title="Pemeran"),
            "low",
        )

        # 3. Tabular / discography / tracklist data
        table_text = """
        {| class="wikitable"
        |-
        ! No. !! Title !! Length
        |-
        | 1 || "Intro" || 1:20
        |-
        | 2 || "Main Track" || 3:45
        |}
        """
        self.assertEqual(
            self.analyzer.recommend_tier(table_text, section_title="Track listing"),
            "low",
        )
        self.assertEqual(
            self.analyzer.recommend_tier(table_text, section_title="Diskografi"),
            "low",
        )

    def test_resolve_model(self):
        # Auto resolution to flash-high
        model, tier = self.analyzer.resolve_model(
            requested_model="gemini-3.8-flash",
            requested_thinking="auto",
            source_text="<math>E = mc^2</math>",
            topic="physics_mathematics",
        )
        self.assertEqual(tier, "high")
        self.assertEqual(model, "gemini-3.8-flash-high")

        # Auto resolution to flash-medium
        model, tier = self.analyzer.resolve_model(
            requested_model="gemini-3.8-flash",
            requested_thinking="auto",
            source_text="The randomized controlled clinical trial observed antibody response.",
            topic="medical_biology",
        )
        self.assertEqual(tier, "medium")
        self.assertEqual(model, "gemini-3.8-flash-medium")

        # Auto resolution to flash-low
        model, tier = self.analyzer.resolve_model(
            requested_model="gemini-3.8-flash",
            requested_thinking="auto",
            source_text="* [[Actor A]] as Character A\n* [[Actor B]] as Character B",
            topic="film",
            section_title="Cast",
        )
        self.assertEqual(tier, "low")
        self.assertEqual(model, "gemini-3.8-flash-low")

        # Explicit non-auto thinking passed through
        model, tier = self.analyzer.resolve_model(
            requested_model="gemini-3.8-flash",
            requested_thinking="high",
            source_text="* [[Actor A]] as Character A",
            topic="film",
        )
        self.assertEqual(tier, "high")
        self.assertEqual(model, "gemini-3.8-flash-high")


class TestGeminiClientAutoResolution(unittest.TestCase):
    def test_auto_resolution_in_gemini_translator_client(self):
        client = GeminiTranslatorClient(thinking_level="auto")
        self.assertEqual(client.thinking_level, "auto")

        # Mock _translate_antigravity to observe model parameter passed
        with patch.object(client, "_translate_antigravity", return_value="Hasil terjemahan") as mock_trans:
            with patch.object(client.auth_manager, "load_credentials") as mock_creds:
                mock_cred = MagicMock()
                mock_cred.is_exhausted = False
                mock_cred.is_expired.return_value = False
                mock_creds.return_value = [mock_cred]

                # 1. High complexity text -> should dynamically use gemini-3.8-flash-high
                client.translate_section(
                    user_prompt="Translate this",
                    source_text=r"<math>\hat{H}|\psi\rangle = E|\psi\rangle</math>",
                    topic="physics_mathematics",
                )
                self.assertEqual(mock_trans.call_args[1]["model"], "gemini-3.8-flash-high")

                # 2. Medium complexity text -> should dynamically use gemini-3.8-flash-medium
                client.translate_section(
                    user_prompt="Translate this",
                    source_text="The antibody neutralized the pathogen during the clinical trial.",
                    topic="medical_biology",
                    section_title="Immunology",
                )
                self.assertEqual(mock_trans.call_args[1]["model"], "gemini-3.8-flash-medium")

                # 3. Low complexity text -> should dynamically use gemini-3.8-flash-low
                client.translate_section(
                    user_prompt="Translate this",
                    source_text="* [[Actor A]] as Character A\n* [[Actor B]] as Character B",
                    topic="film",
                    section_title="Cast",
                )
                self.assertEqual(mock_trans.call_args[1]["model"], "gemini-3.8-flash-low")

                # 4. Explicit model override passed to translate_section
                client.translate_section(
                    user_prompt="Translate this",
                    model="custom-model-x",
                    source_text="<math>E = mc^2</math>",
                )
                self.assertEqual(mock_trans.call_args[1]["model"], "custom-model-x")


if __name__ == "__main__":
    unittest.main()
