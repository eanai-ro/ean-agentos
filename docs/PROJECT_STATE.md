# PROJECT_STATE — Universal Agent Memory (ean-agentos)

**Versiune curentă:** v1.3
**Ultima actualizare:** 2026-03-15
**Autor:** Sandu (EAN - Encean Alexandru Nicolae)
**Expunere:** INTERNAL_ONLY

---

## Stare Generală

| Aspect | Status |
|--------|--------|
| Core Engine | ✅ Stabil |
| REST API | ✅ Funcțional |
| Web Dashboard | ✅ Funcțional |
| MCP Server | ✅ Funcțional |
| CLI (`mem`) | ✅ Funcțional |
| Orchestration | ✅ Funcțional |
| Teste | ✅ Faze 3-18D |
| Documentație | ✅ Completă |

---

## Module Implementate

### Core (v1.0 - v1.1)
- [x] SQLite DB cu WAL mode
- [x] Structured entities: decisions, facts, goals, tasks, resolutions
- [x] FTS5 full-text search
- [x] Context builder (compact/full/survival/delta)
- [x] Memory daemon (hook-based capture)
- [x] CLI `mem` cu toate operațiile CRUD
- [x] Web server + Dashboard API
- [x] Universal API (REST)

### Branching (v1.1)
- [x] Create/switch/compare/merge branches
- [x] Branch-aware entities
- [x] Conflict detection

### Observability (v1.2)
- [x] Agent activity log
- [x] Timeline view
- [x] Health check
- [x] Model usage logging

### Error Intelligence (v1.2)
- [x] Error pattern detection
- [x] Error resolution tracking
- [x] Error learning system

### Cognitive Layer (v1.3)
- [x] Agent event stream (18 event types)
- [x] Cognitive search
- [x] Fact promoter
- [x] Experience replay
- [x] Reasoning traces
- [x] Cross-agent learning

### Multi-Agent Support (v1.3)
- [x] Claude Code (hooks + MCP)
- [x] Gemini CLI (Python hooks)
- [x] Codex CLI (JSONL rollout watcher)
- [x] Kimi CLI (MCP native)
- [x] Python client library
- [x] Toate CLIs pe aceeași DB (project-local)

---

## Module Planificate

### Faza 17X — Knowledge Extraction V1 (IMPLEMENTAT 2026-03-15)
- [x] Pattern-based extraction la session_end
- [x] Confidence scoring (3 factori)
- [x] Jaccard dedup (threshold 0.55)
- [x] Auto-save decisions/facts/resolutions
- [x] 22/22 teste PASSED

### Faza 17Y — Backup & Recovery V1 (IMPLEMENTAT 2026-03-15)
- [x] Backup automat la session_end (SQLite backup API, WAL-safe)
- [x] Verificare integritate (PRAGMA integrity_check + SHA-256)
- [x] Restore sigur (pre-restore backup + post-restore verify)
- [x] Retenție: max 10 + 1/zi x 7 zile
- [x] manifest.json cu metadata audit
- [x] CLI: mem backup create|list|verify|restore|cleanup|status
- [x] DELETE /api/branches endpoint + agent_name în toate branch ops
- [x] T1-T20 PASSED

### Faza 17Z Lite — Smart Context Ranking (IMPLEMENTAT 2026-03-15)
- [x] Integrare memory_scoring.py în context_builder_v2.py
- [x] Keyword/topic relevance (token overlap, stop words, intent keywords)
- [x] Unified cross-type ranking (decisions+facts+resolutions în spațiu comun)
- [x] Overfetch 2x + top-K per mode (survival=8, compact=20, full=60)
- [x] --query parameter pentru relevance targeting
- [x] Fallback la comportament vechi dacă ranking eșuează
- [x] T1-T11 PASSED

