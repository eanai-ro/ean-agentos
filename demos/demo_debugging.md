# :bug: Debugging — Memory Leak Diagnosis in FastAPI

> Real output from a live multi-agent orchestration session.

**Prompt:** "Our FastAPI production app's RSS memory grows from 200MB to 2GB over 24 hours, then OOM-kills. Stack: SQLAlchemy + PostgreSQL + Redis. Help diagnose."

---

## Agent Outputs

### Kimi — Performance Analyst

```
ROLE: Performance Analyst

DIAGNOSIS: Unclosed SQLAlchemy Sessions

ROOT CAUSE:
The most common cause of memory leaks in FastAPI + SQLAlchemy is
sessions that are opened but never properly closed. Each unclosed
session holds references to all ORM objects loaded during that
request, preventing garbage collection.

EVIDENCE TO LOOK FOR:
- db.session or Session() called without corresponding close()
- Missing try/finally blocks around database operations
- No session middleware or dependency injection with cleanup

TYPICAL LEAK PATTERN:
  # BAD — session never closed on exception
  @app.get("/users")
  async def get_users():
      session = SessionLocal()
      users = session.query(User).all()  # session stays open
      return users

FIX — Use dependency injection with yield:
  async def get_db():
      db = SessionLocal()
      try:
          yield db
      finally:
          db.close()

  @app.get("/users")
  async def get_users(db: Session = Depends(get_db)):
      return db.query(User).all()
      # Session automatically closed after response

VERIFICATION:
  # Monitor session count
  from sqlalchemy import event
  active_sessions = 0

  @event.listens_for(Session, "after_begin")
  def receive_after_begin(session, transaction, connection):
      nonlocal active_sessions
      active_sessions += 1

  # Expose as /debug/sessions endpoint
```

### Codex — Backend Engineer

```
ROLE: Backend Engineer

DIAGNOSIS: Long-Lived Sessions + Unbounded Cache

ROOT CAUSE (PRIMARY): SQLAlchemy Session Lifecycle
FastAPI is async but SQLAlchemy sessions are sync. If sessions are
created at module level or stored in global state, they accumulate
ORM identity map entries indefinitely.

Check for:
  # LEAK — global session never cleared
  session = Session()  # created once at import time

  @app.get("/items")
  async def get_items():
      return session.query(Item).all()
      # Identity map grows forever: 200MB → 2GB

ROOT CAUSE (SECONDARY): Unbounded In-Memory Cache
Common pattern — caching query results in a dict with no eviction:
  cache = {}  # grows forever
  def get_user(user_id):
      if user_id not in cache:
          cache[user_id] = db.query(User).get(user_id)
      return cache[user_id]

FIX FOR SESSIONS:
  # Option 1: Scoped session with proper cleanup
  from sqlalchemy.orm import scoped_session, sessionmaker
  SessionLocal = scoped_session(sessionmaker(bind=engine))

  @app.middleware("http")
  async def db_session_middleware(request, call_next):
      try:
          response = await call_next(request)
          return response
      finally:
          SessionLocal.remove()  # Critical: remove scoped session

  # Option 2: Depends with close
  async def get_db():
      db = SessionLocal()
      try:
          yield db
      finally:
          db.close()

FIX FOR CACHE:
  from functools import lru_cache
  # Or use Redis (already in stack) instead of in-memory dict

PROFILING:
  pip install memray
  memray run -o profile.bin uvicorn app:app
  memray flamegraph profile.bin  # visualize allocations
```

### Gemini — Systems Engineer

```
ROLE: Systems Engineer

DIAGNOSIS: Database Query Inefficiency Causing Memory Pressure

INITIAL ANALYSIS:
Checked for common memory leak sources in the Python/FastAPI stack.

FIRST HYPOTHESIS (REVISED):
Initially suspected missing database indexes causing full table scans
that load entire result sets into memory. While this contributes to
memory pressure, it does not explain the persistent growth pattern
(200MB → 2GB over 24h with no recovery).

REVISED DIAGNOSIS:
The growth-without-recovery pattern indicates object retention, not
just large queries. Most likely cause:

1. SQLAlchemy Identity Map — Sessions hold strong references to
   every object loaded. Without session.close() or session.expire_all(),
   these references accumulate.

2. Redis Connection Pool — If redis.ConnectionPool is created per-
   request instead of shared, each pool maintains its own buffer
   memory. Over 24h, thousands of abandoned pools accumulate.

FIX:
  # 1. Ensure sessions are closed (as other agents noted)

  # 2. Share Redis connection pool
  redis_pool = redis.ConnectionPool(host='localhost', port=6379,
                                     max_connections=20)
  redis_client = redis.Redis(connection_pool=redis_pool)
  # Use redis_client everywhere — do NOT create new Redis() per request

  # 3. Add indexes to reduce memory per query
  CREATE INDEX idx_users_email ON users(email);
  CREATE INDEX idx_orders_user_id ON orders(user_id);

MONITORING:
  import psutil, os
  @app.get("/debug/memory")
  async def memory_stats():
      process = psutil.Process(os.getpid())
      return {
          "rss_mb": process.memory_info().rss / 1024 / 1024,
          "connections": len(process.connections()),
          "open_files": len(process.open_files()),
      }
```

---

## Synthesis

### Root Cause Agreement

| Cause | Kimi | Codex | Gemini | Confidence |
|-------|------|-------|--------|------------|
| Unclosed SQLAlchemy sessions | PRIMARY | PRIMARY | CONFIRMED | HIGH |
| Unbounded in-memory cache | — | SECONDARY | — | MEDIUM |
| Redis connection pool leak | — | — | SECONDARY | MEDIUM |
| Missing indexes (memory pressure) | — | — | CONTRIBUTING | LOW |

### Recommended Fix (Priority Order)

```
1. [CRITICAL] Fix SQLAlchemy session lifecycle
   - Use Depends(get_db) with yield + finally: db.close()
   - OR use scoped_session with middleware that calls .remove()
   - All three agents agree this is the primary cause

2. [HIGH] Audit in-memory caches
   - Replace unbounded dicts with lru_cache or Redis
   - Set explicit max sizes on all caches

3. [MEDIUM] Share Redis connection pool
   - Single ConnectionPool instance, shared across app
   - Set max_connections to prevent pool exhaustion

4. [LOW] Add profiling endpoint
   - /debug/memory for RSS tracking
   - memray for allocation flamegraphs in staging
```

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
