# Branch Specification v1.0

This document defines the memory branching model in EAN AgentOS.

---

## What is a Memory Branch?

A memory branch isolates a set of memory entities (decisions, facts, goals, tasks, resolutions) from the main memory line. This enables:

- **Experimentation** — try different approaches without affecting main memory
- **Parallel work** — multiple agents/features can have separate memory contexts
- **Review before merge** — compare branch memory against main before merging

---

## The `main` Branch

The `main` branch is implicit and always exists:

- It has **no row** in the `memory_branches` table
- Entities with `branch=NULL` or `branch='main'` belong to main
- It cannot be created, deleted, or renamed
- It is the default target for merges

---

## Branch-Aware Entity Tables

These tables have a `branch` column (default `'main'`):

| Table | Title field (used for conflict detection) |
|-------|------------------------------------------|
| `decisions` | title |
| `learned_facts` | fact |
| `goals` | title |
| `tasks` | title |
| `error_resolutions` | error_summary |

---

## Operations

### Create Branch

```bash
mem branch create feature-auth -d "Auth system exploration"
mem branch create experiment-redis --from feature-auth
```

**Rules:**
- Name cannot be `"main"`
- Name must be unique per project
- Parent defaults to current branch
- Parent must exist (active in `memory_branches` or `"main"`)

**API:**
```
POST /api/branches/switch
{"branch": "feature-auth", "project": "/path"}
```
Note: The API auto-creates branches on first switch.

### Switch Branch

```bash
mem branch switch feature-auth
mem branch switch main
```

**Behavior:**
- Sets current branch in state file (`v2_common.set_current_branch()`)
- Switching to `main` clears the state file (`clear_current_branch()`)
- All subsequent entity operations target the new branch
- Context builder reads only entities from the current branch

**API:**
```
POST /api/branches/switch
{"branch": "feature-auth", "project": "/path"}
```

### List Branches

```bash
mem branch list
```

Shows all active branches with entity counts per table. `main` always appears first.

**API:**
```
GET /api/branches?project=/path
```

Returns:
```json
{
  "ok": true,
  "branches": [
    {"name": "main", "counts": {"decisions": 5, "facts": 12, ...}},
    {"name": "feature-auth", "parent_branch": "main", "counts": {...}}
  ],
  "current": "main"
}
```

### Compare Branches

```bash
mem branch compare main feature-auth
mem branch diff main feature-auth    # compact format
```

Compares entities between two branches by title/fact/error_summary:

| Category | Meaning |
|----------|---------|
| `only_a` | Entities only in branch A |
| `only_b` | Entities only in branch B |
| `conflicts` | Same title exists in both branches (different entities) |

**API:**
```
GET /api/branches/compare?a=main&b=feature-auth&project=/path
```

### Replay Branch

```bash
mem branch replay feature-auth --days 30 --limit 50
```

Shows chronological timeline of all entity operations on a branch, combining:
- Decisions, facts, goals, tasks, resolutions created on the branch
- Merge operations involving the branch

**API:**
```
GET /api/branches/replay?branch=feature-auth&project=/path&days=30&limit=50
```

### Merge Branch

```bash
mem branch merge feature-auth --into main
mem branch merge feature-auth --strategy replace
```

**Behavior:**
1. Detect conflicts (same title in both branches)
2. If conflicts exist and strategy is not `replace`, warn the user
3. UPDATE all entities: `SET branch=target WHERE branch=source`
4. Log the merge in `branch_merge_log`

**Merge strategies:**

| Strategy | Conflict handling |
|----------|-------------------|
| `merge` (default) | Warns about conflicts, proceeds anyway |
| `replace` | Suppresses conflict warning, merges silently |

**Important:** Merge moves entities, it does not copy them. After merge, the source branch is empty.

**API:**
```
POST /api/branches/merge
{"source": "feature-auth", "target": "main", "confirm": true, "project": "/path"}
```

Without `confirm: true`, returns preview with conflict info.

### Delete Branch

```bash
mem branch delete feature-auth
```

**Rules:**
- Cannot delete `"main"`
- Refuses if entities remain on the branch (merge first)
- Sets `is_active=0` (soft delete)
- Auto-switches to `main` if deleted branch was current

### Detect Conflicts

```bash
mem branch conflicts main feature-auth
```

Finds entities with identical titles in both branches. Each conflict shows:
- Table name
- Entity IDs in both branches
- The conflicting title

---

## Conflict Detection

A **conflict** is detected when:
- The same table (e.g., `decisions`) has entities in both branches
- The title/fact/error_summary text matches exactly

Conflicts do NOT block merges — they are informational. The merge operation moves all entities regardless.

---

## Branch Merge Log

Every merge is recorded in `branch_merge_log`:

| Field | Description |
|-------|-------------|
| source_branch | Branch merged from |
| target_branch | Branch merged into |
| project_path | Project scope |
| strategy | `merge` or `replace` |
| conflicts_found | Number of conflicts detected |
| conflicts_resolved | Number resolved (currently same as found) |
| entities_merged | Total entities moved |
| merged_at | Timestamp |
| merged_by | Who initiated |
| notes | Additional context |

---

## Context Builder Integration

The context builder respects the current branch:
- `get_context()` only reads entities from the active branch
- If no branch is set, reads from `main`
- Branch name appears in context output for transparency

---

## Agent Events Integration

Branch operations emit agent events:

| Operation | Event type |
|-----------|------------|
| Switch branch | `branch_switched` |
| Compare branches | `branch_compared` |
| Merge branches | `branch_merged` |

---

## Limitations

1. **No partial merge** — merge moves ALL entities from source to target
2. **No undo merge** — use checkpoints before merging if you need rollback
3. **Simple conflict detection** — only exact title match, no semantic similarity
4. **No concurrent branch editing** — branch is a process-level state, not per-connection
5. **Flat hierarchy** — branches can have parents but this is metadata only, not structural