### Faza 18A — Knowledge Extraction V2 (IMPLEMENTAT 2026-03-15)
- [x] Negative patterns (12 regex) — rejectează meta-discuții, întrebări, ipoteze, cod
- [x] Auto-clasificare decisions (6 categorii: architecture, tooling, data, security, process, configuration)
- [x] Auto-clasificare facts (4 tipuri: configuration, constraint, compatibility, behavior)
- [x] Matched text validation (min 3 cuvinte, alpha ratio, no paths/URLs)
- [x] Segment filtering V2 (code block tracking, markdown refs)
- [x] Decision patterns V2 (adverbe opționale)
- [x] T1-T18 (51 teste) PASSED

### Faza 18B — Theme Categorization (IMPLEMENTAT 2026-03-15)
- [x] Topic extraction regex (~100 termeni tehnici: DB, frameworks, languages, tools, protocols, cloud)
- [x] `topics` column adăugat pe decisions, learned_facts, error_resolutions
- [x] Max 5 topic tags per item, comma-separated, lowercase
- [x] `learned_facts.category` populat automat
- [x] T19-T21 (8 teste noi) PASSED, total 59/59

### Faza 18C — Review UI (IMPLEMENTAT 2026-03-15)
- [x] API: GET /api/review/pending, POST /api/review/approve, POST /api/review/reject, GET /api/review/stats
- [x] CLI: mem review pending|approve|reject|stats
- [x] Convention auto_extracted: 0=manual, 1=pending, 2=approved, -1=rejected

### Faza 18D — MCP Orchestration V1 (IMPLEMENTAT 2026-03-15)
- [x] Peer-to-peer orchestrare prin DB (fără proces central)
- [x] Proiecte orchestrate cu task-uri și lease-based ownership
- [x] Task routing cu scoring (strength + workload + success rate)
- [x] Deliberare multi-agent: quick (2 runde), deep (4), expert (6)
- [x] Consensus detection (Jaccard ≥0.25), theme clustering (8 teme)
- [x] Inter-agent messaging (directed + broadcast, read tracking)
- [x] Agent presence tracking (heartbeat, stale detection)
- [x] 12 REST API endpoints (/api/v1/orch/*)
- [x] 12 CLI commands (mem orch)
- [x] 5 MCP tools (orch_project_create, orch_tasks, orch_deliberation, orch_messaging, orch_agent_heartbeat)
- [x] T1-T25 PASSED

### Viitor
- [ ] CLI launcher V2 (lansare programatică CLI-uri)
- [ ] Semantic search (embeddings)
- [ ] Web server persistence (systemd)
- [ ] Orchestration UI web

---

## Infrastructură

| Componentă | Detalii |
|------------|---------|
| Limbaj | Python 3.10+ |
| DB | SQLite 3.35+ cu FTS5 + WAL |
| API Framework | Flask |
| MCP Library | FastMCP |
| Port API | 19876 |
| DB Path | `<project_root>/global.db` |
| Dependențe | Minimal — doar Python stdlib + Flask + FastMCP |

---

## Dependențe

| Pachet | Versiune | Licență | Status |
|--------|----------|---------|--------|
| Flask | 3.x | BSD-3 | ✅ Permisă |
| FastMCP | 3.1.x | MIT | ✅ Permisă |
| requests | 2.x | Apache-2.0 | ✅ Permisă |

---

## Probleme Cunoscute

1. **Web server persistence** — Serverul trebuie pornit manual; nu există systemd service
2. **web_server.py default DB** — Încă are default `./global.db`; necesită env var
3. **Schema consistency** — Unele tabele nu au `model_used` (goals, learned_facts)
4. **Soft delete** — Nu există; ștergerea este permanentă

---

## Decizii Active

| ID | Decizie | Data | Status |
|----|---------|------|--------|
| D1 | DB unificată per-proiect (nu per-user) | 2026-03-15 | ✅ Activ |
| D2 | Toate CLIs scriu în aceeași DB | 2026-03-15 | ✅ Activ |
| D3 | Knowledge extraction la session_end only | 2026-03-15 | 🟡 Planificat |
| D4 | Pattern-based (no LLM) pentru V1 | 2026-03-15 | 🟡 Planificat |
| D5 | 1 fișier knowledge_extractor.py | 2026-03-15 | 🟡 Planificat |
