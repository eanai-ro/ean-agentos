# :shield: Security Audit — Flask Login with SQL Injection

> Real output from a live multi-agent orchestration session.

**Prompt:** "Audit this Flask login endpoint for security vulnerabilities."

```python
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = db.query("SELECT * FROM users WHERE email='" + data['email'] + "'")
    if user and user['password'] == data['password']:
        token = jwt.encode({'user_id': user['id'], 'exp': datetime.utcnow() + timedelta(hours=24)}, 'secret123')
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401
```

---

## Agent Outputs

### Gemini — Security Auditor

```
ROLE: Security Auditor

FINDINGS:

[CRITICAL] SQL Injection (CVSS 9.8)
  Line: db.query("SELECT * FROM users WHERE email='" + data['email'] + "'")
  Impact: Full database compromise. Attacker can extract all data,
  modify records, or drop tables.
  Exploit: email = "' OR '1'='1' --"
  Fix: Use parameterized queries:
    db.query("SELECT * FROM users WHERE email = %s", (data['email'],))

[CRITICAL] Plaintext Password Storage (CVSS 9.1)
  Line: user['password'] == data['password']
  Impact: Passwords stored in plaintext. Any database breach exposes
  all user credentials directly.
  Fix: Use bcrypt for hashing:
    from bcrypt import hashpw, checkpw, gensalt
    # Store: hashpw(password.encode(), gensalt())
    # Verify: checkpw(data['password'].encode(), user['password_hash'])

[HIGH] Weak JWT Secret (CVSS 7.5)
  Line: jwt.encode({...}, 'secret123')
  Impact: Trivial to brute-force. Attacker can forge valid tokens
  for any user, achieving full account takeover.
  Fix: Use a cryptographically random secret (256+ bits):
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    Store in environment variable, never in source code.

[MEDIUM] No Rate Limiting (CVSS 5.3)
  No protection against brute-force attacks.
```

### Kimi — Security Auditor

```
ROLE: Security Auditor

FINDINGS:

[CRITICAL] SQL Injection — CWE-89 (CVSS 9.8)
  Vector: String concatenation in SQL query
  Proof of Concept:
    POST /login
    {"email": "admin'--", "password": "anything"}
    → Bypasses password check entirely

    {"email": "' UNION SELECT id,email,password,is_admin FROM users--", "password": "x"}
    → Dumps entire user table

  Fix: Parameterized queries with bound parameters:
    db.query("SELECT * FROM users WHERE email = :email", {"email": data['email']})

[CRITICAL] Plaintext Password Comparison — CWE-256 (CVSS 9.1)
  Vector: Direct string comparison means passwords are stored unhashed
  Impact: Single DB breach = all credentials exposed
  Fix: bcrypt with per-user salt:
    import bcrypt
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
    # Verify:
    bcrypt.checkpw(submitted.encode('utf-8'), stored_hash)

[HIGH] Hardcoded JWT Secret — CWE-798 (CVSS 7.5)
  Vector: 'secret123' is in source code, likely in version control
  Impact: Anyone with repo access can forge tokens
  Fix: Environment-based secret + refresh token rotation:
    JWT_SECRET = os.environ['JWT_SECRET']  # 256-bit random
    # Add refresh tokens: short-lived access (15min) + refresh (7d)

[MEDIUM] Missing Input Validation — CWE-20 (CVSS 4.3)
  No validation of email format or password length.
```

### Codex — Security Auditor

```
ROLE: Security Auditor

FINDINGS:

[CRITICAL] SQL Injection (CVSS 9.8)
  The query concatenates user input directly into SQL.
  This is the textbook example of SQL injection.

  Fix — Option A (ORM):
    user = User.query.filter_by(email=data['email']).first()

  Fix — Option B (Parameterized):
    cursor.execute("SELECT * FROM users WHERE email = %s", (data['email'],))

  Both completely prevent SQL injection.

[CRITICAL] Plaintext Password Storage (CVSS 9.1)
  The == comparison confirms passwords are stored as plain text.

  Fix: Use argon2 (preferred) or bcrypt:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    # Store: ph.hash(password)
    # Verify: ph.verify(stored_hash, submitted_password)

  Argon2 won the Password Hashing Competition and is the current
  OWASP recommendation over bcrypt.

[HIGH] Hardcoded JWT Secret (CVSS 7.5)
  'secret123' is guessable and version-controlled.

  Fix:
    JWT_SECRET = os.environ.get('JWT_SECRET')
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be set and >= 32 chars")

  Generate with: openssl rand -hex 32

[MEDIUM] Token Lifetime Too Long (CVSS 4.0)
  24-hour tokens increase the window for stolen token abuse.
  Use 15-minute access tokens with refresh token rotation.
```

---

## Synthesis

### Unanimous Findings

All three agents found the same three critical vulnerabilities:

| Vulnerability | CVSS | Gemini | Kimi | Codex |
|--------------|------|--------|------|-------|
| SQL Injection | 9.8 | Parameterized queries | Parameterized queries | ORM or parameterized |
| Plaintext Passwords | 9.1 | bcrypt | bcrypt with salt | argon2 or bcrypt |
| Weak JWT Secret | 7.5 | secrets.token_hex | env variable | env variable |

### Recommended Secure Implementation

```python
import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

JWT_SECRET = os.environ['JWT_SECRET']  # openssl rand -hex 32

@app.route('/login', methods=['POST'])
@limiter.limit("10/minute")
def login():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({"error": "Missing credentials"}), 400

    user = User.query.filter_by(email=data['email']).first()

    if user and bcrypt.checkpw(
        data['password'].encode('utf-8'),
        user.password_hash.encode('utf-8')
    ):
        token = jwt.encode(
            {'user_id': user.id, 'exp': datetime.utcnow() + timedelta(minutes=15)},
            JWT_SECRET,
            algorithm='HS256'
        )
        return jsonify({"token": token})

    return jsonify({"error": "Invalid credentials"}), 401
```

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
