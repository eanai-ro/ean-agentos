# DEV_LOG — Universal Agent Memory (ean-cc-mem-kit)

Jurnal de dezvoltare cu toate modificările semnificative.

---

## 2026-03-15 — Faza 18D: MCP Orchestration V1

### Concept
Orchestrare multi-agent **peer-to-peer prin DB** — fără proces central. Orice CLI (Claude Code, Gemini CLI, Codex CLI, Kimi CLI) poate crea proiecte, claim task-uri, participa la deliberări, trimite mesaje. Comunicarea e exclusiv prin polling SQLite.

### Fișiere Create

| Fișier | Linii | Scop |
|--------|-------|------|
| `migrations/017_orchestration.sql` | ~70 | Schema: 7 tabele + 8 indexuri |
| `scripts/orchestrator.py` | ~420 | Core engine: proiecte, task-uri, routing, leases, agents |
| `scripts/deliberation.py` | ~530 | Deliberation engine + Synthesizer (portat din EAN-AutoCode_AI) |
| `scripts/orch_api.py` | ~200 | Flask Blueprint: 12 REST endpoints |

### Fișiere Modificate

| Fișier | Ce s-a schimbat |
|--------|-----------------|
| `scripts/v2_common.py` | +VALID_CLI_NAMES, +ORCH_TASK_STATUSES, +DELIBERATION_PHASES, +7 event types |
| `scripts/init_db.py` | +ensure_orchestration_tables() — execută migrarea 017 |
| `scripts/web_server.py` | +Blueprint registration pentru orch_api |
| `scripts/mem` | +12 comenzi `mem orch` (create, status, add-task, tasks, claim, done, deliberate, propose, vote, send, messages, agents) |
| `mcp_server/tools.py` | +5 funcții orchestrare (orch_create_project, orch_manage_tasks, orch_deliberate, orch_message, orch_heartbeat) |
| `mcp_server/server.py` | +5 MCP tools (orch_project_create, orch_tasks, orch_deliberation, orch_messaging, orch_agent_heartbeat) |

### Tabele Noi (7)

| Tabel | Scop |
|-------|------|
| `orchestration_projects` | Proiecte orchestrate |
| `orch_tasks` | Task-uri cu lease-based ownership |
| `orch_sessions` | Sesiuni de deliberare (quick/deep/expert) |
| `orch_proposals` | Propuneri per rundă |
| `orch_votes` | Voturi |
| `orch_messages` | Mesaje inter-agent |
| `orch_agents` | Agent presence tracking |

### REST API Endpoints (12)

| Endpoint | Metodă | Scop |
|----------|--------|------|
| `/api/v1/orch/projects` | POST | Creează proiect |
| `/api/v1/orch/projects/<id>` | GET | Status proiect |
| `/api/v1/orch/tasks` | POST | Creează task |
| `/api/v1/orch/tasks` | GET | Listează task-uri |
| `/api/v1/orch/tasks/<id>/claim` | POST | Claim cu lease |
| `/api/v1/orch/tasks/<id>/complete` | POST | Complete/fail |
| `/api/v1/orch/deliberation` | POST | Creează sesiune |
| `/api/v1/orch/deliberation/<id>` | GET | Status sesiune |
| `/api/v1/orch/deliberation/<id>/respond` | POST | Propose/vote/advance/synthesize |
| `/api/v1/orch/messages` | POST | Trimite mesaj |
| `/api/v1/orch/messages` | GET | Citește mesaje |
| `/api/v1/orch/heartbeat` | POST | Heartbeat + status |

### MCP Tools Noi (5)

| Tool | Scop |
|------|------|
| `orch_project_create` | Creează proiect orchestrat |
| `orch_tasks` | Unified: create/claim/complete/fail/list |
| `orch_deliberation` | Unified: create/propose/vote/advance/synthesize/status |
| `orch_messaging` | Send/read mesaje inter-agent |
| `orch_agent_heartbeat` | Heartbeat + status agents |

