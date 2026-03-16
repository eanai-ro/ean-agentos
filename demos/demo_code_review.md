# :mag: Code Review — Login Endpoint Peer Review

> Real output from a live multi-agent orchestration session.

**Prompt:** "Review this login endpoint for security and best practices."

```python
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password_hash, data['password']):
        token = create_access_token(identity=user.id, expires_delta=timedelta(hours=24))
        return jsonify({"token": token, "user": {"id": user.id, "email": user.email}})
    return jsonify({"error": "Invalid credentials"}), 401
```

---

## Agent Outputs

### Gemini — Security Reviewer

```
ROLE: Security Reviewer

CRITICAL FINDING: Missing Rate Limiting
This endpoint has no rate limiting. An attacker can attempt thousands
of login requests per second for brute-force credential stuffing.

RECOMMENDATIONS:
1. Rate Limiting by IP — Max 10 attempts per minute per IP address.
   Use Flask-Limiter with Redis backend:
   @limiter.limit("10/minute")

2. Rate Limiting by Account — Max 5 failed attempts per account
   per 15 minutes. Track in database or Redis.

3. Progressive Delays — After 3 failed attempts, add artificial
   delay: 1s, 2s, 4s, 8s. Makes brute-force impractical.

4. Account Lockout — After 10 consecutive failures, lock the
   account for 30 minutes. Send email notification to user.

OTHER FINDINGS:
- [MEDIUM] Token expiry too long — 24h is excessive for a login
  token. Use 15-minute access token + 7-day refresh token.
- [LOW] No request validation — Missing check for required fields.
  data['email'] throws KeyError if field is absent.
- [LOW] User enumeration — Response time differs between valid
  and invalid emails (DB query vs. no query). Use constant-time
  comparison or always query.
```

### Kimi — Security Reviewer

```
ROLE: Security Reviewer

CRITICAL FINDING: Brute-Force Vulnerability
No mechanism prevents unlimited login attempts. This is the #1
vulnerability in authentication systems (OWASP A07:2021).

RECOMMENDATIONS:
1. Rate Limiting Policy:
   - Max 5 attempts per 15 minutes per account
   - Max 20 attempts per 15 minutes per IP
   - Progressive delay: 0s, 1s, 2s, 4s, 8s, 16s after each failure
   - Account lockout after 10 failures (30-min cooldown)

2. Implementation:
   failed_attempts = redis.incr(f"login_fail:{email}")
   redis.expire(f"login_fail:{email}", 900)  # 15 min window
   if failed_attempts > 5:
       delay = min(2 ** (failed_attempts - 5), 60)
       time.sleep(delay)
   if failed_attempts > 10:
       return jsonify({"error": "Account temporarily locked"}), 429

3. Monitoring — Log all failed attempts with IP, email, timestamp,
   User-Agent. Alert on >100 failures/hour from single IP.

OTHER FINDINGS:
- [HIGH] No CSRF protection on POST endpoint
- [MEDIUM] Password hash timing — check_password_hash may leak
  info via timing. Ensure constant-time comparison.
- [LOW] Missing Content-Type validation — Endpoint assumes JSON
  but doesn't verify Content-Type header.
```

### Codex — Security Reviewer

```
ROLE: Security Reviewer

CRITICAL FINDING: No Rate Limiting
Endpoint accepts unlimited authentication attempts. Combined with
the generic error message (which is good), an attacker can run
credential stuffing attacks undetected.

RECOMMENDATIONS:
1. Per-IP Rate Limiting:
   - 10 requests/minute from same IP
   - Use sliding window algorithm, not fixed window
   - Store in Redis for distributed deployments

2. Per-Account Rate Limiting:
   - 5 failed attempts per account per 15 minutes
   - Exponential backoff: base=1s, multiplier=2, max=60s
   - After 15 failures: lock account, require email verification

3. Implementation Pattern:
   from flask_limiter import Limiter
   limiter = Limiter(app, key_func=get_remote_address,
                     storage_uri="redis://localhost:6379")

   @app.route('/login', methods=['POST'])
   @limiter.limit("10/minute")
   def login():
       # ... existing code ...
       # Add per-account tracking in the failure path

4. Response Headers — Include rate limit headers:
   X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

OTHER FINDINGS:
- [MEDIUM] No input sanitization — email field not validated
- [MEDIUM] Token scope too broad — 24h single token, no refresh
- [LOW] Missing request ID for tracing/debugging
```

---

## Synthesis

### Unanimous Finding

All three agents independently identified **missing rate limiting** as the critical vulnerability, confirming it as the top-priority fix.

### Combined Rate Limiting Strategy

```
Per-IP:       10 requests/minute (sliding window)
Per-Account:  5 failed attempts per 15 minutes
Backoff:      Exponential — 1s, 2s, 4s, 8s, 16s (max 60s)
Lockout:      After 10-15 failures, lock for 30 minutes
Notification: Email user on lockout
Storage:      Redis (works across multiple app instances)
Headers:      X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
```

### All Findings by Severity

| Finding | Gemini | Kimi | Codex | Priority |
|---------|--------|------|-------|----------|
| No rate limiting | Yes | Yes | Yes | CRITICAL |
| Token expiry too long | Yes | — | Yes | MEDIUM |
| No input validation | Yes | Yes | Yes | MEDIUM |
| CSRF protection | — | Yes | — | HIGH |
| Timing attacks | — | Yes | — | MEDIUM |
| Missing request ID | — | — | Yes | LOW |

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
