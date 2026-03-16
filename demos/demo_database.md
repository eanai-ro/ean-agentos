# :floppy_disk: Database Decision — SQL vs NoSQL for Chat Application

> Real output from a live multi-agent orchestration session.

**Prompt:** "We're building a real-time chat application expecting 50K concurrent users. Should we use SQL or NoSQL for message storage?"

---

## Agent Outputs

### Gemini — NoSQL Advocate

```
ROLE: Database Architect

RECOMMENDATION: NoSQL (MongoDB)

RATIONALE:
1. Flexible Schema — Chat messages vary in structure: text, images,
   reactions, threads, edits, deletions. A document model handles
   this naturally without schema migrations.

2. Horizontal Scaling — At 50K concurrent users generating ~500K
   messages/hour, you need write scalability. MongoDB sharding
   distributes writes across nodes transparently.

3. Write Performance — MongoDB with WiredTiger engine handles
   high-throughput inserts with configurable write concern.
   For chat, w:1 (acknowledge after primary write) gives the
   best latency while journaling prevents data loss.

4. Natural Document Model — A message is a self-contained document:
   {sender, recipient, content, timestamp, read_receipts, reactions}
   No JOINs needed for the primary read path.

CAVEATS:
- Use a separate store for user accounts (PostgreSQL is fine)
- Implement TTL indexes for message expiration if needed
- Consider MongoDB Atlas for managed sharding
```

### Kimi — NoSQL Advocate

```
ROLE: Database Architect

RECOMMENDATION: NoSQL (MongoDB for messages, Redis for presence)

RATIONALE:
1. Write-Heavy Workload — Chat is 80% writes, 20% reads.
   NoSQL databases are optimized for this pattern. MongoDB
   can sustain 100K+ inserts/second on modest hardware.

2. Horizontal Scalability — SQL vertical scaling hits a ceiling.
   At 50K concurrent users today, plan for 500K tomorrow.
   MongoDB sharding scales linearly with added nodes.

3. Real-Time Layer — Use Redis for:
   - Online/offline presence (SET with TTL)
   - Typing indicators (PUB/SUB)
   - Recent message cache (sorted sets by timestamp)
   - Unread counts (INCR/DECR)

4. Data Model:
   messages collection — sharded by conversation_id
   conversations collection — participant lists, metadata
   Redis sorted sets — last 100 messages per conversation

ARCHITECTURE:
  Client → WebSocket → Redis PUB/SUB → MongoDB (persist)
                     → Redis Cache (fast reads)
```

### Codex — SQL Advocate

```
ROLE: Database Architect

RECOMMENDATION: SQL (PostgreSQL)

RATIONALE:
1. Message Ordering Guarantees — Chat requires strict chronological
   ordering. PostgreSQL sequences and timestamp indexes guarantee
   this. NoSQL eventual consistency can show messages out of order.

2. Relationships Matter — Users, conversations, participants,
   messages, read receipts — these are relational data.
   A JOIN to get "all messages in conversation X by user Y
   after timestamp Z" is one query in SQL, multiple queries
   or denormalized data in NoSQL.

3. Transactional Updates — "Mark all messages as read" needs
   atomicity. PostgreSQL handles this in a single transaction.
   In MongoDB, multi-document transactions have higher overhead.

4. PostgreSQL Scales — With partitioning by date range,
   connection pooling (PgBouncer), and read replicas,
   PostgreSQL handles 50K concurrent users comfortably.
   Instagram ran on PostgreSQL at much larger scale.

SCHEMA:
  messages (id, conversation_id, sender_id, content, created_at)
  — PARTITION BY RANGE (created_at)
  — INDEX on (conversation_id, created_at DESC)
```

---

## Claude Synthesis

```
SYNTHESIS: Hybrid Architecture

The agents split 2:1 in favor of NoSQL, but each perspective has
merit. The optimal solution combines both:

RECOMMENDED ARCHITECTURE:
+-----------------------+     +-------------------------+
| PostgreSQL            |     | MongoDB                 |
| - User accounts       |     | - Message storage       |
| - Conversations       |     | - Message search        |
| - Billing/payments    |     | - File metadata         |
| - Audit logs          |     |                         |
+-----------------------+     +-------------------------+
          |                              |
          +----------+  +---------------+
                     |  |
              +------+--+------+
              | Redis           |
              | - Presence      |
              | - Message cache |
              | - Typing status |
              | - Unread counts |
              +-----------------+

WHY HYBRID:
- Messages are write-heavy, schema-flexible → MongoDB
- Accounts need ACID transactions, relationships → PostgreSQL
- Real-time features need sub-millisecond latency → Redis

This matches what Discord, Slack, and WhatsApp use in production.
```

---

## Consensus Matrix

| Factor | Gemini | Kimi | Codex | Final |
|--------|--------|------|-------|-------|
| Message storage | MongoDB | MongoDB | PostgreSQL | MongoDB |
| User accounts | PostgreSQL | (implicit) | PostgreSQL | PostgreSQL |
| Real-time cache | — | Redis | — | Redis |
| Scaling strategy | Sharding | Sharding | Partitioning | Both |

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
