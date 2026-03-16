# WORKFLOW — Universal Agent Memory

**Ultima actualizare:** 2026-03-15

---

## Flux de Dezvoltare

```
1. RECITEȘTE
   ├── PROJECT_STATE.md
   ├── DEV_LOG.md
   ├── ERRORS_SOLUTIONS.md
   └── LICENTE_COMPONENTE.md

2. ANALIZĂ
   ├── Înțelege cerința
   ├── Verifică impactul asupra componentelor existente
   └── Verifică dacă eroarea / feature-ul a fost deja abordat

3. PLAN
   ├── Propune abordare
   ├── Identifică fișierele afectate
   └── Estimează riscuri

4. CONFIRMARE
   └── Aprobarea utilizatorului

5. IMPLEMENTARE
   ├── Cod + teste
   ├── Migrare DB (dacă e cazul)
   └── Actualizare documentație

6. TESTARE
   ├── ./scripts/run_tests.sh
   ├── python3 scripts/release_check.py
   └── Verificare manuală

7. DOCUMENTARE
   ├── DEV_LOG.md
   ├── PROJECT_STATE.md
   └── ERRORS_SOLUTIONS.md (dacă e cazul)

8. SALVEAZĂ
   └── Commit + actualizare toate fișierele obligatorii
```

---

## Flux Auto-Capture (Runtime)

### Claude Code
```
User prompt → hook UserPromptSubmit → memory_daemon.py user_prompt
                                           ↓
                                     Salvare în messages
                                           ↓
Tool use → hook PreToolUse/PostToolUse → memory_daemon.py pre_tool/post_tool
                                           ↓
                                     Salvare în messages
                                           ↓
Session end → hook SessionStop → memory_daemon.py session_end
                                           ↓
                                     Close session + stats
```

### Gemini CLI
```
User prompt → gemini_hook.py user_prompt → memory_daemon.py user_prompt
                                                  ↓
Agent response → gemini_hook.py assistant_response → memory_daemon.py
                                                  ↓
Tool use → gemini_hook.py pre_tool/post_tool → memory_daemon.py
```

### Codex CLI
```
JSONL session file → codex_rollout_watcher.py (poll 5s)
                          ↓
                     parse_jsonl_line()
                          ↓
                     _call_memory_daemon(handler, payload)
                          ↓
                     memory_daemon.py
```

### Kimi CLI
```
Kimi CLI → MCP stdio → mcp_server/server.py
                              ↓
                         HTTP API → universal_api.py
                              ↓
                         SQLite DB
```

---

## Flux Context Retrieval

```
Agent needs context
      ↓
GET /api/v1/context?mode=compact&project=/path
      ↓
context_builder_v2.py
      ├── Detectare intent (debugging/feature/refactor/etc)
      ├── Selectare entities relevante
      ├── Formatare output
      └── Truncare la budget caractere
      ↓
Context injectat în conversația agentului
```

---

## Flux Branching

```
1. Create branch
   mem branch create feature-x
        ↓
   INSERT memory_branches (name, parent, project)

2. Switch branch
   mem branch switch feature-x
        ↓
   UPDATE memory_branches SET is_active

3. Work on branch
   Toate entitățile noi primesc branch_name = feature-x

4. Compare
   mem branch compare main feature-x
        ↓
   SELECT diff entre branches

5. Merge
   mem branch merge feature-x --into main
        ↓
   Conflict detection → resolution → copy entities
```

---

## Flux Multi-Agent

```
                    ┌─── Claude Code (hooks)
                    │
Project DB ←────────┼─── Gemini CLI (hooks)
(global.db)         │
                    ├─── Codex CLI (JSONL watcher)
                    │
                    └─── Kimi CLI (MCP → API)

Toți agenții:
1. Scriu în aceeași DB
2. Pot vedea ce au făcut ceilalți
3. Atribuire prin cli_name, agent_name, model_name, provider
4. Cross-agent learning: items promovate de un agent → vizibile celorlalți
```
