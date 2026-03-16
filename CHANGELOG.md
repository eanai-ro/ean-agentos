# Changelog

Toate schimbările notabile ale acestui proiect vor fi documentate în acest fișier.

Formatul se bazează pe [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
și acest proiect aderă la [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0-rc1] - 2026-03-12

### Added — V2 Memory System
- Structured memory entities: decisions, facts, goals, tasks, error resolutions
- Context builder with 4 modes (compact, full, survival, delta) and intent-aware filtering
- Memory intelligence layer: error patterns, staleness detection, conflict analysis
- Checkpoints: save/restore memory snapshots with timeline events
- CLI dashboard and web dashboard (dark theme, 13 tabs)
- Universal REST API (`/api/v1/*`) for any agent
- Dashboard API (`/api/*`) for web UI operations
- Memory branches: git-like branching (create, switch, compare, merge, replay)
- Agent event stream: 18 event types, 4 phases, event UI with filtering and replay
- MCP bridge (Model Context Protocol) for Claude Desktop / Cursor
- Adapters: Gemini CLI, Codex CLI
- Generic Python client (`UniversalMemoryClient`) — zero external dependencies
- Specification documents: memory schema, events, adapters, branches, compatibility
- Payload validator (`scripts/spec_validator.py`)
- Project profiles and model usage tracking
- Agent activity logging with model attribution

### Added — Release Candidate Polish
- `requirements.txt` with declared dependencies
- Run scripts: `run_server.sh`, `run_mcp.sh`, `run_tests.sh`
- Demo seed script (`demo_seed.py`) and walkthrough (`docs/demo.md`)
- Release check script (`release_check.py`)
- `ROADMAP.md` and `RELEASE_NOTES_RC1.md`

### Infrastructure
- SQLite with WAL mode, FTS5 full-text search
- Flask Blueprint pattern for modular API
- 14 test phases, 200+ individual tests
- 7 SQL migrations (007-013)

---

## [1.0.0] - 2026-02-07

### Added - P1 Implementation
- CLI unificat `mem` cu 6 comenzi (stats, search, err, trace, reconcile, reload)
- Telegram alerts cu sistem de debounce (5 minute între alerte)
- PreCompact hook pentru salvare stats înainte de auto-compact
- Script `p2_safe_optimize.sh` pentru optimizare DB safe
- Script `p2a2_profile_mem.sh` pentru profilare performanță
- Git repository local cu versioning complet

### Fixed - P1 Bugfixes
- `notify.py`: Detectare corectă folder proiect folosind PWD env var
- `search_memory.py`: Schema DB corectată (error_stack → stack_trace, pattern_key → pattern_name)

### Changed - P2-A Database Optimization
- Aplicat PRAGMA optimize pentru statistici query planner
- Executat ANALYZE pentru refresh statistici tabele
- Verificare și validare 47 indexuri active
- Reducere freelist: 3 → 2 pagini

### Changed - P2-A.2 FTS5 Migration
- Migrare `search_messages()` de la LIKE la FTS5
- Migrare `search_bash_commands()` de la LIKE la FTS5
- Speedup 7-10x pentru query-uri complexe
- Toate căutările acum sub 0.18s (majoritatea sub 0.10s)

### Performance
- mem stats: 85ms (înainte: 100ms+)
- mem search: 90-110ms (înainte: 730-820ms pentru query-uri complexe)
- mem err: 37ms (foarte rapid)
- DB integrity verificată: ok

### Documentation
- README.md comprehensiv cu features, usage, configuration
- DEV_LOG.md cu istoric complet dezvoltare
- DOCUMENTATION.md cu arhitectură sistem
- PROJECT_STATE.md cu status curent
- docs/P1_IMPLEMENTATION.md
- docs/P2A_OPTIMIZATION.md
- docs/P2A2_FTS5_OPTIMIZATION.md

### Infrastructure
- Git repository inițializat cu .gitignore
- 3 commits cu istoric complet
- Tag v1.0.0 pentru release
- Multiple backup-uri create și verificate

## [Unreleased]

See [ROADMAP.md](ROADMAP.md) for planned features.