### Arhitectură Cheie
- **Lease-based ownership** — claim task → UUID lease_token + expiry 30min → stale detection
- **Task routing** — scoring: strength match (0-40) + workload (0-30) + historical success (0-30)
- **Deliberation** — 3 nivele: quick (2 runde), deep (4), expert (6)
- **Consensus detection** — Jaccard similarity ≥0.25 între key points extrași din propuneri
- **Theme clustering** — 8 dimensiuni cu ~80 keywords (EN+RO)
- **Agreement matrix** — Jaccard pairwise între toate CLI-urile

### Teste T1-T25: PASSED

### Deviații față de plan
- CLI launcher NU implementat (conform plan — mută la V2)
- `update_project_status()` adăugat extra (nu în plan inițial)
- Threshold consens coborât de la 0.4 la 0.25 (pentru a funcționa cu propuneri scurte)

---

## 2026-03-15 — Faza 18C: Review UI (API + CLI)

### Modificări

**Dashboard API** (`scripts/dashboard_api.py` — MODIFICAT, +120 linii)
- `GET /api/review/pending` — items auto-extracted nerevizuite (decisions + facts + resolutions)
- `POST /api/review/approve` — aprobă item (auto_extracted = 2, confidence = confirmed)
- `POST /api/review/reject` — rejectează item (auto_extracted = -1, status/is_active = rejected/0)
- `GET /api/review/stats` — statistici pending/approved/rejected per type

**CLI** (`scripts/mem` — MODIFICAT)
- `mem review pending` — listează items de revizuit cu confidence + topics
- `mem review approve <type> <id>` — aprobă item
- `mem review reject <type> <id>` — rejectează item
- `mem review stats` — statistici review

### Convention auto_extracted
- `0` = manual (creat de utilizator)
- `1` = auto-extracted, pending review
- `2` = auto-extracted, approved
- `-1` = auto-extracted, rejected

### Decizii
- Review state stocat în `auto_extracted` column (nu coloană separată) — simplu, queryable
- Approve setează confidence='confirmed' — boost la scoring
- Reject setează status='rejected'/is_active=0 — nu mai apare în context

---

## 2026-03-15 — Faza 18B: Theme Categorization

### Modificări

**Knowledge Extractor** (`scripts/knowledge_extractor.py` — MODIFICAT, +30 linii)
- Topic extraction: `TECH_TERM_PATTERN` regex cu ~100 termeni tehnici (databases, frameworks, languages, tools, protocols, cloud)
- `_extract_topics()` — extrage max 5 topic tags, comma-separated, lowercase
- Topics salvate în nou coloana `topics TEXT` pe decisions, learned_facts, error_resolutions
- `learned_facts.category` populat din decision classifier (câmpul exista dar era NULL)
- `_ensure_extraction_columns()` actualizat cu topics columns

### Teste (T19-T21)
- T19: Topic extraction (4 teste: databases, frameworks, generic text, max 5) — PASSED
- T20: Topics saved to DB (3 teste: decision topics, fact topics, fact category) — PASSED
- T21: Topics column exists pe toate 3 tabelele — PASSED
- **Total: 59/59 PASSED**

### Decizii
- Topics ca comma-separated text, nu tabel separat — simplu, queryable cu LIKE
- Max 5 topics per item — suficient, nu poluează
- Regex cu word boundaries — previne false matches pe substrings
- Refolosit `_classify_decision_category()` pentru `learned_facts.category`

---

## 2026-03-15 — Faza 18A: Knowledge Extraction V2

### Modificări

