# LICENTE COMPONENTE — EAN AgentOS

Ultima actualizare: 2026-03-11

## Politica de licențiere

Conform CLAUDE.md secțiunile 3 și 11:
- **Permise:** MIT, Apache 2.0, BSD, MPL 2.0, ISC, CC0
- **Interzise:** GPL, LGPL, AGPL, SSPL, EUPL, CPAL, orice licență virală

---

## Dependențe directe

| Componentă | Versiune | Licență | Status | Utilizare |
|------------|----------|---------|--------|-----------|
| Flask | 3.0.0 | BSD-3-Clause | APROBAT | Web server (web_server.py, dashboard_api.py) |
| flask-cors | 6.0.2 | MIT | APROBAT | CORS support (web_server.py) |
| sentence-transformers | 5.1.2 | Apache 2.0 | APROBAT | Embeddings vector search (vector_search.py, OPȚIONAL) |
| chromadb | 1.4.1 | Apache 2.0 | APROBAT | Vector database (vector_search.py, OPȚIONAL) |
| mcp | 1.4.0 | MIT | APROBAT | MCP server (mcp-server/, OPȚIONAL) |
| pyperclip | - | BSD-3-Clause | APROBAT | Clipboard (kimi_context_loader.py, OPȚIONAL, neinstalat) |
| SQLite3 | builtin | Public Domain | APROBAT | Baza de date (stdlib Python) |

## Dependențe indirecte (dependency tree)

### Flask dependency tree
| Componentă | Versiune | Licență | Status |
|------------|----------|---------|--------|
| Werkzeug | 3.1.3 | BSD-3-Clause | APROBAT |
| Jinja2 | 3.1.4 | BSD-3-Clause | APROBAT |
| MarkupSafe | 2.1.5 | BSD-3-Clause | APROBAT |
| itsdangerous | 2.2.0 | BSD-3-Clause | APROBAT |
| click | 8.1.8 | BSD-3-Clause | APROBAT |

### sentence-transformers dependency tree
| Componentă | Versiune | Licență | Status |
|------------|----------|---------|--------|
| torch (PyTorch) | 2.5.1 | BSD-3-Clause | APROBAT |
| transformers (HuggingFace) | 4.52.0 | Apache 2.0 | APROBAT |
| numpy | 1.26.4 | BSD-3-Clause | APROBAT |

## Frontend

| Componentă | Licență | Status |
|------------|---------|--------|
| Vanilla JavaScript | N/A | APROBAT — fără dependențe externe |
| HTML5 / CSS3 | N/A | APROBAT — standarde web |

## Componente interzise detectate

**NICIUNA** — toate dependențele au licențe permisive.

## Rezumat

| Tip licență | Count | Componente |
|-------------|-------|------------|
| BSD-3-Clause | 9 | Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, click, torch, numpy, pyperclip |
| MIT | 2 | flask-cors, mcp |
| Apache 2.0 | 3 | sentence-transformers, chromadb, transformers |
| Public Domain | 1 | SQLite3 |
| **Total** | **15** | **Toate APROBATE** |

## Note

1. sentence-transformers, chromadb, mcp și pyperclip sunt **OPȚIONALE** — proiectul funcționează complet fără ele
2. Dependențele core (obligatorii) sunt doar: Flask + flask-cors
3. Frontend-ul este 100% vanilla (zero dependențe externe)
4. Nicio componentă GPL/LGPL/AGPL/SSPL detectată în dependency tree
