# ERRORS_SOLUTIONS — Universal Agent Memory (ean-cc-mem-kit)

Jurnal de erori întâlnite și soluțiile lor.

---

## E001 — Web server folosea DB greșită

- **Data:** 2026-03-15
- **Descriere:** Web server-ul (`web_server.py`) avea default `~/.claude/memory/global.db` (955MB legacy) în loc de project-local DB
- **Cauza:** Hardcoded default la linia 40: `MEMORY_DIR = Path.home() / ".claude" / "memory"`
- **Soluție:** Restart server cu env var: `MEMORY_DB_PATH=/mnt/lucru/proiecte/claude/ean-cc-mem-kit/global.db`
- **Risc:** Recidivă la fiecare restart fără env var
- **Status:** 🟡 Workaround (trebuie systemd service sau fix permanent)
- **Rezolvat de:** Claude Code (AI)

---

## E002 — Branch creation endpoint lipsă

- **Data:** 2026-03-15
- **Descriere:** `POST /api/branches` cu JSON body returna eroare "Expecting value"
- **Cauza:** Endpoint-ul de creare branch nu exista deloc în `dashboard_api.py`. Doar GET list, GET compare, POST switch, POST merge erau implementate.
- **Log:** Raportat de Kimi CLI la testare
- **Soluție:** Adăugat endpoint complet cu validare (name required, main reserved, parent check, duplicate 409)
- **Fișier:** `scripts/dashboard_api.py`
- **Status:** ✅ Rezolvat
- **Rezolvat de:** Claude Code (AI)

---

## E003 — Activity log TypeError pe agent_name NULL

- **Data:** 2026-03-15
- **Descriere:** `TypeError: unsupported format string passed to NoneType.__format__` la formatare activity log
- **Cauza:** `agent_name` este NULL în DB pentru unele entries — nu e bug, e date lipsă
- **Soluție:** Nu necesită fix — API-ul returnează corect, formatarea CLI (`mem`) ar putea folosi fallback
- **Status:** ✅ Clarificat (nu e bug)
- **Rezolvat de:** Claude Code (AI)

---

## E004 — Dual/Triple database confusion

- **Data:** 2026-03-15
- **Descriere:** Trei baze de date separate existau simultan
- **Cauza:** Componente diferite cu default-uri diferite pentru MEMORY_DIR
- **Log:**
  ```
  ~/.claude/memory/global.db       # 955MB - legacy (vechi)
  ~/.ean-memory/global.db          # 22MB  - intermediar
  ean-cc-mem-kit/global.db         # 896KB - project-local
  ```
- **Soluție:** Unificat toate componentele să folosească project-local DB prin schimbarea default-urilor în: memory_daemon.py, toate hooks, codex_rollout_watcher.py, gemini_hook.py, MCP configs
- **Status:** ✅ Rezolvat
- **Rezolvat de:** Claude Code (AI)