**Knowledge Extractor V2** (`scripts/knowledge_extractor.py` — MODIFICAT, ~+100 linii)
- Negative patterns: 12 regex compilate care rejectează meta-discuții, întrebări, ipoteze, cod inline, opțiuni alternative
- Auto-clasificare decisions: 6 categorii (architecture, tooling, data, security, process, configuration) cu regex `\b`-bounded
- Auto-clasificare facts: 4 tipuri (configuration, constraint, compatibility, behavior) cu regex `\b`-bounded
- Matched text validation: min 3 cuvinte, alpha ratio > 0.4, no pure paths/URLs
- Segment filtering V2: code block tracking (```), skip markdown refs, skip pure file listings
- Decision patterns V2: support adverbe opționale între subiect și verb ("we definitely decided")
- Backward compatible — V1 API neschimbat, items includ acum `category`/`fact_type`

### Teste (T1-T18)
- T1-T10: V1 regression — 22/22 PASSED
- T11: Negative patterns (5 teste: questions, hypotheticals, alternatives, imports, real decisions not blocked) — PASSED
- T12: Decision category classification (6 teste: architecture, tooling, data, security, process, default) — PASSED
- T13: Fact type classification (4 teste: configuration, constraint, compatibility, default) — PASSED
- T14: Matched text validation (5 teste: short, path, URL, low alpha, valid) — PASSED
- T15: Category/fact_type saved to DB (2 teste) — PASSED
- T16: Segment filtering V2 code blocks (2 teste) — PASSED
- T17: V2 patterns compiled at import (3 teste) — PASSED
- T18: Regression full pipeline + API (2 teste) — PASSED
- **Total: 51/51 PASSED**

### Decizii
- Negative patterns ca filtre pre-scoring, nu post-scoring — mai eficient
- Word boundaries `\b` pe classification patterns — previne false matches (ex: "IDE" în "decided", "port" în "support")
- Category/fact_type auto-clasificate nu înlocuiesc manual — sunt default-uri mai bune decât "technical"
- Optional adverb `(?:\w+\s+)?` în decision patterns — nu mai pierde "we definitely decided"

---

## 2026-03-15 — Faza 17Z Lite: Smart Context Ranking

### Modificări

**Context Builder V2** (`scripts/context_builder_v2.py` — MODIFICAT, +120 linii)
- Keyword relevance: `_tokenize()` + `_keyword_relevance()` — token overlap cu stop words EN+RO
- Intent keywords: `_INTENT_KEYWORDS` — debugging/feature/deploy/refactor/docs/review/explore
- `_unified_score()` — combină memory_scoring.py (0-100) + keyword relevance (0-30) + intent boost (0-15) × type weight (0.8-1.2)
- `_ranked_select()` — ranking cross-type, top-K per mode
- Overfetch 2x în compact/survival pentru ranking mai bun
- `--query` parameter pentru relevance targeting
- Fallback safe la comportament vechi dacă ranking eșuează

### Scoring Formula
```
final_score = (memory_score + keyword_relevance + intent_boost) × type_weight

memory_score:       0-100 din memory_scoring.py (base + success + reuse + agent_weight + recency)
keyword_relevance:  0-30  (fracție overlap query tokens × 30)
intent_boost:       0-15  (debugging→resolutions +15, deploy→decisions +12, etc.)
type_weight:        0.8-1.2 (decision=1.2, resolution=1.1, fact=1.0, goal=0.9, task=0.8)
```

### Top-K per mode
- survival: 8 items total cross-type
- compact: 20 items total cross-type
- full: 60 items total cross-type

### Teste (T1-T11)
- T1: Imports OK — PASSED
- T2: Keyword relevance funcționează (related vs unrelated) — PASSED
- T3: Unified scoring corect (resolution > decision > fact pentru "sqlite backup") — PASSED
- T4: Intent-aware (debugging → resolutions first) — PASSED
- T5: Cross-type ranking (survival=8 items) — PASSED
- T6-T7: Compact/full/survival moduri funcționează — PASSED
- T8: --query parameter funcționează — PASSED
- T9: mem context CLI funcționează — PASSED
- T10: Regression (daemon, knowledge extractor, backup) — PASSED
- T11: PRAGMA integrity_check — PASSED

### Decizii
- Nu am creat fișier nou — totul integrat în context_builder_v2.py existent
- memory_scoring.py refolosit via import, nu duplicat
- Stop words minimale (nu am adus nltk/spacy) — suficient pentru keyword overlap
- Type weights modeste (0.8-1.2) — nu distorsionează ranking-ul masiv

---

## 2026-03-15 — Faza 17Y: Backup & Recovery V1

### Modificări

**Backup Manager** (`scripts/backup_manager.py` — NOU, ~430 linii)
- SQLite backup API (WAL-safe, nu shutil.copy)
- Verificare integritate: existență + size > 0 + sqlite open + PRAGMA integrity_check
- SHA-256 per backup + manifest.json cu metadata
- Restore sigur: validate → backup current → restore → verify
- Retenție: max 10 backup-uri + 1/zi pentru ultimele 7 zile
- CLI: create, list, verify, restore, cleanup, status
- Output JSON pe toate comenzile

**Integrare Daemon** (`scripts/memory_daemon.py` — MODIFICAT)
- Backup automat la session_end (după knowledge extraction, înainte de clear_session)
- Safe: try/except, nu blochează session_end

**CLI** (`scripts/mem` — MODIFICAT)
- `mem backup` → delegare la backup_manager.py
- Subcomands: create, list, verify, restore, cleanup, status
- Default (fără args): status

**Branch API Fixes** (`scripts/dashboard_api.py` — MODIFICAT)
- NOU: `DELETE /api/branches/<name>` cu logging complet
- `agent_name` propagat în create, delete, switch, merge
- Protecție: nu poți șterge `main`

**Event Types** (`scripts/v2_common.py` — MODIFICAT)
- Adăugat `branch_created`, `branch_deleted` în VALID_AGENT_EVENT_TYPES

### Teste (T1-T20)
- T1-T4: Backup create, file exists, verify, integrity_check — PASSED
- T5-T6: Retenție, cleanup — PASSED
- T7-T9: Restore flow (fără force, cu force, post-verify) — PASSED
- T10: Restore invalid backup refuzat — PASSED
- T11-T13: List, status, CLI integration — PASSED
- T14-T17: Regression (daemon, knowledge extractor, context builder, dashboard) — PASSED
- T18-T20: Gemini/Codex adapters, existing tests 22/22 — PASSED

### Decizii
- SQLite backup API vs shutil.copy: backup API e WAL-safe, consistent
- Backup la session_end, nu periodic: nu necesită scheduler
- manifest.json: audit trail complet, nu doar fișiere pe disc
- pre_restore backup-uri protejate de cleanup (nu se șterg niciodată automat)

---

## 2026-03-15 — Faza 17X: Knowledge Extraction V1

### Modificări

**Knowledge Extractor** (`scripts/knowledge_extractor.py` — NOU, ~370 linii)
- Pattern-based extraction (decisions, facts, resolutions) la session_end
- 9 decision patterns (EN + RO), 9 fact patterns, 9 resolution patterns
- Pattern-uri compilate la import (inspirat din EAN CLI mode_controller.py)
- Confidence scoring cu 3 factori: pattern_weight + certainty_bonus + context_bonus
- Jaccard similarity dedup (threshold 0.55, inspirat din EAN CLI synthesis.py)
- CLI mode cu `--dry-run` și `--json`

**Schema Changes** (`migrations/016_knowledge_extraction.sql`)
- `decisions.auto_extracted`, `extraction_confidence`, `source_session_id`
- `learned_facts.auto_extracted`, `extraction_confidence`, `source_session_id`
- `error_resolutions.auto_extracted`, `extraction_confidence`, `source_session_id`

**Integrare** (`scripts/memory_daemon.py` — MODIFICAT)
- Adăugat apel `run_extraction(session_id)` în `handle_session_end()`
- Între context monitor și clear_current_session()
- Safe: try/except, nu blochează session_end la eroare

**Teste** (`tests/test_knowledge_extractor.py` — NOU, 22 teste)
- T1-T3: Extracție decisions/facts/resolutions (EN + RO)
- T4: Confidence scoring diferențiază clar vs vag
- T5-T6: High-confidence salvat, low-confidence ignorat
- T7: Jaccard dedup funcționează
- T8: Import + graceful degradation
- T9: auto_extracted queryable + extraction_confidence stored
- T10: PRAGMA integrity_check
- Rezultat: **22/22 PASSED**

### Thresholds finale (calibrate pe date reale)
- Decisions: >= 0.65
- Facts: >= 0.55
- Resolutions: >= 0.65

### Decizii
- Thresholds inițial propuse (0.85/0.80/0.82) s-au dovedit prea agresive pe propoziții singulare
- Jaccard threshold scăzut la 0.55 (de la 0.70) — trade-off: mai puține false negatives la dedup
- `extraction_method` și `source_kind` NU adăugate în V1 — `auto_extracted=1` e suficient
- `capsule_builder.py` NU modificat

---

## 2026-03-15 — DB Unification + Multi-CLI + Bug Fixes

### Modificări

**DB Unification**
- Toate componentele folosesc acum DB din project root (`ean-cc-mem-kit/global.db`)
- Schimbat default MEMORY_DIR de la `~/.claude/memory` la project root
- Fișiere modificate:
  - `scripts/memory_daemon.py` — _DAEMON_PROJECT_ROOT
  - `scripts/codex_rollout_watcher.py` — _PROJECT_ROOT, STATE_FILE, MEMORY_DIR
  - `scripts/hooks/*.sh` (toate 6) — MEMORY_DIR default
  - `scripts/hooks/gemini/gemini_hook.py` — MEMORY_DIR default
  - `~/.claude/.mcp.json` — MEMORY_PROJECT_PATH
  - `~/.kimi/mcp.json` — MEMORY_BASE_URL

**Kimi CLI Integration**
- Adăugat ca al 4-lea CLI agent via MCP native
- Creat `docs/kimi-cli-setup.md`
- Actualizat `docs/mcp.md` cu secțiuni per CLI
- Actualizat `README.md` cu Kimi CLI

**Bug Fixes**
- Fix: Adăugat `POST /api/branches` endpoint (lipsea — raportat de Kimi)
  - Validare: name required, main reserved, parent must exist, duplicate HTTP 409
  - Fișier: `scripts/dashboard_api.py`
- Clarificat: Activity log `agent_name` NULL nu e bug, e date lipsă

### Decizii
- Toate CLIs pe aceeași DB per-proiect (nu per-user)
- Faza 17X: Knowledge Extraction V1 aprobată ca direcție

---

## 2026-03-14 — Cross-Agent Learning (Faza 15C Stage 2)

### Modificări
- Adăugat `scripts/cross_agent_learning.py` — scan, promote, suggest
- Adăugat `scripts/experience_replay.py` — replay sesiune/agent/branch
- Adăugat `scripts/reasoning_trace.py` — trace reconstruction din agent_events
- Migrare `014_cross_agent_learning.sql` — coloane is_global, promoted_from_agent
- Actualizat `scripts/v2_common.py` — VALID_AGENT_EVENT_TYPES

---

## 2026-03-13 — Adapters + Specs

### Modificări
- Creat `docs/spec-adapters.md` — specificații adapter pattern
- Creat `docs/adapters.md` — ghid de utilizare
- Creat `docs/quickstart.md` — quick start guide
- Adăugat `scripts/adapters/gemini_cli_adapter.py`
- Adăugat `scripts/adapters/codex_cli_adapter.py`

---

## 2026-03-12 — Agent Events + Branches + Context V2

### Modificări
- Implementat agent event stream (18 tipuri)
- Branch manager complet (create/switch/compare/merge)
- Context builder V2 cu intent-aware filtering
- Migrări 012-013
- Creat specificații: spec-memory-schema, spec-events, spec-branches

---

## 2026-03-11 — Initial Release v1.1

### Modificări
- Core engine complet: daemon, context builder, CLI
- Checkpoints, error intelligence, observability
- Web dashboard (HTML/JS/CSS)
- Toate migrările 006-011
- Release check script
- Documentație completă în docs/
