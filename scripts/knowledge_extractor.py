#!/usr/bin/env python3
"""
Knowledge Extractor V2 — Faza 18A (upgraded from V1/17X)

Extrage automat decisions, facts și error resolutions din conversațiile
capturate la session_end. Pattern-based, fără LLM.

V2 improvements (18A):
- Negative patterns: rejectează meta-discuții, întrebări, ipoteze, cod
- Auto-clasificare: category pentru decisions, fact_type pentru facts
- Segment filtering îmbunătățit: skip întrebări, code refs, noise
- Matched text validation: lungime minimă, no pure code snippets
- Threshold tuning bazat pe V1 false positives observate

Inspirat din EAN-AutoCode_AI/core/research/:
- Pattern compilation la import (mode_controller.py)
- Confidence scoring cu 3 factori (mode_controller.py)
- Jaccard similarity pentru dedup (synthesis.py)

Integrare: apelat din memory_daemon.py handle_session_end()
"""

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# === PATHS ===
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent

# Import v2_common pentru DB
try:
    from v2_common import get_db, get_current_session_id, get_current_project_path, get_current_branch
except ImportError:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from v2_common import get_db, get_current_session_id, get_current_project_path, get_current_branch


# ============================================================
# 1. EXTRACTION PATTERNS (compilate la import)
# ============================================================

