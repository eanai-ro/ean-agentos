#!/usr/bin/env python3
"""
Universal Agent Memory — MCP Server.

Exposes memory operations as MCP tools for AI agents.

Usage:
    # stdio transport (default, for Claude Desktop / Cursor / etc.)
    python mcp_server/server.py

    # Or via mcp CLI
    mcp run mcp_server/server.py

Environment variables:
    MEMORY_BASE_URL       Memory API URL (default: http://localhost:19876)
    MEMORY_PROJECT_PATH   Default project path (default: cwd)
    MEMORY_AGENT_NAME     Default agent name (default: mcp-agent)
    MEMORY_MODEL_NAME     Default model name (default: unknown)
    MEMORY_PROVIDER       Default provider (default: mcp)
"""

import sys
import os

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP
from typing import Optional

from mcp_server.tools import (
    get_context,
    create_decision, create_fact, create_goal, create_task, create_resolution,
    list_branches, switch_branch, compare_branches, merge_branch,
    get_health, get_activity, get_timeline,
)

# Create MCP server
mcp = FastMCP(
    "Universal Agent Memory",
    instructions=(
        "Persistent, structured memory for AI coding agents. "
        "Use these tools to store and retrieve decisions, facts, goals, tasks, "
        "error resolutions, and manage memory branches."
    ),
)


# ================================================================
# CONTEXT
# ================================================================

@mcp.tool()
def memory_get_context(
    mode: str = "compact",
    project_path: str = "",
    branch: str = "",
    intent: str = "",
) -> dict:
    """Get assembled memory context for the current project.

    Returns structured knowledge: decisions, facts, goals, tasks, resolutions.
    Use this at session start to load project context.

    Args:
        mode: Context mode — compact (default), full, survival, or delta
        project_path: Project path (uses configured default if empty)
        branch: Memory branch name (uses current if empty)
        intent: Work intent — debugging, feature, refactor, deploy, docs, review, explore
    """
    return get_context(
        mode=mode,
        project_path=project_path or None,
        branch=branch or None,
        intent=intent or None,
    )


# ================================================================
# MEMORY WRITE
# ================================================================

@mcp.tool()
def memory_create_decision(
    title: str,
    description: str = "",
    category: str = "technical",
    confidence: str = "high",
    rationale: str = "",
    project_path: str = "",
) -> dict:
    """Record an architectural or technical decision.

    Args:
        title: Short decision title (e.g. "Use PostgreSQL for production")
        description: Detailed description of the decision
        category: technical, architectural, convention, process, security, performance
        confidence: confirmed, high, medium, low, speculative
        rationale: Why this decision was made
        project_path: Project path (uses configured default if empty)
    """
    return create_decision(
        title, description=description, category=category,
        confidence=confidence, rationale=rationale,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_create_fact(
    fact: str,
    fact_type: str = "technical",
    category: str = "",
    confidence: str = "high",
    source: str = "",
    project_path: str = "",
) -> dict:
    """Store a learned fact or piece of knowledge.

    Args:
        fact: The fact text (e.g. "API rate limit is 100 req/min")
        fact_type: technical, convention, preference, constraint, observation
        category: Optional grouping category
        confidence: confirmed, high, medium, low, speculative
        source: Where this fact was learned from
        project_path: Project path (uses configured default if empty)
    """
    return create_fact(
        fact, fact_type=fact_type, category=category,
        confidence=confidence, source=source,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_create_goal(
    title: str,
    description: str = "",
    priority: str = "medium",
    target_date: str = "",
    project_path: str = "",
) -> dict:
    """Create a high-level goal or objective.

    Args:
        title: Goal title (e.g. "Complete authentication module")
        description: Detailed description
        priority: critical, high, medium, low
        target_date: Target date in YYYY-MM-DD format
        project_path: Project path (uses configured default if empty)
    """
    return create_goal(
        title, description=description, priority=priority,
        target_date=target_date,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    goal_id: int = 0,
    project_path: str = "",
) -> dict:
    """Create a concrete task or action item.

    Args:
        title: Task title (e.g. "Write unit tests for auth")
        description: Detailed description
        priority: critical, high, medium, low
        goal_id: ID of parent goal (0 for no parent)
        project_path: Project path (uses configured default if empty)
    """
    return create_task(
        title, description=description, priority=priority,
        goal_id=goal_id if goal_id > 0 else None,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_create_resolution(
    error_summary: str,
    resolution: str,
    worked: bool = True,
    resolution_type: str = "fix",
    project_path: str = "",
) -> dict:
    """Record how an error was resolved. Prevents solving the same error twice.

    Args:
        error_summary: The error message or description
        resolution: How it was fixed
        worked: Whether the fix actually worked
        resolution_type: fix, workaround, dependency, config
        project_path: Project path (uses configured default if empty)
    """
    return create_resolution(
        error_summary, resolution, worked=worked,
        resolution_type=resolution_type,
        project_path=project_path or None,
    )


# ================================================================
# BRANCHES
# ================================================================

@mcp.tool()
def memory_list_branches(project_path: str = "") -> dict:
    """List all memory branches with entity counts and current branch.

    Args:
        project_path: Project path (uses configured default if empty)
    """
    return list_branches(project_path=project_path or None)


@mcp.tool()
def memory_switch_branch(branch: str, project_path: str = "") -> dict:
    """Switch to a different memory branch. New entities will be stored on this branch.

    Args:
        branch: Branch name to switch to
        project_path: Project path (uses configured default if empty)
    """
    return switch_branch(branch, project_path=project_path or None)


@mcp.tool()
def memory_compare_branches(
    branch_a: str = "main",
    branch_b: str = "",
    project_path: str = "",
) -> dict:
    """Compare two memory branches. Shows entities only in A, only in B, and conflicts.

    Args:
        branch_a: First branch (default: main)
        branch_b: Second branch to compare
        project_path: Project path (uses configured default if empty)
    """
    return compare_branches(
        branch_a=branch_a, branch_b=branch_b,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_merge_branch(
    source: str,
    target: str = "main",
    project_path: str = "",
) -> dict:
    """Merge a source branch into target. Moves all entities from source to target.

    Args:
        source: Source branch to merge from
        target: Target branch to merge into (default: main)
        project_path: Project path (uses configured default if empty)
    """
    return merge_branch(
        source, target=target,
        project_path=project_path or None,
    )


# ================================================================
# OBSERVABILITY
# ================================================================

@mcp.tool()
def memory_get_health(project_path: str = "") -> dict:
    """Get memory health — entity counts, stale items, conflicts.

    Args:
        project_path: Project path (uses configured default if empty)
    """
    return get_health(project_path=project_path or None)


@mcp.tool()
def memory_get_activity(
    limit: int = 20,
    action_type: str = "",
    project_path: str = "",
) -> dict:
    """Get recent agent activity log.

    Args:
        limit: Number of entries (max 100)
        action_type: Filter — decision, learn, goal, task, resolve, checkpoint
        project_path: Project path (uses configured default if empty)
    """
    return get_activity(
        limit=limit,
        action_type=action_type or None,
        project_path=project_path or None,
    )


@mcp.tool()
def memory_get_timeline(
    days: int = 30,
    limit: int = 20,
    project_path: str = "",
) -> dict:
    """Get chronological timeline of memory events.

    Args:
        days: Days to look back (default: 30)
        limit: Maximum events to return
        project_path: Project path (uses configured default if empty)
    """
    return get_timeline(
        days=days, limit=limit,
        project_path=project_path or None,
    )


# ================================================================
# ENTRY POINT
# ================================================================

def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
