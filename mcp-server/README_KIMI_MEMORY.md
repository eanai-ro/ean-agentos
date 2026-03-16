# Kimi Memory - Adaptare Memorie Permanentă pentru Kimi Code CLI

Acest pachet adaptează sistemul tău de memorie permanentă (creat pentru Claude Code) pentru **Kimi Code CLI**.

## 🎯 Arhitectura

```
┌─────────────────┐         ┌─────────────────────────┐
│  Kimi Code CLI  │◄────────│  MCP Memory Server      │
│                 │         │  • memory_search()      │
│  • context auto │         │  • memory_get_context() │
│  • MCP tools    │         │  • memory_search_errors │
│                 │         │  • memory_get_stats()   │
└─────────────────┘         └─────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────┐
│  ~/.kimi/memory/global.db                           │
│  (reutilizezi DB existent sau copie din Claude)    │
└─────────────────────────────────────────────────────┘
```

## 📦 Fișiere

| Fișier | Scop | Linii |
|--------|------|-------|
| `kimi_memory_server.py` | MCP Server - tool-uri pentru Kimi | ~400 |
| `kimi_context_loader.py` | Generează context la startup | ~250 |
| `kimim` | CLI wrapper pentru utilizare ușoară | ~180 |
| `setup_kimi_memory.sh` | Script setup automat | ~80 |

## 🚀 Instalare Rapidă (3 pași)

### Pasul 1: Setup
```bash
cd ./mcp-server
bash setup_kimi_memory.sh
```

Acest script:
- Creează `~/.kimi/memory/`
- Copiază DB din `./`
- Configurează MCP server

### Pasul 2: Configurează MCP în Kimi

Editează `~/.config/kimi/kimi-cli.toml` (sau creează-l):

```toml
[mcp]
enabled = true

[[mcp.servers]]
name = "memory"
command = "python3"
args = ["$HOME/.kimi/memory/mcp-server/kimi_memory_server.py"]
```

### Pasul 3: Testează

```bash
# Test standalone
python3 ~/.kimi/memory/mcp-server/kimi_memory_server.py stats

# Sau folosește wrapper
./mcp-server/kimim --stats
```

## 💡 Utilizare

### Opțiunea A: MCP Tools (Recomandat)

După ce configurezi MCP, în conversațiile cu mine poți spune:

```
"Caută în memorie cum am configurat Docker"
"Ce erori am avut recent cu Python?"
"Încarcă context pentru proiectul curent"
"Statistici memorie"
```

Eu voi apela automat tool-urile MCP:
- `memory_search` - Caută în mesaje
- `memory_search_errors` - Caută erori și soluții
- `memory_get_context` - Încarcă context recent
- `memory_get_stats` - Statistici

### Opțiunea B: Context Manual

```bash
# Generează context pentru proiectul curent
kimim --context-only

# Copiază în clipboard
kimim --context-only --copy

# Context pentru proiect specific
kimim --project ~/proiecte/web --context-only

# Apoi lipește în conversația cu mine
```

### Opțiunea C: CLI Direct

```bash
# Caută în memorie
kimim --search "autentificare"

# Vezi statistici
kimim --stats

# Pornește Kimi cu context auto
kimim
```

## 🛠️ Comenzi Disponibile

### `kimim` (Wrapper)

```bash
kimim                           # Context auto pentru proiectul curent
kimim --no-context              # Fără context auto
kimim --project /path/to/proj   # Context pentru proiect specific
kimim --stats                   # Statistici rapide
kimim --search "query"          # Caută în memorie
kimim --context-only            # Afișează doar context
kimim --context-only --copy     # Copiază în clipboard
kimim --help                    # Help
```

### MCP Tools

Când MCP e activ, eu pot folosi:

**memory_search**
```json
{
  "query": "docker compose",
  "limit": 10
}
```

**memory_search_errors**
```json
{
  "error_query": "ImportError",
  "limit": 5
}
```

**memory_get_context**
```json
{
  "project_path": "/home/user/proiecte/web",
  "hours": 24
}
```

**memory_get_stats**
```json
{}
```

## 🔧 Troubleshooting

### "DB not found"
```bash
# Copiază manual din Claude
cp ./global.db ~/.kimi/memory/
```

### "MCP SDK not available"
- MCP SDK vine built-in cu Kimi Code CLI
- Dacă rulezi standalone, folosește modul CLI:
```bash
python3 kimi_memory_server.py stats
```

### "Cannot connect to MCP server"
Verifică configurația în `~/.config/kimi/kimi-cli.toml`:
```bash
# Test manual
python3 ~/.kimi/memory/mcp-server/kimi_memory_server.py
# Ar trebui să stea deschis (nu exit)
```

## 🔄 Sincronizare cu Claude

Dacă vrei să folosești **aceeași bază de date** pentru ambele:

```bash
# Creează symlink în loc de copie
ln -s ./global.db ~/.kimi/memory/global.db
```

**Atenție:** Dacă rulează ambele simultan, pot apărea conflicte (WAL mode ajută, dar nu e perfect).

## 📊 Comparație: Claude vs Kimi

| Feature | Claude Code | Kimi Code CLI |
|---------|-------------|---------------|
| **Persistență** | Hooks automate | MCP + manual |
| **Context load** | Automat (SessionStart) | Manual sau MCP |
| **Căutare** | `search_memory.py` | MCP tool sau CLI |
| **Securitate** | Scrubbing + Guard | Reutilizezi aceeași logică |
| **Observability** | Dashboard | Similar |

## 🎯 Recomandări

1. **Pentru utilizare zilnică:** Folosește MCP tools - sunt cele mai fluide
2. **Pentru proiecte noi:** Rulează `kimim --context-only --copy` și lipește la început
3. **Pentru debugging:** `kimim --stats` pentru health check rapid

## 📝 TODO (Viitor)

- [ ] Auto-save în Kimi (dacă API-ul permite)
- [ ] Vector search cu embeddings
- [ ] Web UI pentru ambele platforme
- [ ] Sync bidirecțional Claude ↔ Kimi

---

**Creat:** 2026-02-08  
**Versiune:** 1.0.0  
**Autor:** Claude + Kimi  
