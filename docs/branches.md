# Memory Branches

Memory branches let you isolate experimental knowledge without polluting your main memory. Like git branches, but for structured memory entities.

## Concepts

### Branch Isolation

Each entity (decision, fact, goal, task, resolution) has a `branch` column. When you switch to a branch, new entities are created on that branch. Context queries only return entities from the current branch.

### Main Branch

`main` is the default branch. It always exists (implicitly). Entities with `branch = NULL` are treated as belonging to `main` for backward compatibility.

### Parent Branch

Every branch has a parent (defaults to the current branch at creation time). This is metadata only — entities are not copied from parent to child.

## CLI Commands

### Create a branch

```bash
python3 scripts/mem branch create feature-auth -d "Authentication exploration"

# Create from specific parent
python3 scripts/mem branch create hotfix --from main
```

### List branches

```bash
python3 scripts/mem branch list
```

Output:
```
  * main (15 entities) ← current
  * feature-auth (5 entities) — Authentication exploration
  * experiment-redis (3 entities) (from: main)
```

### Switch branch

```bash
python3 scripts/mem branch switch feature-auth
python3 scripts/mem branch switch main
```

### Compare branches

```bash
# Detailed per-category comparison
python3 scripts/mem branch compare main feature-auth

# Compact diff
python3 scripts/mem branch diff main feature-auth
```

Output:
```
  ── DECISIONS ──────────────────────────────────
    Only in main:
      +   #1 Use SQLite                        [2026-03-12]
    Only in feature-auth:
      +   #5 Use JWT tokens                    [2026-03-12]
    ⚠ Conflicts (1):
      #3 (main) ↔ #6 (feature-auth): Shared config

  Summary:
    main: 1 unique entities
    feature-auth: 1 unique entities
    Conflicts: 1
```

### Replay branch activity

```bash
# All activity on a branch
python3 scripts/mem branch replay feature-auth

# Last 7 days
python3 scripts/mem branch replay feature-auth --days 7

# Limit to 10 events
python3 scripts/mem branch replay feature-auth --limit 10
```

### Merge branches

```bash
# Merge feature-auth into main
python3 scripts/mem branch merge feature-auth --into main
```

This moves all entities from `feature-auth` to `main` (updates the `branch` column).

### Detect conflicts

```bash
python3 scripts/mem branch conflicts main feature-auth
```

Conflicts are entities with the same title on both branches.

### Delete a branch

```bash
python3 scripts/mem branch delete feature-auth
```

Only works if the branch has no remaining entities (merge first).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/branches` | List branches with entity counts |
| GET | `/api/branches/compare?a=main&b=feature-x` | Compare two branches |
| GET | `/api/branches/replay?branch=feature-x` | Replay branch activity |
| POST | `/api/branches/switch` | Switch current branch |
| POST | `/api/branches/merge` | Merge (2-step with preview) |

## Web UI

The Branches tab in the web dashboard provides:

- Branch list with current indicator and entity counts
- Switch button per branch
- Compare button (opens structured diff view)
- Merge button (opens preview modal with confirmation)
- Branch chip in topbar when not on main

## How Branch Filtering Works

Entity queries include:

```sql
WHERE (branch = ? OR (branch IS NULL AND ? = 'main'))
```

This means:
- On `main`: you see entities with `branch = 'main'` AND entities with `branch = NULL`
- On any other branch: you see only entities with that exact branch name

## Merge Behavior

Merging moves entities — it does NOT copy them. After merge, the source branch has 0 entities. The merge is logged in `branch_merge_log` with entity count and conflict count.

If conflicts exist (same title on both branches), the merge still proceeds — entities are moved regardless. The conflict count is recorded for audit purposes.
