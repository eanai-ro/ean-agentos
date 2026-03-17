"""
MCP Tool definitions for Universal Agent Memory.

All tools delegate to the existing REST API via UniversalMemoryClient.
No business logic is duplicated here.
"""

import sys
import os
from typing import Optional

# Add scripts dir to path for client import
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
sys.path.insert(0, _SCRIPTS_DIR)

from clients.universal_memory_client import UniversalMemoryClient
from mcp_server.config import BASE_URL, PROJECT_PATH, DEFAULT_AGENT, DEFAULT_MODEL, DEFAULT_PROVIDER, CLI_NAME


def _client(project_path: Optional[str] = None) -> UniversalMemoryClient:
    """Create a client instance."""
    return UniversalMemoryClient(
        base_url=BASE_URL,
        project_path=project_path or PROJECT_PATH,
        cli_name=CLI_NAME,
        agent_name=DEFAULT_AGENT,
        provider=DEFAULT_PROVIDER,
        model_name=DEFAULT_MODEL,
    )


# ================================================================
# CONTEXT
# ================================================================

def get_context(
    mode: str = "compact",
    project_path: Optional[str] = None,
    branch: Optional[str] = None,
    intent: Optional[str] = None,
) -> dict:
    """Get assembled memory context for the current project.

    Args:
        mode: Context mode — compact, full, survival, or delta
        project_path: Project path (uses default if not set)
        branch: Memory branch name (uses current if not set)
        intent: Work intent — debugging, feature, refactor, deploy, docs, review, explore
    """
    c = _client(project_path)
    kwargs = {}
    if branch:
        kwargs["branch"] = branch
    return c.get_context(mode=mode, intent=intent, **kwargs)


# ================================================================
# MEMORY WRITE
# ================================================================

def create_decision(
    title: str,
    description: str = "",
    category: str = "technical",
    confidence: str = "high",
    rationale: str = "",
    project_path: Optional[str] = None,
) -> dict:
    """Record an architectural or technical decision.

    Args:
        title: Short decision title
        description: Detailed description
        category: One of: technical, architectural, convention, process, security, performance
        confidence: One of: confirmed, high, medium, low, speculative
        rationale: Why this decision was made
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c.create_decision(title, description=description, category=category,
                             confidence=confidence, rationale=rationale)


def create_fact(
    fact: str,
    fact_type: str = "technical",
    category: str = "",
    confidence: str = "high",
    source: str = "",
    project_path: Optional[str] = None,
) -> dict:
    """Store a learned fact or piece of knowledge.

    Args:
        fact: The fact text
        fact_type: One of: technical, convention, preference, constraint, observation
        category: Optional category for grouping
        confidence: One of: confirmed, high, medium, low, speculative
        source: Where this fact was learned from
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c.create_fact(fact, fact_type=fact_type, category=category,
                         confidence=confidence, source=source)


def create_goal(
    title: str,
    description: str = "",
    priority: str = "medium",
    target_date: str = "",
    project_path: Optional[str] = None,
) -> dict:
    """Create a high-level goal or objective.

    Args:
        title: Goal title
        description: Detailed description
        priority: One of: critical, high, medium, low
        target_date: Target completion date (YYYY-MM-DD)
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c.create_goal(title, description=description, priority=priority,
                         target_date=target_date)


def create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    goal_id: Optional[int] = None,
    project_path: Optional[str] = None,
) -> dict:
    """Create a concrete task or action item.

    Args:
        title: Task title
        description: Detailed description
        priority: One of: critical, high, medium, low
        goal_id: Optional ID of parent goal
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c.create_task(title, description=description, priority=priority,
                         goal_id=goal_id)


def create_resolution(
    error_summary: str,
    resolution: str,
    worked: bool = True,
    resolution_type: str = "fix",
    project_path: Optional[str] = None,
) -> dict:
    """Record how an error was resolved.

    Args:
        error_summary: The error message or description
        resolution: How it was fixed
        worked: Whether the fix actually worked
        resolution_type: One of: fix, workaround, dependency, config
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c.create_resolution(error_summary, resolution, worked=worked,
                               resolution_type=resolution_type)


# ================================================================
# BRANCHES
# ================================================================

def list_branches(project_path: Optional[str] = None) -> dict:
    """List all memory branches with entity counts.

    Args:
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._get("/api/branches", {"project": c.project_path})


def switch_branch(branch: str, project_path: Optional[str] = None) -> dict:
    """Switch to a different memory branch.

    Args:
        branch: Branch name to switch to
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._post("/api/branches/switch", {"branch": branch, "project": c.project_path})


def compare_branches(
    branch_a: str = "main",
    branch_b: str = "",
    project_path: Optional[str] = None,
) -> dict:
    """Compare two memory branches showing differences per category.

    Args:
        branch_a: First branch (default: main)
        branch_b: Second branch to compare
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._get("/api/branches/compare", {
        "project": c.project_path,
        "a": branch_a,
        "b": branch_b,
    })


def merge_branch(
    source: str,
    target: str = "main",
    project_path: Optional[str] = None,
) -> dict:
    """Merge a source branch into a target branch.

    Moves all entities from source to target branch.

    Args:
        source: Source branch name
        target: Target branch name (default: main)
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._post("/api/branches/merge", {
        "source": source,
        "target": target,
        "confirm": True,
        "project": c.project_path,
    })


# ================================================================
# OBSERVABILITY
# ================================================================

def get_health(project_path: Optional[str] = None) -> dict:
    """Get memory health metrics — entity counts, stale items, conflicts.

    Args:
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._get("/api/health", {"project": c.project_path})


def get_activity(
    limit: int = 20,
    action_type: Optional[str] = None,
    project_path: Optional[str] = None,
) -> dict:
    """Get recent agent activity log.

    Args:
        limit: Number of entries to return (max 100)
        action_type: Filter by type — decision, learn, goal, task, resolve, checkpoint
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    params = {"project": c.project_path, "limit": str(limit)}
    if action_type:
        params["type"] = action_type
    return c._get("/api/activity", params)


def get_timeline(
    days: int = 30,
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """Get chronological timeline of memory events.

    Args:
        days: Number of days to look back (default: 30)
        limit: Maximum events to return
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._get("/api/timeline", {
        "project": c.project_path,
        "days": str(days),
        "limit": str(limit),
    })


