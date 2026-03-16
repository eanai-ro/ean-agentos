# SECURITATE — Universal Agent Memory

**Ultima actualizare:** 2026-03-15
**Nivel expunere:** INTERNAL_ONLY

---

## 1. Profil de Securitate

Universal Agent Memory este un **tool local/LAN** pentru dezvoltatori. Nu este expus public.

| Aspect | Status |
|--------|--------|
| Autentificare API | ❌ Nu există (LAN-only) |
| HTTPS | ❌ Nu (HTTP intern) |
| Rate limiting | ❌ Nu |
| Input validation | ✅ Parțial (Flask) |
| SQL injection | ✅ Protejat (parametrized queries) |
| XSS | N/A (API-only, minimal HTML) |
| CSRF | N/A (fără autentificare) |

---

## 2. Suprafața de Atac

### API Server (port 19876)
- Ascultă pe `0.0.0.0` → accesibil din LAN
- Fără autentificare → oricine din rețea poate citi/scrie
- **Mitigare:** Firewall (UFW) restricționează accesul la IP-uri de încredere

### SQLite DB
- Fișier local, permisiuni OS standard
- WAL mode permite citiri concurente
- **Risc:** Corupție la scrieri concurente intense (mitigat de WAL)

### Hook Scripts
- Rulează ca subprocese cu privilegiile utilizatorului
- Input de la CLI-uri → potențial command injection
- **Mitigare:** Input transmis via JSON stdin, nu ca argumente shell

---

## 3. Date Sensibile

| Tip | Prezent | Mitigare |
|-----|---------|----------|
| API keys | NU — nu se stochează | N/A |
| Parole | NU | N/A |
| Cod sursă | DA — tool responses pot conține cod | Acces doar LAN |
| Conversații AI | DA — mesaje stocate integral | Acces doar LAN |
| Erori cu stack traces | DA — error_resolutions | Acces doar LAN |

---

## 4. Recomandări

### Imediate (pentru producție internă)
1. **Firewall** — Restricționează port 19876 la IP-urile echipei
2. **Backup** — Backup zilnic al `global.db`
3. **Permisiuni fișier** — `chmod 600 global.db`

### Viitoare (dacă se expune extern)
1. Adăugare autentificare (API key sau JWT)
2. HTTPS cu certificat valid
3. Rate limiting
4. Audit logging pentru toate operațiile write
5. Sanitizare input mai strictă

---

## 5. Dependențe

Toate dependențele folosesc licențe permisive (MIT, BSD, Apache).
Nu există dependențe cu vulnerabilități cunoscute la data documentului.

Vezi `docs/LICENTE_COMPONENTE.md` pentru lista completă.
