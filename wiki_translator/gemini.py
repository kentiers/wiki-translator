"""
Gemini translation client for Wiki Translator.

Primary: Google Antigravity CloudCode Internal SSE endpoint (daily-cloudcode-pa.googleapis.com)
Fallback: Standard Google AI Studio API via GEMINI_API_KEY (generativelanguage.googleapis.com)
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from .auth import AuthManager, AntigravityCredential
from .prompts import (
    SYSTEM_PROMPT_GRADE_A_PLUS_PLUS,
    SYSTEM_PROMPT_HUMANIZE_POLISH,
    build_polish_prompt,
)
from .token_saver import (
    TokenCompressor,
    TranslationCache,
    TokenTracker,
    default_cache,
    default_tracker,
)
CLOUDCODE_ENDPOINT = (
    "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
)
AI_STUDIO_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"

# Mapping model identifiers to Antigravity internal endpoint requestModelIds
ANTIGRAVITY_MODEL_MAP: Dict[str, str] = {
    "gemini-3.8-flash": "gemini-3.8-flash-low",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "gemini-3.8-flash:low": "gemini-3.8-flash-low",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash:medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash:high": "gemini-3.8-flash-high",
    "gemini-3.7-flash": "gemini-3.7-flash-low",
}

class SmartComplexityAnalyzer:
    """
    Analyzes source wikitext, topic, and section titles to determine content complexity
    and select optimal model/thinking tiers on the fly.
    """

    # High-complexity topic identifiers
    HIGH_TOPICS = {
        "physics_mathematics",
        "physics",
        "mathematics",
        "quantum",
        "philosophy",
    }

    # Medium-complexity topic identifiers
    MEDIUM_TOPICS = {
        "medical_biology",
        "history_social",
        "law",
        "legal",
        "jurisprudence",
        "medicine",
        "biology",
        "history",
    }

    # Standard / Low-complexity topic identifiers
    LOW_TOPICS = {
        "film",
        "cinema",
        "entertainment",
        "pop_culture",
        "sports",
        "sport",
        "tv_series",
        "television",
        "media",
    }

    # Regex patterns for high complexity detection
    MATH_TAG_PATTERN = re.compile(r"<math[\s>]", re.IGNORECASE)
    COMPLEX_FORMULA_PATTERN = re.compile(
        r"(\{\{math\||\\frac|\\sqrt|\\sum|\\int|\\partial|\\psi|\\alpha|\\beta|\\gamma|\\hbar|\\infty|\b\d+[\^\_]\d+)",
        re.IGNORECASE,
    )
    ACADEMIC_JARGON_PATTERN = re.compile(
        r"\b(eigenstate|eigenvalue|eigenvector|hamiltonian|schrödinger|schrodinger|wave\s+function|"
        r"quantum\s+entanglement|quantum\s+decoherence|superposition|hilbert\s+space|diffeomorphism|"
        r"differential\s+equation|riemannian|epistemolog\w+|ontolog\w+|phenomenolog\w+|hermeneutic\w+|"
        r"teleolog\w+|metaphysic\w+|non-abelian|gauge\s+theory|general\s+relativity|special\s+relativity|"
        r"thermodynamic\w+|quantum\s+field|spacetime\s+curvature|tensor\s+calculus)\b",
        re.IGNORECASE,
    )

    # Medium complexity indicators (legal, jurisprudence, historical events)
    LEGAL_JURISPRUDENCE_PATTERN = re.compile(
        r"\b(jurisprudence|statutory|constitutional|jurisdiction|plaintiff|defendant|appellate|"
        r"adjudication|habeas\s+corpus|tort\b|arbitration|indictment|prosecution|litigation|"
        r"treaty|armistice|ratification|sovereignty|diplomatic\s+immunity|precedent)\b",
        re.IGNORECASE,
    )

    # Low complexity structure indicators (tables, lists, cast, discography, etc.)
    LOW_SECTION_TITLES = {
        "cast",
        "pemeran",
        "daftar pemeran",
        "filmography",
        "filmografi",
        "discography",
        "diskografi",
        "track listing",
        "daftar lagu",
        "bibliography",
        "bibliografi",
        "accolades",
        "penghargaan",
        "awards and nominations",
        "nominasi dan penghargaan",
        "box office",
        "chart performance",
        "tangga lagu",
        "tour dates",
        "daftar putar",
        "see also",
        "lihat pula",
        "references",
        "referensi",
        "external links",
        "pranala luar",
    }

    def _calculate_avg_sentence_length(self, text: str) -> float:
        """Calculates average sentence length in words."""
        # Strip common wikitext tags/templates for raw sentence measurement
        clean_text = re.sub(r"\{\{[^}]*\}\}", " ", text)
        clean_text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", clean_text)
        clean_text = re.sub(r"<ref[^>]*>.*?</ref>", " ", clean_text, flags=re.DOTALL)
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)

        # Split sentences roughly by punctuation
        sentences = [s.strip() for s in re.split(r"[.!?]+", clean_text) if s.strip()]
        if not sentences:
            return 0.0

        word_counts = [len(s.split()) for s in sentences if len(s.split()) > 2]
        if not word_counts:
            return 0.0
        return sum(word_counts) / len(word_counts)

    def _is_tabular_or_list_dominant(self, text: str) -> bool:
        """Determines if text is primarily tabular data or list entries."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False
        table_or_list_lines = sum(
            1
            for ln in lines
            if ln.startswith(("{|", "|", "!", "|-", "|}", "*", "#", ";", ":"))
        )
        return (table_or_list_lines / len(lines)) >= 0.55

    def recommend_tier(
        self,
        source_text: str,
        topic: Optional[str] = None,
        section_title: str = "",
    ) -> str:
        """
        Recommends complexity tier: 'low', 'medium', or 'high'.
        """
        norm_title = (section_title or "").strip().lower()
        norm_topic = (topic or "").strip().lower()
        is_lead_section = norm_title in ("", "lead", "pengantar", "pendahuluan", "ringkasan")

        # Check 1: Structural low complexity (cast lists, filmographies, tabular data, discographies)
        if norm_title in self.LOW_SECTION_TITLES or self._is_tabular_or_list_dominant(source_text):
            # Unless it contains heavy math or formulas
            if not self.MATH_TAG_PATTERN.search(source_text):
                return "low"

        # Check 2: High complexity topics or explicit math/quantum/philosophy indicators
        if norm_topic in self.HIGH_TOPICS:
            return "high"

        # Presence of <math> tags or complex mathematical formulas
        if self.MATH_TAG_PATTERN.search(source_text) or len(self.COMPLEX_FORMULA_PATTERN.findall(source_text)) >= 2:
            return "high"

        # High density of academic jargon
        jargon_matches = self.ACADEMIC_JARGON_PATTERN.findall(source_text)
        if len(jargon_matches) >= 3:
            return "high"

        # Average sentence length > 35 words (long compound-complex sentences)
        avg_sentence_len = self._calculate_avg_sentence_length(source_text)
        if avg_sentence_len > 35.0:
            return "high"

        # Check 3: Medium complexity topics and domain concepts
        if norm_topic in self.MEDIUM_TOPICS:
            return "medium"

        # Legal / jurisprudence concepts or historical event indicators
        if len(self.LEGAL_JURISPRUDENCE_PATTERN.findall(source_text)) >= 2:
            return "medium"

        # Lead sections of prominent biographies or major historical articles
        if is_lead_section and (
            norm_topic in ("history_social", "medical_biology", "biography", "tokoh")
            or len(source_text.split()) > 100
        ):
            # For standard low topics (like film/pop culture), lead of standard article can remain low unless extensive
            if norm_topic in self.LOW_TOPICS:
                if avg_sentence_len > 25.0 and len(source_text.split()) > 200:
                    return "medium"
                return "low"
            return "medium"

        # Check 4: Standard / Low complexity topics (film, cinema, pop culture, sports, etc.)
        if norm_topic in self.LOW_TOPICS:
            return "low"

        # Default fallback: if moderate sentence length / vocabulary, medium; otherwise low
        if avg_sentence_len >= 25.0:
            return "medium"

        return "low"

    def resolve_model(
        self,
        requested_model: str,
        requested_thinking: str,
        source_text: str,
        topic: Optional[str] = None,
        section_title: str = "",
    ) -> Tuple[str, str]:
        """
        Resolves model identifier and thinking tier based on requested parameters and text complexity.
        If requested_thinking == 'auto':
            Automatically determines tier ('low', 'medium', or 'high') and maps to appropriate model identifier.
        Returns (model_name, resolved_tier).
        """
        if requested_thinking == "auto":
            resolved_tier = self.recommend_tier(
                source_text=source_text,
                topic=topic,
                section_title=section_title,
            )
            # Map to appropriate model
            if requested_model.startswith("gemini-3.8-flash"):
                model_name = f"gemini-3.8-flash-{resolved_tier}"
            elif requested_model.startswith("gemini-3.7-flash"):
                model_name = f"gemini-3.7-flash-{resolved_tier}"
            else:
                # Custom or explicit model
                model_name = requested_model
            return model_name, resolved_tier
        else:
            resolved_tier = requested_thinking if requested_thinking in ("low", "medium", "high") else "low"
            if requested_model == "gemini-3.8-flash":
                model_name = f"gemini-3.8-flash-{resolved_tier}"
            else:
                model_name = requested_model
            return model_name, resolved_tier


