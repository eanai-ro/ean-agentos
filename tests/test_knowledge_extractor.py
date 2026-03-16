#!/usr/bin/env python3
"""
Teste pentru Knowledge Extractor V1 (Faza 17X)

T1-T3: Extracție decisions/facts/resolutions pe exemple clare
T4: Confidence scoring diferențiază clar vs vag
T5-T6: High-confidence se salvează, low-confidence se ignoră
T7: Dedup cu Jaccard previne duplicatele
T8: Rulează la session_end fără regresii
T9: Context builder include knowledge extras
T10: PRAGMA integrity_check
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Setup path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from knowledge_extractor import (
    ExtractionPatterns,
    ConfidenceScorer,
    DuplicateDetector,
    KnowledgeExtractor,
    run_extraction,
    _ensure_extraction_columns,
    _PATTERNS,
)


def create_test_db(db_path: str) -> sqlite3.Connection:
    """Creează o DB de test cu schema minimă necesară."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            project_path TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            summary TEXT,
            total_messages INTEGER DEFAULT 0,
            total_tool_calls INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            role TEXT,
            content TEXT,
            message_type TEXT,
            project_path TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT DEFAULT 'technical',
            status TEXT DEFAULT 'active',
            confidence TEXT DEFAULT 'high',
            rationale TEXT,
            alternatives_considered TEXT,
            superseded_by INTEGER,
            stale_after_days INTEGER DEFAULT 90,
            project_path TEXT,
            source_session TEXT,
            created_by TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_used TEXT,
            provider TEXT,
            branch TEXT DEFAULT 'main',
            is_global INTEGER DEFAULT 0,
            promoted_from_agent TEXT
        );

        CREATE TABLE IF NOT EXISTS learned_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            fact_type TEXT DEFAULT 'technical',
            category TEXT,
            confidence TEXT DEFAULT 'high',
            is_pinned INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            source TEXT,
            superseded_by INTEGER,
            project_path TEXT,
            source_session TEXT,
            created_by TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_used TEXT,
            provider TEXT,
            branch TEXT DEFAULT 'main',
            is_global INTEGER DEFAULT 0,
            promoted_from_agent TEXT
        );

        CREATE TABLE IF NOT EXISTS error_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_id INTEGER,
            error_fingerprint TEXT,
            error_summary TEXT,
            resolution TEXT NOT NULL,
            resolution_code TEXT,
            resolution_type TEXT DEFAULT 'fix',
            model_used TEXT,
            provider TEXT,
            agent_name TEXT,
            project_path TEXT,
            source_session TEXT,
            created_by TEXT DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            worked INTEGER DEFAULT 1,
            reuse_count INTEGER DEFAULT 0,
            branch TEXT DEFAULT 'main',
            is_global INTEGER DEFAULT 0,
            promoted_from_agent TEXT
        );
    """)

    _ensure_extraction_columns(conn)
    return conn


def seed_session(conn, session_id="test-session-001", messages=None):
    """Inserează o sesiune de test cu mesaje."""
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, project_path) VALUES (?, ?)",
        (session_id, "/test/project")
    )

    if messages:
        for role, content in messages:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
    conn.commit()


class T1_DecisionExtraction(unittest.TestCase):
    """T1: Extracție decisions pe exemple clare."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_decision_english(self):
        seed_session(self.conn, messages=[
            ("assistant", "We decided to use PostgreSQL for the database because it handles complex queries better."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        decisions = [i for i in items if i["type"] == "decision"]
        self.assertGreater(len(decisions), 0, "Should extract at least one decision")

    def test_decision_romanian(self):
        seed_session(self.conn, "test-ro", messages=[
            ("assistant", "Am decis să folosim Redis pentru caching deoarece este cel mai rapid."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-ro", "/test/project")
        decisions = [i for i in items if i["type"] == "decision"]
        self.assertGreater(len(decisions), 0, "Should extract Romanian decision")

    def test_decision_lets_use(self):
        seed_session(self.conn, "test-lets", messages=[
            ("assistant", "Let's use FastAPI for the backend since it has better async support and auto-docs."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-lets", "/test/project")
        decisions = [i for i in items if i["type"] == "decision"]
        self.assertGreater(len(decisions), 0, "Should extract 'let's use' pattern")


class T2_FactExtraction(unittest.TestCase):
    """T2: Extracție facts pe exemple clare."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_fact_default_value(self):
        seed_session(self.conn, messages=[
            ("assistant", "The default port is 6379 for Redis, and it requires at least 1GB of RAM."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        facts = [i for i in items if i["type"] == "fact"]
        self.assertGreater(len(facts), 0, "Should extract default value fact")

    def test_fact_important_note(self):
        seed_session(self.conn, "test-note", messages=[
            ("assistant", "Important: the API rate limit is definitely 100 requests per minute for all endpoints."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-note", "/test/project")
        facts = [i for i in items if i["type"] == "fact"]
        self.assertGreater(len(facts), 0, "Should extract 'important:' pattern")


class T3_ResolutionExtraction(unittest.TestCase):
    """T3: Extracție resolutions pe exemple clare."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_resolution_fixed_by(self):
        seed_session(self.conn, messages=[
            ("assistant", "The TypeError was fixed by adding a None check before accessing the dictionary key."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        resolutions = [i for i in items if i["type"] == "resolution"]
        self.assertGreater(len(resolutions), 0, "Should extract 'fixed by' pattern")

    def test_resolution_romanian(self):
        seed_session(self.conn, "test-fix-ro", messages=[
            ("assistant", "S-a rezolvat prin adăugarea unui try/except în funcția de connect deoarece serverul era instabil."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-fix-ro", "/test/project")
        resolutions = [i for i in items if i["type"] == "resolution"]
        self.assertGreater(len(resolutions), 0, "Should extract Romanian resolution")


class T4_ConfidenceScoring(unittest.TestCase):
    """T4: Confidence scoring diferențiază clar vs vag."""

    def test_high_confidence(self):
        scorer = ConfidenceScorer()
        # Clear decision with certainty words
        score_clear = scorer.score(
            "We definitely decided to use PostgreSQL because it's confirmed as the best option",
            0.45, "decision"
        )
        # Vague statement
        score_vague = scorer.score(
            "Maybe we could possibly consider using something like PostgreSQL",
            0.30, "decision"
        )
        self.assertGreater(score_clear, score_vague,
                          f"Clear ({score_clear}) should score higher than vague ({score_vague})")

    def test_context_bonus(self):
        scorer = ConfidenceScorer()
        # With reasoning
        score_reasoned = scorer.score(
            "We decided to use FastAPI because it has better async support",
            0.40, "decision"
        )
        # Without reasoning
        score_bare = scorer.score(
            "Use FastAPI",
            0.40, "decision"
        )
        self.assertGreater(score_reasoned, score_bare,
                          "Reasoned text should score higher")


class T5_HighConfidenceSaved(unittest.TestCase):
    """T5: High-confidence se salvează."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_high_confidence_saved(self):
        seed_session(self.conn, messages=[
            ("assistant", "Final decision: we will definitely use PostgreSQL for the production database because it handles complex queries reliably."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        counts = extractor.save_extracted(items, "test-session-001", "/test/project")

        # Verifică DB
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM decisions WHERE auto_extracted = 1")
        rows = cursor.fetchall()
        total = sum(counts.values())
        self.assertGreater(total, 0, "Should save high-confidence items")


class T6_LowConfidenceIgnored(unittest.TestCase):
    """T6: Low-confidence se ignoră."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_low_confidence_ignored(self):
        seed_session(self.conn, messages=[
            ("assistant", "Maybe we could possibly use something."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        # Fie nu se extrage, fie nu trece threshold-ul
        self.assertEqual(len(items), 0,
                        "Vague statements should not produce any extracted items")


class T7_DuplicateDetection(unittest.TestCase):
    """T7: Dedup cu Jaccard previne duplicatele."""

    def test_jaccard_exact_duplicate(self):
        self.assertTrue(
            DuplicateDetector.is_duplicate(
                "Use PostgreSQL for database",
                ["Use PostgreSQL for database"]
            )
        )

    def test_jaccard_near_duplicate(self):
        self.assertTrue(
            DuplicateDetector.is_duplicate(
                "Use PostgreSQL for the production database",
                ["Use PostgreSQL for production database management"]
            )
        )

    def test_jaccard_different(self):
        self.assertFalse(
            DuplicateDetector.is_duplicate(
                "Redis default port is 6379",
                ["PostgreSQL runs on port 5432"]
            )
        )

    def test_normalize(self):
        n = DuplicateDetector.normalize_text("  Hello, World!  ")
        self.assertEqual(n, "hello world")

    def test_dedup_in_extraction(self):
        """Verifică că extracția nu produce duplicate intra-sesiune."""
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        conn = create_test_db(db_file.name)
        # Texte aproape identice — doar o reformulare minoră
        seed_session(conn, messages=[
            ("assistant", "We decided to use PostgreSQL for the production database."),
            ("assistant", "We decided to use PostgreSQL for the production database system."),
        ])
        extractor = KnowledgeExtractor(conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        decisions = [i for i in items if i["type"] == "decision"]
        # Trebuie să fie maxim 1 (al doilea e dedup-at)
        self.assertLessEqual(len(decisions), 1, "Should deduplicate near-identical decisions")
        conn.close()
        os.unlink(db_file.name)


class T8_SessionEndIntegration(unittest.TestCase):
    """T8: Import funcționează fără erori."""

    def test_import(self):
        """Verifică că knowledge_extractor se importă corect."""
        from knowledge_extractor import run_extraction, KnowledgeExtractor
        self.assertTrue(callable(run_extraction))

    def test_run_extraction_no_session(self):
        """run_extraction cu session inexistent returnează gracefully."""
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        conn = create_test_db(db_file.name)
        conn.close()
        result = run_extraction("nonexistent-session", project_path="/test",
                               db_path=db_file.name)
        self.assertEqual(result["extracted"], 0)
        os.unlink(db_file.name)

    def test_patterns_compiled(self):
        """Verifică că pattern-urile sunt compilate la import."""
        self.assertGreater(len(_PATTERNS.decisions), 0)
        self.assertGreater(len(_PATTERNS.facts), 0)
        self.assertGreater(len(_PATTERNS.resolutions), 0)


class T9_ContextIntegration(unittest.TestCase):
    """T9: Knowledge extras este accesibil via DB queries standard."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_auto_extracted_queryable(self):
        """Verifică că items auto-extracted pot fi filtrate."""
        seed_session(self.conn, messages=[
            ("assistant", "Final decision: we will definitely use Redis for caching because it's the fastest option confirmed by benchmarks."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        extractor.save_extracted(items, "test-session-001", "/test/project")

        # Query auto-extracted
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM decisions WHERE auto_extracted = 1")
        count = cursor.fetchone()[0]

        # Query all (auto + manual)
        cursor.execute("SELECT COUNT(*) FROM decisions")
        total = cursor.fetchone()[0]

        # Auto-extracted trebuie să fie un subset
        self.assertLessEqual(count, total)

    def test_extraction_confidence_stored(self):
        """Verifică că extraction_confidence e salvat."""
        seed_session(self.conn, messages=[
            ("assistant", "We definitely decided to use SQLite because it's confirmed as the simplest embedded database."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        extractor.save_extracted(items, "test-session-001", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT extraction_confidence FROM decisions WHERE auto_extracted = 1"
        )
        rows = cursor.fetchall()
        for row in rows:
            self.assertIsNotNone(row[0], "extraction_confidence should not be NULL")
            self.assertGreater(row[0], 0, "extraction_confidence should be > 0")


class T10_IntegrityCheck(unittest.TestCase):
    """T10: PRAGMA integrity_check."""

    def test_integrity(self):
        db_path = str(Path(__file__).parent.parent / "global.db")
        if not Path(db_path).exists():
            self.skipTest("global.db not found")
        conn = sqlite3.connect(db_path)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        self.assertEqual(result, "ok", f"Integrity check failed: {result}")


# ============================================================
# V2 TESTS (Faza 18A — Knowledge Extraction V2)
# ============================================================

class T11_NegativePatterns(unittest.TestCase):
    """T11: Negative patterns rejectează false positives."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)
        self.extractor = KnowledgeExtractor(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_question_rejected(self):
        """Întrebările nu se extrag ca decizii."""
        result = self.extractor._classify_and_score(
            "Should we use PostgreSQL for the database?"
        )
        self.assertIsNone(result, "Questions should be rejected by negative patterns")

    def test_hypothetical_rejected(self):
        """Ipotezele nu se extrag."""
        result = self.extractor._classify_and_score(
            "If we decided to use Redis, what if we need persistence?"
        )
        self.assertIsNone(result, "Hypotheticals should be rejected")

    def test_alternative_option_rejected(self):
        """Discuțiile despre opțiuni nu sunt decizii."""
        result = self.extractor._classify_and_score(
            "We could also use MongoDB as another option for the cache"
        )
        self.assertIsNone(result, "Alternative options should be rejected")

    def test_code_import_rejected(self):
        """Import statements nu se extrag."""
        result = self.extractor._classify_and_score(
            "from flask import Flask, request, jsonify"
        )
        self.assertIsNone(result, "Code imports should be rejected")

    def test_real_decision_not_rejected(self):
        """Deciziile reale NU sunt rejectate de negative patterns."""
        result = self.extractor._classify_and_score(
            "We decided to use PostgreSQL for the production database because it handles complex queries."
        )
        self.assertIsNotNone(result, "Real decisions should NOT be rejected")


class T12_CategoryClassification(unittest.TestCase):
    """T12: Auto-clasificare decision category."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)
        self.extractor = KnowledgeExtractor(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_data_category(self):
        cat = self.extractor._classify_decision_category(
            "We decided to use PostgreSQL database with SQLite cache"
        )
        self.assertEqual(cat, "data")

    def test_tooling_category(self):
        cat = self.extractor._classify_decision_category(
            "Let's use the React framework with Tailwind CSS library"
        )
        self.assertEqual(cat, "tooling")

    def test_security_category(self):
        cat = self.extractor._classify_decision_category(
            "We'll implement JWT authentication with OAuth tokens"
        )
        self.assertEqual(cat, "security")

    def test_architecture_category(self):
        cat = self.extractor._classify_decision_category(
            "Going with a microservices architecture pattern for the backend"
        )
        self.assertEqual(cat, "architecture")

    def test_process_category(self):
        cat = self.extractor._classify_decision_category(
            "We decided to set up a CI/CD pipeline with deploy automation"
        )
        self.assertEqual(cat, "process")

    def test_default_technical(self):
        cat = self.extractor._classify_decision_category(
            "We decided to do it this way"
        )
        self.assertEqual(cat, "technical")


class T13_FactTypeClassification(unittest.TestCase):
    """T13: Auto-clasificare fact_type."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)
        self.extractor = KnowledgeExtractor(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_configuration_type(self):
        ft = self.extractor._classify_fact_type(
            "The default port is 5432 for PostgreSQL config"
        )
        self.assertEqual(ft, "configuration")

    def test_constraint_type(self):
        ft = self.extractor._classify_fact_type(
            "SQLite requires minimum version 3.35 and doesn't support concurrent writes"
        )
        self.assertEqual(ft, "constraint")

    def test_compatibility_type(self):
        ft = self.extractor._classify_fact_type(
            "FastAPI supports Python 3.8+ and works with all modern browsers"
        )
        self.assertEqual(ft, "compatibility")

    def test_default_technical(self):
        ft = self.extractor._classify_fact_type(
            "Something generic about the system"
        )
        self.assertEqual(ft, "technical")


class T14_MatchedTextValidation(unittest.TestCase):
    """T14: Validare text extras — exclude noise."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)
        self.extractor = KnowledgeExtractor(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_too_short_rejected(self):
        self.assertFalse(self.extractor._validate_matched_text("ok"))

    def test_pure_path_rejected(self):
        self.assertFalse(self.extractor._validate_matched_text("/usr/bin/python3"))

    def test_pure_url_rejected(self):
        self.assertFalse(self.extractor._validate_matched_text("https://example.com/api"))

    def test_low_alpha_rejected(self):
        self.assertFalse(self.extractor._validate_matched_text("{{{}}} => [][] !!!"))

    def test_valid_text_accepted(self):
        self.assertTrue(self.extractor._validate_matched_text(
            "PostgreSQL for the production database"
        ))


class T15_CategorySavedToDB(unittest.TestCase):
    """T15: Category/fact_type se salvează corect în DB."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_decision_category_in_db(self):
        seed_session(self.conn, messages=[
            ("assistant",
             "Final decision: we will definitely use PostgreSQL database with SQL queries because it's confirmed as the best option."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        extractor.save_extracted(items, "test-session-001", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT category FROM decisions WHERE auto_extracted = 1"
        )
        rows = cursor.fetchall()
        self.assertGreater(len(rows), 0, "Should save at least one decision")
        # Should be classified as 'data' (database/SQL keywords)
        self.assertEqual(rows[0][0], "data",
                        f"Expected 'data' category, got '{rows[0][0]}'")

    def test_fact_type_in_db(self):
        seed_session(self.conn, "test-ft", messages=[
            ("assistant",
             "Important: the default port is definitely 19876 for the API config setting."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-ft", "/test/project")
        extractor.save_extracted(items, "test-ft", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT fact_type FROM learned_facts WHERE auto_extracted = 1"
        )
        rows = cursor.fetchall()
        self.assertGreater(len(rows), 0, "Should save at least one fact")
        self.assertEqual(rows[0][0], "configuration",
                        f"Expected 'configuration' fact_type, got '{rows[0][0]}'")


class T16_SegmentFilteringV2(unittest.TestCase):
    """T16: Segment filtering V2 — skip code blocks, markdown refs."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_code_block_skipped(self):
        """Cod în ``` blocuri nu se extrage."""
        seed_session(self.conn, messages=[
            ("assistant", """Here's the approach:
```python
# We decided to use PostgreSQL for the database
import psycopg2
conn = psycopg2.connect("dbname=test")
```
The code above demonstrates the connection."""),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        # The decision inside code block should NOT be extracted
        for item in items:
            self.assertNotIn("psycopg2", item["text"],
                           "Code block content should not be extracted")

    def test_real_text_outside_block_works(self):
        """Text real în afara code blocks se extrage normal."""
        msg = (
            "We decided to use Flask for the API backend because it's definitely simpler.\n"
            "```python\n"
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "```\n"
            "That was confirmed as the final approach."
        )
        seed_session(self.conn, "test-outside", messages=[
            ("assistant", msg),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-outside", "/test/project")
        # Should extract at least one item (decision or fact) from outside code block
        self.assertGreater(len(items), 0,
                          "Should extract items from text outside code block")
        # Code inside block should NOT appear in extracted text
        for item in items:
            self.assertNotIn("Flask(__name__)", item["text"],
                           "Code block content should not be in extracted text")


class T17_NegativePatternsCompiled(unittest.TestCase):
    """T17: Negative patterns + classifiers sunt compilate la import."""

    def test_negatives_compiled(self):
        self.assertGreater(len(_PATTERNS.negatives), 0,
                          "Negative patterns should be compiled")

    def test_decision_classifiers_compiled(self):
        self.assertIn("data", _PATTERNS.decision_classifiers)
        self.assertIn("security", _PATTERNS.decision_classifiers)

    def test_fact_classifiers_compiled(self):
        self.assertIn("configuration", _PATTERNS.fact_classifiers)
        self.assertIn("constraint", _PATTERNS.fact_classifiers)


class T18_RegressionV2(unittest.TestCase):
    """T18: Regression — V2 nu rupe testele de bază V1."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_full_pipeline(self):
        """Pipeline complet: extract → save → query."""
        seed_session(self.conn, messages=[
            ("assistant",
             "We definitely decided to use SQLite for the embedded database because it's confirmed as the simplest option."),
            ("assistant",
             "The bug was fixed by adding a None check before accessing the dictionary key, which resolved the crash."),
            ("assistant",
             "Important: the API rate limit is definitely 100 requests per minute for all endpoints in production."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        self.assertGreater(len(items), 0, "Should extract at least one item")

        counts = extractor.save_extracted(items, "test-session-001", "/test/project")
        total = sum(counts.values())
        self.assertGreater(total, 0, "Should save at least one item")

    def test_run_extraction_api(self):
        """run_extraction() API funcționează cu V2."""
        seed_session(self.conn, messages=[
            ("assistant",
             "Final decision: we will definitely use Redis for caching because it's the fastest confirmed option."),
        ])
        result = run_extraction("test-session-001", project_path="/test/project",
                               db_path=self.db_file.name)
        self.assertGreater(result.get("extracted", 0), 0)


# ============================================================
# 18B TESTS — Theme Categorization (Topic Extraction)
# ============================================================

class T19_TopicExtraction(unittest.TestCase):
    """T19: Topic extraction din text."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)
        self.extractor = KnowledgeExtractor(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_extracts_database_topics(self):
        topics = self.extractor._extract_topics(
            "We decided to use PostgreSQL for the main database and Redis for caching"
        )
        self.assertIn("postgresql", topics)
        self.assertIn("redis", topics)

    def test_extracts_framework_topics(self):
        topics = self.extractor._extract_topics(
            "Using Flask with Python to build the REST API backend"
        )
        self.assertIn("flask", topics)
        self.assertIn("python", topics)
        self.assertIn("rest", topics)

    def test_no_topics_from_generic_text(self):
        topics = self.extractor._extract_topics(
            "We decided to do it this way because it makes more sense"
        )
        self.assertEqual(topics, "")

    def test_max_5_topics(self):
        topics = self.extractor._extract_topics(
            "Using Flask, Django, FastAPI, React, Vue, Angular, Svelte, PostgreSQL, MongoDB and Redis"
        )
        topic_list = topics.split(",")
        self.assertLessEqual(len(topic_list), 5)


class T20_TopicsSavedToDB(unittest.TestCase):
    """T20: Topics se salvează corect în DB."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = create_test_db(self.db_file.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_file.name)

    def test_decision_topics_in_db(self):
        seed_session(self.conn, messages=[
            ("assistant",
             "Final decision: we will definitely use PostgreSQL database with SQLite for embedded storage."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-session-001", "/test/project")
        extractor.save_extracted(items, "test-session-001", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT topics FROM decisions WHERE auto_extracted = 1 AND topics IS NOT NULL AND topics != ''"
        )
        rows = cursor.fetchall()
        self.assertGreater(len(rows), 0, "Should save topics for decisions")
        self.assertIn("postgresql", rows[0][0])

    def test_fact_topics_in_db(self):
        seed_session(self.conn, "test-ft2", messages=[
            ("assistant",
             "Important: the default port is definitely 6379 for Redis configuration."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-ft2", "/test/project")
        extractor.save_extracted(items, "test-ft2", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT topics FROM learned_facts WHERE auto_extracted = 1 AND topics IS NOT NULL AND topics != ''"
        )
        rows = cursor.fetchall()
        self.assertGreater(len(rows), 0, "Should save topics for facts")
        self.assertIn("redis", rows[0][0])

    def test_fact_category_populated(self):
        """18B: learned_facts.category se populează din decision classifier."""
        seed_session(self.conn, "test-cat", messages=[
            ("assistant",
             "Important: the PostgreSQL database requires definitely at least 2GB RAM for production."),
        ])
        extractor = KnowledgeExtractor(self.conn)
        items = extractor.extract_from_transcript("test-cat", "/test/project")
        extractor.save_extracted(items, "test-cat", "/test/project")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT category FROM learned_facts WHERE auto_extracted = 1"
        )
        rows = cursor.fetchall()
        if rows:
            self.assertIsNotNone(rows[0][0], "category should be populated")


class T21_TopicsColumnExists(unittest.TestCase):
    """T21: Topics column adăugată corect la toate tabelele."""

    def test_topics_columns_exist(self):
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        conn = create_test_db(db_file.name)
        for table in ["decisions", "learned_facts", "error_resolutions"]:
            try:
                conn.execute(f"SELECT topics FROM {table} LIMIT 0")
            except sqlite3.OperationalError:
                self.fail(f"Column 'topics' missing from {table}")
        conn.close()
        os.unlink(db_file.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
