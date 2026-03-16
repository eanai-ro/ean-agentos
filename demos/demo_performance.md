# :zap: Performance — PostgreSQL Query Optimization

> Real output from a live multi-agent orchestration session.

**Prompt:** "This PostgreSQL query takes 12 seconds. The orders table has 1M rows. Help optimize."

```sql
SELECT *
FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN products p ON o.product_id = p.id
WHERE o.status = 'pending'
  AND o.created_at > '2025-01-01'
ORDER BY o.created_at DESC
LIMIT 50;
```

**Current state:** No indexes beyond primary keys. Tables: orders (1M rows), customers (50K rows), products (10K rows).

---

## Agent Outputs

### Gemini — Database Expert

```
ROLE: Database Performance Expert

ANALYSIS:
12 seconds for a 3-table join with LIMIT 50 indicates sequential
scans on all tables. PostgreSQL is scanning 1M order rows because
there are no indexes on the filter or join columns.

OPTIMIZATIONS:

1. Add B-tree Indexes on Join Keys:
   CREATE INDEX idx_orders_customer_id ON orders(customer_id);
   CREATE INDEX idx_orders_product_id ON orders(product_id);

2. Add Composite Index for Filter + Sort:
   CREATE INDEX idx_orders_status_created
     ON orders(status, created_at DESC);

   This single index serves both the WHERE clause and ORDER BY.
   PostgreSQL can use an index-only backward scan to find the
   top 50 matching rows without scanning 1M rows.

3. Replace SELECT * with Specific Columns:
   SELECT o.id, o.status, o.created_at, o.total,
          c.name, c.email,
          p.name AS product_name, p.price
   FROM ...

   SELECT * fetches all columns from all 3 tables. If orders
   has 30 columns, that is 3x more data than needed.

4. Run ANALYZE After Index Creation:
   ANALYZE orders;
   ANALYZE customers;
   ANALYZE products;

   Updates statistics so the query planner chooses optimal paths.

EXPECTED IMPROVEMENT: 12s → 5-20ms
```

### Kimi — Database Expert

```
ROLE: Database Performance Expert

ANALYSIS:
Without EXPLAIN ANALYZE output, working from the query structure.
The 12-second runtime on 1M rows with no indexes strongly suggests
full sequential scans. Here is the fix:

STEP 1: Run EXPLAIN ANALYZE to Confirm
   EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
   SELECT * FROM orders o
   JOIN customers c ON o.customer_id = c.id
   JOIN products p ON o.product_id = p.id
   WHERE o.status = 'pending'
     AND o.created_at > '2025-01-01'
   ORDER BY o.created_at DESC
   LIMIT 50;

   Look for: Seq Scan, Sort (external merge), high row estimates.

STEP 2: Create Composite Indexes
   -- Covers WHERE + ORDER BY + JOIN in one index
   CREATE INDEX idx_orders_status_created_cust_prod
     ON orders(status, created_at DESC, customer_id, product_id);

   -- Join targets (if not already indexed)
   CREATE INDEX idx_customers_id ON customers(id);  -- likely exists (PK)
   CREATE INDEX idx_products_id ON products(id);     -- likely exists (PK)

STEP 3: Replace SELECT *
   Only fetch columns used by the application. This reduces:
   - I/O (fewer pages read from disk)
   - Memory (smaller sort buffers)
   - Network (less data transferred to app)

STEP 4: Consider Partial Index
   If most orders are NOT 'pending':
   CREATE INDEX idx_orders_pending ON orders(created_at DESC)
     WHERE status = 'pending';

   This index only contains pending orders — much smaller and faster.

EXPECTED: 12s → under 10ms with proper indexes.
```

### Codex — Database Expert

```
ROLE: Database Performance Expert

ANALYSIS:
Three problems causing the 12-second query:
1. No indexes on join columns (customer_id, product_id)
2. No index on filter columns (status, created_at)
3. SELECT * pulling unnecessary data across the wire

FIX:

1. Indexes on JOIN Columns:
   CREATE INDEX idx_orders_customer_id ON orders(customer_id);
   CREATE INDEX idx_orders_product_id ON orders(product_id);

   Without these, PostgreSQL uses hash joins or nested loops
   with sequential scans on the 1M-row orders table.

2. Indexes on WHERE + ORDER BY Columns:
   CREATE INDEX idx_orders_status_created
     ON orders(status, created_at DESC);

   Column order matters: status first (equality), then
   created_at DESC (range + sort). This lets PostgreSQL
   satisfy WHERE, ORDER BY, and LIMIT from the index alone.

3. Replace SELECT * with Specific Columns:
   Reduces I/O by 50-80% depending on table width.
   If orders has TEXT/JSONB columns, the impact is even larger
   because those are stored out-of-line (TOASTed).

4. After Creating Indexes:
   ANALYZE orders;
   -- Verify with EXPLAIN ANALYZE that indexes are used

BONUS — If Query is Still Slow:
   -- Covering index (index-only scan, no table access)
   CREATE INDEX idx_orders_covering ON orders(
     status, created_at DESC, customer_id, product_id, id, total
   );

EXPECTED: 12s → 1-10ms depending on data distribution.
```

---

## Synthesis

### Full Agreement

All three agents identified the same three optimizations:

| Optimization | Gemini | Kimi | Codex | Impact |
|-------------|--------|------|-------|--------|
| Add indexes on join keys | B-tree indexes | Composite index | Individual indexes | HIGH |
| Composite index for WHERE + ORDER BY | status, created_at DESC | status, created_at DESC | status, created_at DESC | CRITICAL |
| Replace SELECT * | Specific columns | Specific columns | Specific columns | MEDIUM |
| Run EXPLAIN ANALYZE | After fix | Before fix | After fix | DIAGNOSTIC |

### Recommended Execution Order

```sql
-- Step 1: Baseline measurement
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders o ... ;

-- Step 2: Create indexes (can run concurrently in production)
CREATE INDEX CONCURRENTLY idx_orders_status_created
  ON orders(status, created_at DESC);
CREATE INDEX CONCURRENTLY idx_orders_customer_id
  ON orders(customer_id);
CREATE INDEX CONCURRENTLY idx_orders_product_id
  ON orders(product_id);

-- Step 3: Update statistics
ANALYZE orders;

-- Step 4: Verify improvement
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.status, o.created_at, o.total,
       c.name, c.email,
       p.name AS product_name, p.price
FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN products p ON o.product_id = p.id
WHERE o.status = 'pending'
  AND o.created_at > '2025-01-01'
ORDER BY o.created_at DESC
LIMIT 50;

-- Expected: 12 seconds → under 10 milliseconds
```

### Bonus: Partial Index (from Kimi)

If less than 5% of orders are "pending":

```sql
CREATE INDEX idx_orders_pending
  ON orders(created_at DESC, customer_id, product_id)
  WHERE status = 'pending';
```

This creates a much smaller, faster index covering only the relevant rows.

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