class ExtractionPatterns:
    """Pattern-uri regex compilate pentru extracție. Compilare o singură dată la import."""

    # --- Decisions ---
    # Pattern weights: contribuie direct la scor (max 0.60 cap)
    DECISION_PATTERNS = [
        # EN — explicit decisions (V2: optional adverb between subject and verb)
        (r"(?:we|i)\s+(?:\w+\s+)?decided?\s+(?:to\s+)?(.{10,120})", 0.55),
        (r"(?:let'?s|we'?ll)\s+(?:use|go with|stick with|switch to|move to)\s+(.{5,100})", 0.50),
        (r"final\s+decision[:\s]+(.{10,120})", 0.60),
        (r"(?:we|i)\s+(?:\w+\s+)?(?:chose|picked|selected)\s+(.{5,100})", 0.50),
        (r"going\s+(?:with|for)\s+(.{5,80})", 0.40),
        # RO — explicit
        (r"am\s+decis\s+(?:să\s+)?(.{10,120})", 0.55),
        (r"(?:mergem|rămânem|trecem)\s+(?:pe|la|cu)\s+(.{5,100})", 0.50),
        (r"(?:folosim|păstrăm|alegem|implementăm)\s+(.{5,100})", 0.45),
        (r"decizia?\s+(?:finală|e|este)[:\s]+(.{10,120})", 0.60),
    ]

    # --- Facts ---
    FACT_PATTERNS = [
        # EN
        (r"(?:it\s+)?(?:supports?|requires?|uses?|runs?\s+on|depends?\s+on)\s+(.{5,100})", 0.40),
        (r"(?:the\s+)?default\s+(?:is|port|value|path)[:\s]+(.{3,80})", 0.45),
        (r"(?:is\s+stored|lives?)\s+(?:in|at)\s+(.{5,80})", 0.40),
        (r"(?:important|note|remember)[:\s]+(.{10,120})", 0.50),
        (r"(?:does\s+not|doesn'?t)\s+support\s+(.{5,80})", 0.45),
        # RO
        (r"(?:suportă|necesită|folosește|rulează\s+pe)\s+(.{5,100})", 0.40),
        (r"(?:portul|calea|valoarea)\s+(?:este|e|default)[:\s]+(.{3,80})", 0.45),
        (r"(?:important|atenție|notă|reține)[:\s]+(.{10,120})", 0.50),
        (r"(?:nu\s+suportă|nu\s+funcționează\s+cu)\s+(.{5,80})", 0.45),
    ]

    # --- Resolutions ---
    RESOLUTION_PATTERNS = [
        # EN
        (r"(?:fixed|resolved|solved)\s+(?:by|with|via)\s+(.{10,150})", 0.55),
        (r"(?:the\s+)?(?:fix|solution|workaround)\s+(?:was|is)[:\s]+(.{10,150})", 0.55),
        (r"(?:the\s+)?(?:problem|issue|bug|root\s+cause)\s+(?:was|is)[:\s]+(.{10,150})", 0.50),
        (r"worked\s+after\s+(.{10,120})", 0.50),
        (r"issue\s+(?:was\s+)?caused\s+by\s+(.{10,120})", 0.50),
        # RO
        (r"s-a\s+rezolvat\s+(?:prin|cu|după)\s+(.{10,150})", 0.55),
        (r"(?:fixul|soluția)\s+(?:a\s+fost|e|este)[:\s]+(.{10,150})", 0.55),
        (r"(?:problema|bug-ul|cauza)\s+(?:era|a\s+fost|e)[:\s]+(.{10,150})", 0.50),
        (r"(?:am\s+rezolvat|am\s+fixat)\s+(?:prin|cu)\s+(.{10,120})", 0.55),
    ]

    # --- Negative patterns V2 (rejectează false positives) ---
    # Dacă un segment match-uiește oricare din acestea, NU se extrage
    NEGATIVE_PATTERNS = [
        # Întrebări (meta-discuție, nu decizii)
        r"^\s*(?:should|shall|can|could|would|do|does|is|are|what|how|why|where|when)\s+.+\?\s*$",
        r"^\s*(?:care|cum|de ce|unde|când|ce)\s+.+\?\s*$",
        # Ipoteze / speculații
        r"(?:if\s+we|what\s+if|in\s+case|as\s+an?\s+alternative)",
        r"(?:dacă\s+am|în\s+cazul|ca\s+alternativă)",
        # Meta-discuție despre opțiuni (nu decizii efective)
        r"(?:we\s+could\s+(?:also|either)|another\s+option|one\s+option)\s+",
        r"(?:am\s+putea\s+(?:și|fie)|altă\s+opțiune|o\s+opțiune)\s+",
        # Referințe la cod/fișiere fără decizie
        r"^(?:file|fișier|line|linia|function|funcția|class|clasa)\s*[:=]",
        # Listing/enumerare fără substanță
        r"^[-*•]\s+\w{1,20}$",
        # Status updates fără decizie
        r"^(?:done|ready|ok|updated|modificat|actualizat|gata)\s*[.!]?\s*$",
        # Tool output / code snippets inline
        r"(?:```|>>>|\$\s+|^\s*import\s+|^\s*from\s+\w+\s+import)",
        # Quote attribution (nu e decizia noastră)
        r"(?:according\s+to|as\s+(?:stated|mentioned)\s+(?:in|by)|conform|după\s+cum\s+zice)",
    ]

    # --- Topic extraction V2/18B ---
    # Extrage keywords tehnice din text pentru tagging
    TECH_TERM_PATTERN = re.compile(
        r"\b("
        # Databases
        r"(?:SQLite|PostgreSQL|MySQL|MongoDB|Redis|DynamoDB|Cassandra|MariaDB)"
        r"|(?:Flask|FastAPI|Django|Express|Next\.?js|React|Vue|Angular|Svelte)"
        r"|(?:Docker|Kubernetes|K8s|Nginx|Apache|Caddy|Traefik)"
        r"|(?:Python|JavaScript|TypeScript|Go|Rust|Java|C\#|PHP|Ruby)"
        r"|(?:JWT|OAuth|CORS|SSL|TLS|HTTPS|SSH|RBAC)"
        r"|(?:WAL|FTS5|NVLink|VRAM|GPU|CPU|RAM|SSD|NVMe)"
        r"|(?:CI/?CD|GitHub|GitLab|Bitbucket|Jenkins|ArgoCD)"
        r"|(?:REST|GraphQL|gRPC|WebSocket|HTTP|MCP|API)"
        r"|(?:npm|pip|cargo|yarn|pnpm|brew)"
        r"|(?:Linux|Windows|macOS|Ubuntu|Debian|Alpine)"
        r"|(?:AWS|GCP|Azure|Cloudflare|Vercel|Netlify)"
        r"|(?:JSON|YAML|TOML|XML|CSV|Markdown)"
        r")\b",
        re.IGNORECASE
    )

    # --- Category classification V2 ---
    DECISION_CATEGORIES = {
        "architecture": [
            r"\b(?:architect|pattern|microservice|monolith|layer|component|module|design\s+system)\b",
            r"\b(?:arhitectur|structur|modul|component|layer)\b",
        ],
        "tooling": [
            r"\b(?:framework|library|package|tool|SDK|CLI|editor|IDE|linter|bundler)\b",
            r"\b(?:framework|librărie|pachet|tool|SDK|instrument)\b",
        ],
        "data": [
            r"\b(?:database|DB|SQL|NoSQL|schema|migration|table|index|query|ORM|cache)\b",
            r"\b(?:bază\s+de\s+date|schemă|migrare|tabel|index|cache)\b",
        ],
        "security": [
            r"\b(?:auth|token|JWT|OAuth|CORS|encrypt|hash|secret|credential|RBAC|permission)\b",
            r"\b(?:autentific|token|cript|secret|permisiu|securitat)",
        ],
        "process": [
            r"\b(?:CI/?CD|deploy|release|branch|merge|workflow|pipeline|test\s+strateg)",
            r"\b(?:deploy|release|branch|merge|workflow|pipeline|strategi)",
        ],
        "configuration": [
            r"\b(?:config|env\b|port\b|path\b|timeout|limit|threshold|setting|default\s+value)",
            r"\b(?:config|port\b|cale\b|timeout|limită|prag|setare|valoare\s+default)",
        ],
    }

    FACT_TYPES = {
        "configuration": [
            r"\b(?:default|port\b|path\b|config|env\b|setting|parameter|variable|value\s+is)",
            r"\b(?:default|port\b|cale\b|config|setare|parametru|variabil)\b",
        ],
        "constraint": [
            r"\b(?:require|limit|must\b|cannot|doesn'?t\s+support|incompatible|minimum|maximum)\b",
            r"\b(?:necesit|limită|trebuie|nu\s+(?:poate|suportă)|incompatibil|minim|maxim)",
        ],
        "compatibility": [
            r"\b(?:support|compatible|works?\s+with|version|platform|OS\b|browser)\b",
            r"\b(?:suport|compatibil|funcționează\s+cu|versiune|platformă)",
        ],
        "behavior": [
            r"\b(?:stores?|lives?\s+(?:in|at)|runs?\s+on|(?:is|gets?)\s+(?:called|triggered))\b",
            r"\b(?:stochez|se\s+află|rulează\s+pe|se\s+apelează|se\s+declanșează)",
        ],
    }

    # --- Certainty/Uncertainty words ---
    CERTAINTY_WORDS = {
        "decided", "final", "confirmed", "will", "must", "always",
        "definitely", "fixed", "resolved", "important", "critical",
        "am decis", "definitiv", "confirmat", "obligatoriu", "rezolvat",
    }

    UNCERTAINTY_WORDS = {
        "maybe", "perhaps", "could", "might", "possibly", "probably",
        "not sure", "consider", "thinking", "temporary", "workaround",
        "poate", "probabil", "posibil", "nu sunt sigur", "temporar",
    }

    def __init__(self):
        """Compilează toate pattern-urile o singură dată."""
        self.decisions = [(re.compile(p, re.IGNORECASE), w) for p, w in self.DECISION_PATTERNS]
        self.facts = [(re.compile(p, re.IGNORECASE), w) for p, w in self.FACT_PATTERNS]
        self.resolutions = [(re.compile(p, re.IGNORECASE), w) for p, w in self.RESOLUTION_PATTERNS]

        # V2: Negative patterns compilate
        self.negatives = [re.compile(p, re.IGNORECASE) for p in self.NEGATIVE_PATTERNS]

        # V2: Category classifiers compilate
        self.decision_classifiers = {
            cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in self.DECISION_CATEGORIES.items()
        }
        self.fact_classifiers = {
            ft: [re.compile(p, re.IGNORECASE) for p in patterns]
            for ft, patterns in self.FACT_TYPES.items()
        }

        # Compilează certainty/uncertainty ca set lowercased
        self.certainty = {w.lower() for w in self.CERTAINTY_WORDS}
        self.uncertainty = {w.lower() for w in self.UNCERTAINTY_WORDS}


