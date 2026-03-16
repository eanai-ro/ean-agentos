# 🧠 EAN AgentOS

### Memorie permanentă pentru agenți AI de programare

**Nu mai rezolva același bug de două ori.**

---

## Ce face EAN AgentOS?

Agentul tău AI uită totul între sesiuni. EAN AgentOS îi dă memorie permanentă.

```
Sesiunea 1:
  > Eroare CORS în Flask
  > Rezolvat: pip install flask-cors + CORS(app)

Sesiunea 2 (3 luni mai târziu):
  > Aceeași eroare CORS
  > AgentOS: "Ai rezolvat asta pe 12 martie. Soluția: flask-cors middleware"
```

**Funcționează cu Claude Code, Gemini CLI, Codex CLI și Kimi CLI.** Toți agenții împărtășesc aceeași memorie.

---

## Funcționalități

| Feature | Descriere |
|---------|-----------|
| 🔁 **Memorie Permanentă** | Decizii, fapte, obiective, task-uri — persistate între sesiuni |
| 💡 **`mem suggest`** | Caută soluții anterioare: *"Nu mai rezolva același bug de două ori"* |
| 🧬 **Knowledge Extraction** | Extragere automată de pattern-uri, scoruri, deduplicare |
| 🔍 **Căutare Cognitivă** | Caută în rezoluții, decizii, fapte, mesaje |
| 🌳 **Memory Branches** | Ramuri de memorie per git branch |
| 📊 **Experience Graph** | Graf problem → soluție → rezultat |
| 🔄 **Cross-Agent Learning** | Agenții învață din experiența celorlalți |
| 💾 **Backup & Recovery** | Backup automat, restaurare, verificare integritate |
| 🖥️ **Web Dashboard** | Vizualizare decizii, fapte, timeline, health |
| 🔌 **MCP Server** | Integrare nativă cu Claude Code + alte CLI-uri |

---

## Instalare rapidă

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
./install.sh
```

Installer-ul detectează automat CLI-urile instalate și te lasă să alegi pe care să le integrezi.

### Sau manual:

```bash
pip install flask flask-cors
python3 scripts/init_db.py
python3 scripts/ean_memory.py install claude   # sau gemini, codex
```

---

## Utilizare

### Nu mai rezolva același bug de două ori

```bash
mem suggest "CORS error"
```

```
💡 SOLUTIONS FOR: CORS error
══════════════════════════════════════════════════════════════

  1. [92pts] ✅ error_resolutions#5
     Problem:  CORS error: blocked by CORS policy
     Solution: Add flask-cors middleware: CORS(app)
     Match: 100% | Confidence: 92% | Agent: claude-code
```

### Comenzi principale

```bash
mem suggest "eroare"          # Caută soluții anterioare
mem search "keyword"          # Caută în toată memoria
mem decisions                 # Vezi decizii active
mem status                    # Status memorie
mem graph stats               # Statistici experience graph
```

### Web Dashboard

```bash
python3 scripts/web_server.py
# Deschide: http://localhost:19876
```

### MCP Server (pentru Claude Code)

Se configurează automat la instalare. Agentul tău AI primește context din memoria permanentă la fiecare sesiune.

---

## CLI-uri Suportate

| CLI | Integrare | Comandă instalare |
|-----|-----------|-------------------|
| **Claude Code** | Hooks + MCP Server | `python3 scripts/ean_memory.py install claude` |
| **Gemini CLI** | Hooks | `python3 scripts/ean_memory.py install gemini` |
| **Codex CLI** | Hooks | `python3 scripts/ean_memory.py install codex` |
| **Kimi CLI** | MCP Server | Manual config |

Toate CLI-urile citesc și scriu în aceeași bază de date. Ceea ce învață un agent e disponibil pentru toți.

---

## Cum funcționează

```
  Claude Code    Gemini CLI    Codex CLI    Kimi CLI
       │              │             │            │
       │     captură automată (hooks)            │
       └──────────────┬─────────────┬────────────┘
                      │             │
                      ▼             ▼
               ┌──────────────────────────┐
               │       global.db          │
               │                          │
               │  decisions               │
               │  learned_facts           │
               │  error_resolutions       │
               │  experience_graph        │
               │  solution_index          │
               │  ...49 tabele            │
               └──────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      REST API    MCP Server    CLI (mem)
       Dashboard   (Claude)     (terminal)
```

1. **Captura**: Hooks-urile capturează automat decizii, erori, soluții din sesiunile AI
2. **Structurare**: Knowledge Extractor clasifică, scorează și deduplică
3. **Căutare**: La fiecare sesiune nouă, agentul primește context relevant
4. **Învățare**: Solution Index + Experience Graph = memoria devine mai inteligentă

---

## Structura proiectului

```
ean-agentos/
├── scripts/
│   ├── mem                      # CLI principal
│   ├── v2_common.py             # Core DB + utilități
│   ├── init_db.py               # Inițializare DB
│   ├── solution_index.py        # 💡 mem suggest
│   ├── knowledge_extractor.py   # Extragere automată
│   ├── context_builder_v2.py    # Context pentru LLM
│   ├── experience_graph.py      # Graf experiențe
│   ├── search_memory.py         # Căutare unificată
│   ├── backup_manager.py        # Backup & restore
│   ├── web_server.py            # Dashboard web
│   ├── ean_memory.py            # Installer
│   └── ...
├── web/                         # Dashboard HTML/JS/CSS
├── mcp_server/                  # MCP pentru Claude Code
├── mcp-server/                  # MCP pentru Kimi CLI
├── migrations/                  # Schema DB
├── install.sh                   # Installer interactiv
├── test_full.sh                 # Test suite (57 teste)
└── Dockerfile                   # Container test
```

---

## Teste

```bash
./test_full.sh
```

57 teste acoperă: structură, database, importuri, license gate, mem suggest, experience graph, context builder, search, web server, MCP, integritate DB, backup.

---

## EAN AgentOS Pro 🔒

Versiunea Pro adaugă **orchestrare multi-agent** — coordonarea mai multor CLI-uri AI pe același proiect:

| Feature Pro | Descriere |
|------------|-----------|
| 🤖 **Multi-Agent Orchestration** | Proiecte cu task-uri, lease-based ownership |
| 🗣️ **AI Deliberation** | Sesiuni structurate multi-round cu sinteză |
| 🚀 **CLI Launcher** | Lansare programatică Claude/Gemini/Codex/Kimi |
| 🔄 **Auto-Pipeline** | Task chaining, auto-review, conflict resolution |
| 🧠 **Intelligence Layer** | Capability scoring, weighted voting, skill learning |
| 📼 **Replay System** | Timeline complete proiecte + deliberări |
| 📋 **Peer Review** | Verdicte formale, auto-fix |

**Detalii**: [ean@eanai.ro](mailto:ean@eanai.ro)

---

## License

MIT — vezi [LICENSE](LICENSE)

---

## Despre

Dezvoltat de **EAN** (Encean Alexandru Nicolae) 🇷🇴

*Memorie permanentă pentru agenți AI. Nu mai uita. Nu mai repeta. Învață.*
