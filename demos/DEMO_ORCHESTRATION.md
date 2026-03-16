# 🤖 EAN AgentOS Pro — Multi-Agent Demos

> All outputs below are **real** — recorded live from Claude Code orchestrating Gemini CLI, Kimi CLI, and Codex CLI.

---

## Demo 1: Team Architecture Discussion

> Claude Code assigns roles and asks each agent to contribute to a REST API project.

```
📋 Project: Build a TODO REST API
   Orchestrator: Claude Code
   Team: Gemini CLI, Kimi CLI, Codex CLI

🤖 gemini-cli (Testing Expert):
   To thoroughly test a REST API /todos endpoint, I would implement
   happy path unit tests for all CRUD operations, ensuring successful
   data persistence and correct status codes (200, 201). I would also
   prioritize negative tests for input validation (400 Bad Request)
   and resource discovery (404 Not Found for invalid IDs).

🤖 kimi-cli (Security Analyst):
   Top security risks for a todo REST API:
   1. Broken Authentication/Authorization — weak or missing auth
      allows IDOR attacks where users access other users' data
   2. Injection attacks — SQL injection, NoSQL injection
   3. Missing rate limiting enables DoS attacks

🤖 codex-cli (Backend Developer):
   I'd standardize errors into a consistent response shape with HTTP
   status code, machine-readable error code, human-readable message,
   and optional request ID. Separate client errors (400, 401, 403)
   from server errors (500), validate input early, and avoid leaking
   sensitive details.

🧠 Result: 3 perspectives → testing + security + error handling
   All saved to shared memory for future sessions.
```

---

## Demo 2: AI Deliberation — SQL vs NoSQL

> All 3 agents debate the same question. Each brings a different answer.

```
🗣️ Question: SQL or NoSQL for a real-time chat app?

🤖 gemini-cli:
   NoSQL — flexible schema handles varied message types, distributed
   architecture allows horizontal scaling, optimized write performance
   and low-latency retrieval are essential for real-time chat.

🤖 kimi-cli:
   NoSQL (MongoDB or Redis) — chat messages are self-contained,
   write-heavy data with simple query patterns that benefit from
   horizontal scalability and flexible schema.

🤖 codex-cli:
   SQL — chat systems need strong guarantees around message ordering,
   user relationships, unread counts, and transactional updates.
   A relational database handles those predictably with indexing
   and partitioning.

🧠 Claude Code (orchestrator):
   Based on all 3 perspectives: NoSQL (MongoDB) for messages +
   PostgreSQL for user accounts. Hybrid approach.

📊 3 different opinions → 1 informed decision
```

---

## Demo 3: Peer Review — Security Audit

> All 3 agents review the same code and independently find the same vulnerability.

```
📋 Code: POST /api/login — no rate limiting, no account lockout

🔍 gemini-cli:
   Vulnerable to brute-force and credential stuffing attacks.
   Fix: implement rate limiting by IP/account and account lockout
   or progressive delays after multiple failures.

🔍 kimi-cli:
   Vulnerable to brute-force attacks — attackers can try unlimited
   passwords without restriction.
   Fix: max 5 attempts per IP/account per 15 minutes + progressive
   delay + account lockout after threshold.

🔍 codex-cli:
   Vulnerable to brute-force and credential-stuffing. Fix with
   per-IP and per-account rate limiting with exponential backoff
   or temporary lockouts after N failures.

🛡️ 3 reviewers independently found: missing rate limiting
   Consensus: add rate limiting + account lockout
   Vulnerability prevented before deployment.
```

---

## Demo 4: Security Audit — Real Vulnerable Code

> All 3 agents audit the same Flask login endpoint with SQL injection, plaintext passwords, and weak JWT.

```python
# The vulnerable code:
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = db.query("SELECT * FROM users WHERE email='" + data['email']
                    + "' AND password='" + data['password'] + "'")
    if user:
        token = jwt.encode({'user_id': user.id,
                'exp': datetime.utcnow() + timedelta(days=365)}, 'secret123')
        return jsonify({'token': token})
```

```
🔍 gemini-cli:
   1. SQL Injection (CRITICAL) — concatenates user input into raw SQL.
      Attacker sends: ' OR '1'='1 → bypasses authentication entirely.
   2. Plain-Text Password Comparison — passwords stored/compared as
      plaintext. Must use bcrypt or argon2 hashing.
   3. Weak JWT — hardcoded secret 'secret123', 365-day expiry.

🔍 kimi-cli:
   1. SQL Injection (CRITICAL) — attacker injects via email/password
      fields to bypass auth or exfiltrate entire database.
      Fix: parameterized queries or ORM.
   2. Passwords handled as plaintext — no hashing, no salting.
      Fix: bcrypt with salt rounds.
   3. Weak JWT secret + excessive token lifetime (365 days).
      Fix: strong random secret + short expiry + refresh tokens.

🔍 codex-cli:
   1. SQL injection — user input concatenated into SQL. Replace with
      parameterized queries so input is never interpreted as SQL.
   2. Passwords as plaintext — must hash with bcrypt/argon2 before
      storage, compare hashes on login.
   3. JWT hardcoded secret 'secret123' + 1-year expiry. Use
      env-stored secret + 15-minute access tokens + refresh flow.

🚨 CONSENSUS: All 3 found same 3 critical vulnerabilities
   Severity: CRITICAL — block deployment
   Fixes: parameterized SQL + password hashing + JWT hardening
```

---

## What these demos show

| Demo | What it proves |
|------|---------------|
| **Architecture** | Each agent brings a unique expertise (testing, security, backend) |
| **Deliberation** | Agents can disagree (SQL vs NoSQL) — orchestrator synthesizes |
| **Peer Review** | Multiple agents catch the same vulnerability independently |

All outputs are saved to shared memory. What one agent learns, all agents remember.

---

*Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro*
*The free version includes persistent memory, `mem suggest`, knowledge extraction, and more.*