default_complexity_analyzer = SmartComplexityAnalyzer()


class GeminiTranslatorClient:
    """Translation client connecting to Gemini via Antigravity or Google AI Studio."""

    def __init__(
        self,
        auth_manager: Optional[AuthManager] = None,
        preferred_model: str = "gemini-3.8-flash",
        api_key: Optional[str] = None,
        cache: Optional[TranslationCache] = None,
        tracker: Optional[TokenTracker] = None,
        thinking_level: str = "auto",
        complexity_analyzer: Optional[SmartComplexityAnalyzer] = None,
    ):
        self.auth_manager = auth_manager or AuthManager()
        self.thinking_level = thinking_level if thinking_level in ("auto", "low", "medium", "high") else "auto"
        self.complexity_analyzer = complexity_analyzer or default_complexity_analyzer
        # Resolve model if preferred_model is base gemini-3.8-flash or maps via thinking_level
        if preferred_model == "gemini-3.8-flash":
            if self.thinking_level != "auto":
                self.preferred_model = f"gemini-3.8-flash-{self.thinking_level}"
            else:
                self.preferred_model = "gemini-3.8-flash-low"
        else:
            self.preferred_model = preferred_model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.cache = cache or default_cache
        self.tracker = tracker or default_tracker
    def translate_section_by_paragraphs(
        self,
        section_title: str,
        wikitext: str,
        topic: Optional[str] = None,
        context_notes: Optional[str] = None,
        custom_glossary: Optional[Dict[str, str]] = None,
        resolved_glossary: Optional[Dict[str, str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Translates a multi-paragraph wikitext section chunk-by-chunk with context awareness.
        """
        from .paragraph_translator import default_paragraph_translator

        def chunk_translator(chunk_prompt: str, sys_inst: Optional[str] = None) -> str:
            return self.translate_section(
                user_prompt=chunk_prompt,
                system_instruction=sys_inst,
                model=model,
                source_text=chunk_prompt,
                topic=topic,
                section_title=section_title,
            )

        return default_paragraph_translator.translate_section_by_paragraphs(
            section_title=section_title,
            wikitext=wikitext,
            translator_func=chunk_translator,
            topic=topic,
            context_notes=context_notes,
            custom_glossary=custom_glossary,
            resolved_glossary=resolved_glossary,
            stream_callback=stream_callback,
        )

    def translate_section(
        self,
        user_prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
        source_text: Optional[str] = None,
        topic: Optional[str] = None,
        section_title: str = "",
    ) -> str:
        """
        Translates a single section. Attempts Antigravity first, falls back to GEMINI_API_KEY if needed.
        If thinking_level == 'auto', dynamically determines the model using SmartComplexityAnalyzer.
        """
        if model:
            model_to_use = model
        elif self.thinking_level == "auto":
            # Analyze source text if provided, otherwise analyze user_prompt
            text_to_analyze = source_text or user_prompt
            model_to_use, _ = self.complexity_analyzer.resolve_model(
                requested_model=self.preferred_model,
                requested_thinking="auto",
                source_text=text_to_analyze,
                topic=topic,
                section_title=section_title,
            )
        else:
            model_to_use = self.preferred_model
        sys_inst = system_instruction or SYSTEM_PROMPT_GRADE_A_PLUS_PLUS
        # Try Antigravity credentials with multi-pass and backoff for transient 503 errors
        credentials = self.auth_manager.load_credentials()
        if credentials:
            for attempt in range(2):
                for cred in credentials:
                    if cred.is_exhausted:
                        continue
                    if cred.is_expired():
                        self.auth_manager.refresh_access_token(cred)

                    try:
                        res = self._translate_antigravity(
                            cred=cred,
                            user_prompt=user_prompt,
                            system_instruction=sys_inst,
                            model=model_to_use,
                            stream_callback=stream_callback,
                        )
                        if res:
                            return res
                    except urllib.error.HTTPError as he:
                        if he.code in (429, 403):
                            cred.is_exhausted = True
                            continue
                        elif he.code == 401:
                            # Refresh token and retry once
                            refreshed = self.auth_manager.refresh_access_token(cred)
                            if refreshed:
                                try:
                                    return self._translate_antigravity(
                                        cred=cred,
                                        user_prompt=user_prompt,
                                        system_instruction=sys_inst,
                                        model=model_to_use,
                                        stream_callback=stream_callback,
                                    )
                                except Exception:
                                    cred.is_exhausted = True
                                    continue
                        elif he.code in (500, 502, 503, 504):
                            time.sleep(0.5)
                            continue
                        else:
                            continue
                    except Exception:
                        continue
                if attempt == 0:
                    time.sleep(1.0)
        # Fallback to standard GEMINI_API_KEY
        if self.api_key:
            return self._translate_ai_studio(
                api_key=self.api_key,
                user_prompt=user_prompt,
                system_instruction=sys_inst,
                model=model_to_use,
                stream_callback=stream_callback,
            )

        raise RuntimeError(
            "Translation failed: No active Antigravity credentials available in agent.db and GEMINI_API_KEY not configured."
        )

    def polish_section(
        self,
        source_en: str,
        draft_id: str,
        model: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Performs a 2nd pass humanize/polish on the draft translation to remove AI slop.
        """
        polish_prompt = build_polish_prompt(source_en=source_en, draft_id=draft_id)
        return self.translate_section(
            user_prompt=polish_prompt,
            system_instruction=SYSTEM_PROMPT_HUMANIZE_POLISH,
            model=model,
            stream_callback=stream_callback,
        )

    def _translate_antigravity(
        self,
        cred: AntigravityCredential,
        user_prompt: str,
        system_instruction: str,
        model: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Sends request to Antigravity internal endpoint with SSE parser."""
        headers = {
            "Authorization": f"Bearer {cred.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/hub/2.8.0 (aidev_client; os_type=darwin; arch=arm64; cl=963137146)",
        }

        # Build CloudCode payload format with maxOutputTokens compatible with backend (32768)
        payload = {
            "project": cred.project_id or "aicode-consumers",
            "model": ANTIGRAVITY_MODEL_MAP.get(model, model),
            "userAgent": "antigravity",
            "requestType": "agent",
            "request": {
                "systemInstruction": {
                    "role": "user",
                    "parts": [{"text": system_instruction}],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 32768,
                },
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            CLOUDCODE_ENDPOINT,
            data=data_bytes,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=90) as resp:
            return self._parse_sse_response(resp, stream_callback)

    def _translate_ai_studio(
        self,
        api_key: str,
        user_prompt: str,
        system_instruction: str,
        model: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Fallback to Google AI Studio v1beta endpoint."""
        url = AI_STUDIO_ENDPOINT.format(model=model, api_key=api_key)
        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 32768,
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=90) as resp:
            return self._parse_sse_response(resp, stream_callback)

    def _parse_sse_response(
        self,
        resp_stream: Any,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Parses Server-Sent Events (SSE) data stream from Gemini.
        Robustly handles multiline data blocks, thoughts, and chunk buffers.
        """
        full_text_chunks: List[str] = []
        current_event_data: List[str] = []

        def flush_event_data() -> None:
            if not current_event_data:
                return
            combined_data = "\n".join(current_event_data).strip()
            current_event_data.clear()
            if not combined_data or combined_data == "[DONE]":
                return
            try:
                chunk_json = json.loads(combined_data)
                # Support both standard Gemini schema and CloudCode envelope schema
                response_obj = chunk_json.get("response", chunk_json)
                candidates = response_obj.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    for p in parts:
                        # Skip internal thought traces if returned by reasoning models
                        if p.get("thought"):
                            continue
                        txt = p.get("text", "")
                        if txt:
                            full_text_chunks.append(txt)
                            if stream_callback:
                                stream_callback(txt)
            except Exception:
                pass

        # Read line by line from stream
        for line_bytes in resp_stream:
            if isinstance(line_bytes, str):
                line = line_bytes.rstrip("\r\n")
            else:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")

            # Empty line dispatches the SSE event
            if not line:
                flush_event_data()
                continue

            # SSE comment lines start with ':'
            if line.startswith(":"):
                continue

            if line.startswith("data:"):
                payload = line[5:]
                if payload.startswith(" "):
                    payload = payload[1:]
                current_event_data.append(payload)

        # Flush remaining if stream closed without trailing empty line
        flush_event_data()

        full_output = "".join(full_text_chunks).strip()

        # Clean markdown fence if LLM wrapped output in ```wikitext or ```
        if full_output.startswith("```wikitext"):
            full_output = full_output[11:].strip()
        elif full_output.startswith("```"):
            full_output = full_output[3:].strip()

        if full_output.endswith("```"):
            full_output = full_output[:-3].strip()

        return full_output

__all__ = [
    "SmartComplexityAnalyzer",
    "default_complexity_analyzer",
    "GeminiTranslatorClient",
    "ANTIGRAVITY_MODEL_MAP",
]