# Singleton — compilat la import
_PATTERNS = ExtractionPatterns()


# ============================================================
# 2. CONFIDENCE SCORER (3 factori)
# ============================================================

class ConfidenceScorer:
    """Scoring transparent cu 3 factori, inspirat din EAN CLI mode_controller.py."""

    @staticmethod
    def score(text: str, pattern_weight: float, item_type: str) -> float:
        """
        Calculează confidence score cu 3 factori:
        1. pattern_weight (0.0 - 0.50) — forța match-ului regex
        2. certainty_bonus (0.0 - 0.30) — prezența cuvintelor de certitudine
        3. context_bonus (0.0 - 0.20) — calitatea contextului (lungime, structură)

        Returns: float 0.0 - 1.0
        """
        text_lower = text.lower()
        words = set(text_lower.split())

        # Factor 1: Pattern weight (preluat direct din match)
        f1 = min(0.60, pattern_weight)

        # Factor 2: Certainty bonus
        certainty_hits = len(words & _PATTERNS.certainty)
        uncertainty_hits = len(words & _PATTERNS.uncertainty)
        f2 = min(0.30, certainty_hits * 0.10) - min(0.20, uncertainty_hits * 0.10)
        f2 = max(0.0, f2)

        # Factor 3: Context bonus
        f3 = 0.0
        # Lungime rezonabilă (nu prea scurtă, nu prea lungă)
        text_len = len(text.strip())
        if 20 < text_len < 500:
            f3 += 0.05
        if 50 < text_len < 300:
            f3 += 0.05
        # Structură (conține explicație/motivație)
        if any(w in text_lower for w in ["because", "since", "due to", "pentru că", "deoarece"]):
            f3 += 0.05
        # Specificity (conține nume tehnice)
        if re.search(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+|[a-z]+_[a-z]+|\.[a-z]{2,4}\b", text):
            f3 += 0.05
        f3 = min(0.20, f3)

        total = f1 + f2 + f3
        return round(min(1.0, total), 3)


# ============================================================
# 3. DUPLICATE DETECTOR (Jaccard, inspirat din synthesis.py)
# ============================================================

class DuplicateDetector:
    """Detectare duplicate cu Jaccard similarity pe cuvinte."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalizare text pentru comparație."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def jaccard_similarity(text1: str, text2: str) -> float:
        """Jaccard similarity pe cuvinte (exact ca în EAN CLI synthesis.py)."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    @classmethod
    def is_duplicate(cls, new_text: str, existing_texts: List[str],
                     threshold: float = 0.55) -> bool:
        """Verifică dacă new_text e duplicat al unui text existent."""
        normalized_new = cls.normalize_text(new_text)
        if len(normalized_new) < 5:
            return True  # Prea scurt — tratează ca duplicat

        for existing in existing_texts:
            normalized_existing = cls.normalize_text(existing)
            sim = cls.jaccard_similarity(normalized_new, normalized_existing)
            if sim >= threshold:
                return True
        return False


# ============================================================
# 4. KNOWLEDGE EXTRACTOR
# ============================================================

class KnowledgeExtractor:
    """Extractor principal. Procesează mesajele unei sesiuni și extrage knowledge."""

    # Thresholds V1 — calibrate pe date reale (propoziții singulare de la agenți)
    # Scoruri tipice: 0.55-0.80. Threshold sub best-case dar peste noise.
    THRESHOLDS = {
        "decision": 0.65,
        "fact": 0.55,
        "resolution": 0.65,
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.scorer = ConfidenceScorer()
        self.dedup = DuplicateDetector()
        self._existing_cache: Dict[str, List[str]] = {}

    def _load_existing(self, project_path: str) -> None:
        """Încarcă textele existente pentru dedup."""
        cursor = self.conn.cursor()

        # Decisions
        cursor.execute(
            "SELECT title FROM decisions WHERE project_path = ? AND status = 'active'",
            (project_path,)
        )
        self._existing_cache["decision"] = [r[0] for r in cursor.fetchall()]

        # Facts
        cursor.execute(
            "SELECT fact FROM learned_facts WHERE project_path = ? AND is_active = 1",
            (project_path,)
        )
        self._existing_cache["fact"] = [r[0] for r in cursor.fetchall()]

        # Resolutions
        cursor.execute(
            "SELECT resolution FROM error_resolutions WHERE project_path = ?",
            (project_path,)
        )
        self._existing_cache["resolution"] = [r[0] for r in cursor.fetchall()]

    def extract_from_transcript(self, session_id: str,
                                 project_path: str) -> List[Dict]:
        """
        Extrage knowledge din mesajele unei sesiuni.
        Returnează lista de items cu {type, text, confidence, source_text}.
        """
        cursor = self.conn.cursor()

        # Citește mesajele asistentului din sesiune
        cursor.execute("""
            SELECT content FROM messages
            WHERE session_id = ? AND role = 'assistant'
            AND content IS NOT NULL AND length(content) > 20
            ORDER BY id
        """, (session_id,))

        messages = [r[0] for r in cursor.fetchall()]
        if not messages:
            return []

        # Încarcă existente pentru dedup
        self._load_existing(project_path)

        items = []
        seen_texts = set()  # Dedup intra-sesiune

        for msg in messages:
            # Procesează fiecare propoziție/linie
            lines = self._split_into_segments(msg)
            for line in lines:
                extracted = self._classify_and_score(line)
                if not extracted:
                    continue

                item_type, matched_text, confidence = extracted

                # Verifică threshold
                if confidence < self.THRESHOLDS[item_type]:
                    continue

                # Dedup intra-sesiune
                norm = self.dedup.normalize_text(matched_text)
                if norm in seen_texts:
                    continue
                seen_texts.add(norm)

                # Dedup cu existente
                existing = self._existing_cache.get(item_type, [])
                if self.dedup.is_duplicate(matched_text, existing):
                    continue

                # V2: Auto-classify category/type
                extra = {}
                if item_type == "decision":
                    extra["category"] = self._classify_decision_category(line)
                elif item_type == "fact":
                    extra["fact_type"] = self._classify_fact_type(line)
                    # 18B: facts also get category from decision classifier
                    extra["category"] = self._classify_decision_category(line)

                # 18B: Extract topic tags
                topics = self._extract_topics(line)
                if topics:
                    extra["topics"] = topics

                items.append({
                    "type": item_type,
                    "text": matched_text.strip(),
                    "confidence": confidence,
                    "source_text": line[:200],
                    **extra,
                })

                # Adaugă la existing cache (pentru dedup intra-batch)
                existing.append(matched_text)

        return items

    def _is_negative(self, text: str) -> bool:
        """V2: Verifică dacă textul match-uiește un negative pattern."""
        for neg in _PATTERNS.negatives:
            if neg.search(text):
                return True
        return False

    def _classify_decision_category(self, text: str) -> str:
        """V2: Auto-clasifică categoria deciziei (default: technical)."""
        text_lower = text.lower()
        best_cat = "technical"
        best_hits = 0
        for cat, patterns in _PATTERNS.decision_classifiers.items():
            hits = sum(1 for p in patterns if p.search(text_lower))
            if hits > best_hits:
                best_hits = hits
                best_cat = cat
        return best_cat

    def _classify_fact_type(self, text: str) -> str:
        """V2: Auto-clasifică tipul factului (default: technical)."""
        text_lower = text.lower()
        best_ft = "technical"
        best_hits = 0
        for ft, patterns in _PATTERNS.fact_classifiers.items():
            hits = sum(1 for p in patterns if p.search(text_lower))
            if hits > best_hits:
                best_hits = hits
                best_ft = ft
        return best_ft

    def _extract_topics(self, text: str) -> str:
        """18B: Extrage topic tags din text. Returnează comma-separated lowercase."""
        matches = set()
        for m in _PATTERNS.TECH_TERM_PATTERN.finditer(text):
            matches.add(m.group(1).lower().replace('.', ''))
        # Limit to 5 most relevant topics
        return ",".join(sorted(matches)[:5]) if matches else ""

    def _validate_matched_text(self, text: str) -> bool:
        """V2: Validează textul extras — exclude noise."""
        text = text.strip()
        # Prea scurt (sub 3 cuvinte reale)
        words = [w for w in text.split() if len(w) > 1]
        if len(words) < 3:
            return False
        # Pure code (doar simboluri + keywords)
        alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
        if alpha_ratio < 0.4:
            return False
        # Doar un path/url
        if re.match(r"^[/~][\w/.-]+$", text) or re.match(r"^https?://", text):
            return False
        return True

    def _split_into_segments(self, text: str) -> List[str]:
        """Împarte textul în segmente procesabile (propoziții/linii). V2: filtering îmbunătățit."""
        segments = []
        in_code_block = False

        for line in text.split("\n"):
            line = line.strip()

            # V2: Track code blocks
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue

            if len(line) < 15:
                continue
            # Skip linii care sunt doar cod sau formatting
            if line.startswith("    ") or line.startswith("| "):
                continue
            if line.startswith("#") and len(line) < 80:
                continue
            # V2: Skip linii care sunt doar referințe la fișiere/paths
            if re.match(r"^[-*•]\s*`[^`]+`\s*$", line):
                continue
            # V2: Skip markdown links
            if re.match(r"^[-*•]\s*\[.+\]\(.+\)\s*$", line):
                continue

            segments.append(line)

        # Dacă nu avem linii, try propoziții
        if not segments:
            sentences = re.split(r"[.!?]+\s+", text)
            segments = [s.strip() for s in sentences if len(s.strip()) > 15]

        return segments[:200]  # Limită pentru sesiuni foarte lungi

    def _classify_and_score(self, text: str) -> Optional[Tuple[str, str, float]]:
        """
        Clasifică textul și returnează (type, matched_text, confidence).
        Returnează None dacă nu match-uiește niciun pattern.
        V2: Adaugă negative check + matched text validation.
        """
        # V2: Negative pattern check — rejectează meta-discuții, întrebări, ipoteze
        if self._is_negative(text):
            return None

        best_match = None
        best_score = 0.0

        # Verifică resolutions PRIMUL (prioritate — rezolvările sunt cele mai valoroase)
        for pattern, weight in _PATTERNS.resolutions:
            m = pattern.search(text)
            if m:
                matched = m.group(1) if m.lastindex else m.group(0)
                # V2: validate matched text
                if not self._validate_matched_text(matched):
                    continue
                score = self.scorer.score(text, weight, "resolution")
                if score > best_score:
                    best_match = ("resolution", matched, score)
                    best_score = score

        # Apoi decisions
        for pattern, weight in _PATTERNS.decisions:
            m = pattern.search(text)
            if m:
                matched = m.group(1) if m.lastindex else m.group(0)
                if not self._validate_matched_text(matched):
                    continue
                score = self.scorer.score(text, weight, "decision")
                if score > best_score:
                    best_match = ("decision", matched, score)
                    best_score = score

        # Apoi facts (cel mai permisiv — doar dacă nu e altceva mai bun)
        for pattern, weight in _PATTERNS.facts:
            m = pattern.search(text)
            if m:
                matched = m.group(1) if m.lastindex else m.group(0)
                if not self._validate_matched_text(matched):
                    continue
                score = self.scorer.score(text, weight, "fact")
                if score > best_score:
                    best_match = ("fact", matched, score)
                    best_score = score

        return best_match

    def save_extracted(self, items: List[Dict], session_id: str,
                       project_path: str) -> Dict[str, int]:
        """Salvează items extrase în tabelele existente. Returnează counts."""
        cursor = self.conn.cursor()
        branch = get_current_branch()
        counts = {"decision": 0, "fact": 0, "resolution": 0}

        for item in items:
            try:
                if item["type"] == "decision":
                    # V2: Auto-classified category, 18B: topics
                    category = item.get("category", "technical")
                    topics = item.get("topics", "")
                    cursor.execute("""
                        INSERT INTO decisions
                        (title, description, category, confidence, status,
                         project_path, source_session, created_by,
                         branch, auto_extracted, extraction_confidence, source_session_id, topics)
                        VALUES (?, ?, ?, 'medium', 'active',
                                ?, ?, 'auto',
                                ?, 1, ?, ?, ?)
                    """, (
                        item["text"][:200],
                        f"Auto-extracted: {item['source_text'][:300]}",
                        category,
                        project_path,
                        session_id,
                        branch,
                        item["confidence"],
                        session_id,
                        topics,
                    ))
                    counts["decision"] += 1

                elif item["type"] == "fact":
                    # V2: Auto-classified fact_type, 18B: topics + category
                    fact_type = item.get("fact_type", "technical")
                    topics = item.get("topics", "")
                    category = item.get("category", "")
                    cursor.execute("""
                        INSERT INTO learned_facts
                        (fact, fact_type, category, confidence, is_active,
                         project_path, source_session, created_by,
                         branch, auto_extracted, extraction_confidence, source_session_id, topics)
                        VALUES (?, ?, ?, 'medium', 1,
                                ?, ?, 'auto',
                                ?, 1, ?, ?, ?)
                    """, (
                        item["text"][:500],
                        fact_type,
                        category,
                        project_path,
                        session_id,
                        branch,
                        item["confidence"],
                        session_id,
                        topics,
                    ))
                    counts["fact"] += 1

                elif item["type"] == "resolution":
                    topics = item.get("topics", "")
                    cursor.execute("""
                        INSERT INTO error_resolutions
                        (error_summary, resolution, resolution_type,
                         project_path, source_session, created_by,
                         branch, auto_extracted, extraction_confidence, source_session_id, topics)
                        VALUES (?, ?, 'auto_extracted',
                                ?, ?, 'auto',
                                ?, 1, ?, ?, ?)
                    """, (
                        f"Auto-extracted from session {session_id}",
                        item["text"][:500],
                        project_path,
                        session_id,
                        branch,
                        item["confidence"],
                        session_id,
                        topics,
                    ))
                    counts["resolution"] += 1

            except Exception as e:
                # Nu oprește procesarea pentru o eroare la un singur item
                _log(f"save error ({item['type']}): {e}")
                continue

        self.conn.commit()
        return counts


# ============================================================
# 5. ENTRY POINT
# ============================================================

def _log(msg: str) -> None:
    """Log pe stderr (nu interferează cu stdout JSON)."""
    print(f"[KNOWLEDGE-EXTRACTOR] {msg}", file=sys.stderr, flush=True)


def run_extraction(session_id: str, project_path: Optional[str] = None,
                   db_path: Optional[str] = None) -> Dict:
    """
    Entry point principal. Apelat din handle_session_end().

    Args:
        session_id: ID-ul sesiunii de procesat
        project_path: Calea proiectului (opțional, default = CWD)
        db_path: Calea DB (opțional, default = v2_common.GLOBAL_DB)

    Returns:
        Dict cu statistici: {"extracted": N, "saved": {"decision": N, "fact": N, "resolution": N}}
    """
    if not session_id:
        return {"extracted": 0, "saved": {}, "error": "no session_id"}

    if not project_path:
        project_path = get_current_project_path()

    try:
        if db_path:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        else:
            conn = get_db()
    except Exception as e:
        _log(f"DB connection error: {e}")
        return {"extracted": 0, "saved": {}, "error": str(e)}

    # Verifică dacă coloanele de extraction există
    try:
        conn.execute("SELECT auto_extracted FROM decisions LIMIT 0")
    except sqlite3.OperationalError:
        # Coloanele nu există încă — rulează migrarea
        _ensure_extraction_columns(conn)

    extractor = KnowledgeExtractor(conn)

    try:
        items = extractor.extract_from_transcript(session_id, project_path)
        if not items:
            conn.close()
            return {"extracted": 0, "saved": {"decision": 0, "fact": 0, "resolution": 0}}

        counts = extractor.save_extracted(items, session_id, project_path)
        conn.close()

        total_saved = sum(counts.values())
        if total_saved > 0:
            _log(f"session {session_id}: extracted {len(items)} candidates, "
                 f"saved {total_saved} (D:{counts['decision']} F:{counts['fact']} R:{counts['resolution']})")

        return {"extracted": len(items), "saved": counts}

    except Exception as e:
        _log(f"extraction error: {e}")
        conn.close()
        return {"extracted": 0, "saved": {}, "error": str(e)}


def _ensure_extraction_columns(conn: sqlite3.Connection) -> None:
    """Adaugă coloanele de extraction dacă nu există (safe ALTER TABLE)."""
    columns = [
        ("decisions", "auto_extracted", "INTEGER DEFAULT 0"),
        ("decisions", "extraction_confidence", "REAL"),
        ("decisions", "source_session_id", "TEXT"),
        ("decisions", "topics", "TEXT"),
        ("learned_facts", "auto_extracted", "INTEGER DEFAULT 0"),
        ("learned_facts", "extraction_confidence", "REAL"),
        ("learned_facts", "source_session_id", "TEXT"),
        ("learned_facts", "topics", "TEXT"),
        ("error_resolutions", "auto_extracted", "INTEGER DEFAULT 0"),
        ("error_resolutions", "extraction_confidence", "REAL"),
        ("error_resolutions", "source_session_id", "TEXT"),
        ("error_resolutions", "topics", "TEXT"),
    ]
    for table, col, col_type in columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Coloana există deja
    conn.commit()


# ============================================================
# CLI MODE (pentru testare directă)
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge Extractor V1")
    parser.add_argument("session_id", nargs="?", help="Session ID to process")
    parser.add_argument("--project", help="Project path")
    parser.add_argument("--db", help="DB path")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't save")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    sid = args.session_id or get_current_session_id()
    if not sid:
        print("Usage: knowledge_extractor.py <session_id>", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        # Dry run: extrage dar nu salvează
        try:
            conn = sqlite3.connect(args.db or str(PROJECT_ROOT / "global.db"))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _ensure_extraction_columns(conn)
            extractor = KnowledgeExtractor(conn)
            items = extractor.extract_from_transcript(sid, args.project or get_current_project_path())
            conn.close()

            if args.json:
                print(json.dumps(items, indent=2, ensure_ascii=False))
            else:
                print(f"Found {len(items)} candidates:")
                for item in items:
                    print(f"  [{item['type'].upper()}] (conf={item['confidence']:.3f}) {item['text'][:80]}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        result = run_extraction(sid, project_path=args.project, db_path=args.db)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            saved = result.get("saved", {})
            print(f"Extracted: {result.get('extracted', 0)} candidates")
            print(f"Saved: D={saved.get('decision', 0)} F={saved.get('fact', 0)} R={saved.get('resolution', 0)}")
            if result.get("error"):
                print(f"Error: {result['error']}")
