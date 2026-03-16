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


# ================================================================
# ORCHESTRATION (Premium features — require license)
# ================================================================

try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from license_gate import check_premium as _check_orch_premium
except ImportError:
    _check_orch_premium = lambda f="orchestration": True


def _require_orch():
    """Check orchestration license for MCP tools."""
    if not _check_orch_premium("orchestration"):
        return {"error": "Premium feature. Orchestration requires ean-agentos Pro license.",
                "upgrade_url": "https://ean-memory.dev/pro"}
    return None


def orch_create_project(
    title: str,
    description: str = "",
    project_path: Optional[str] = None,
) -> dict:
    """Create an orchestrated multi-agent project.

    Args:
        title: Project title
        description: Project description
        project_path: Project path (uses default if not set)
    """
    c = _client(project_path)
    return c._post("/api/v1/orch/projects", {
        "title": title,
        "description": description,
        "orchestrator_cli": CLI_NAME,
        "project_path": c.project_path,
    })


def orch_manage_tasks(
    action: str,
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    title: str = "",
    description: str = "",
    priority: str = "medium",
    task_type: str = "implementation",
    required_skills: Optional[str] = None,
    result_summary: str = "",
    error: str = "",
) -> dict:
    """Unified task management: create, claim, complete, fail, list.

    Args:
        action: One of: create, claim, complete, fail, list, list_mine
        project_id: Project ID (required for create, list)
        task_id: Task ID (required for claim, complete, fail)
        title: Task title (for create)
        description: Task description (for create)
        priority: critical, high, medium, low (for create)
        task_type: implementation, review, research, fix (for create)
        required_skills: JSON array of skills (for create)
        result_summary: Summary of result (for complete)
        error: Error description (for fail)
    """
    c = _client()

    if action == "create":
        return c._post("/api/v1/orch/tasks", {
            "project_id": project_id,
            "title": title,
            "description": description,
            "priority": priority,
            "task_type": task_type,
            "required_skills": required_skills,
            "created_by_cli": CLI_NAME,
        })

    elif action == "claim":
        return c._post(f"/api/v1/orch/tasks/{task_id}/claim", {
            "cli_name": CLI_NAME,
        })

    elif action == "complete":
        return c._post(f"/api/v1/orch/tasks/{task_id}/complete", {
            "lease_token": _get_lease_token(c, task_id),
            "result_summary": result_summary,
        })

    elif action == "fail":
        return c._post(f"/api/v1/orch/tasks/{task_id}/complete?failed=1", {
            "lease_token": _get_lease_token(c, task_id),
            "error": error,
        })

    elif action == "list":
        params = {}
        if project_id:
            params["project_id"] = str(project_id)
        return c._get("/api/v1/orch/tasks", params)

    elif action == "list_mine":
        params = {"mine": "1", "cli": CLI_NAME}
        if project_id:
            params["project_id"] = str(project_id)
        return c._get("/api/v1/orch/tasks", params)

    return {"error": f"Unknown action: {action}"}


def _get_lease_token(c, task_id: int) -> str:
    """Helper: fetch lease_token for a task from available tasks."""
    try:
        tasks = c._get("/api/v1/orch/tasks", {"mine": "1", "cli": CLI_NAME})
        for t in tasks:
            if t.get("id") == task_id:
                return t.get("lease_token", "")
    except Exception:
        pass
    return ""


def orch_deliberate(
    action: str,
    session_id: Optional[int] = None,
    topic: str = "",
    session_type: str = "deep",
    project_id: Optional[int] = None,
    content: str = "",
    confidence: float = 0.5,
    voted_for: str = "",
    reasoning: str = "",
) -> dict:
    """Unified deliberation: create, propose, vote, advance, synthesize, status.

    Args:
        action: One of: create, propose, vote, advance, synthesize, status
        session_id: Deliberation session ID (required for propose/vote/advance/synthesize/status)
        topic: Discussion topic (for create)
        session_type: quick (2 rounds), deep (4), expert (6) — for create
        project_id: Project ID (for create)
        content: Proposal content (for propose)
        confidence: Confidence level 0.0-1.0 (for propose)
        voted_for: What to vote for (for vote)
        reasoning: Vote reasoning (for vote)
    """
    c = _client()

    if action == "create":
        return c._post("/api/v1/orch/deliberation", {
            "topic": topic,
            "session_type": session_type,
            "project_id": project_id,
            "started_by_cli": CLI_NAME,
        })

    elif action == "status":
        return c._get(f"/api/v1/orch/deliberation/{session_id}", {})

    elif action in ("propose", "vote", "advance", "synthesize"):
        payload = {"action": action, "cli_name": CLI_NAME}
        if action == "propose":
            payload["content"] = content
            payload["confidence"] = confidence
        elif action == "vote":
            payload["voted_for"] = voted_for
            payload["reasoning"] = reasoning
        return c._post(f"/api/v1/orch/deliberation/{session_id}/respond", payload)

    return {"error": f"Unknown action: {action}"}


def orch_message(
    to_cli: str = "",
    content: str = "",
    message_type: str = "info",
    project_id: Optional[int] = None,
    unread_only: bool = True,
    limit: int = 20,
) -> dict:
    """Send or read inter-agent messages.

    If content is provided, sends a message. Otherwise reads messages.

    Args:
        to_cli: Target CLI (empty = broadcast when sending, reads own when receiving)
        content: Message content (if provided, sends; if empty, reads)
        message_type: info, question, answer, review, correction, handoff
        project_id: Project ID filter
        unread_only: Only unread messages (for reading)
        limit: Max messages to return (for reading)
    """
    c = _client()

    if content:
        return c._post("/api/v1/orch/messages", {
            "from_cli": CLI_NAME,
            "to_cli": to_cli or None,
            "content": content,
            "message_type": message_type,
            "project_id": project_id,
        })
    else:
        params = {"to": to_cli or CLI_NAME, "limit": str(limit)}
        if unread_only:
            params["unread"] = "1"
        if project_id:
            params["project_id"] = str(project_id)
        return c._get("/api/v1/orch/messages", params)


def orch_heartbeat() -> dict:
    """Report agent presence and get status updates.

    Returns: agents online, unread messages, stale leases cleaned.
    """
    c = _client()
    return c._post("/api/v1/orch/heartbeat", {
        "cli_name": CLI_NAME,
    })


def orch_launch(
    cli_name: str,
    task_id: Optional[int] = None,
    session_id: Optional[int] = None,
    prompt: str = "",
    timeout: int = 300,
    permission_mode: str = "safe",
    working_dir: str = "",
) -> dict:
    """Launch a CLI agent for a task, deliberation session, or custom prompt.

    Args:
        cli_name: Target CLI (claude-code, gemini-cli, codex-cli, kimi-cli)
        task_id: Task ID to launch for (mutually exclusive with session_id/prompt)
        session_id: Deliberation session ID
        prompt: Custom prompt text
        timeout: Timeout in seconds (default 300)
        permission_mode: safe (default), auto, or unsafe
        working_dir: Working directory override

    Returns: Launch result with status, output, log_path
    """
    c = _client()
    payload = {
        "cli_name": cli_name,
        "timeout": timeout,
        "permission_mode": permission_mode,
    }
    if task_id:
        payload["task_id"] = task_id
    elif session_id:
        payload["session_id"] = session_id
    elif prompt:
        payload["prompt"] = prompt
    if working_dir:
        payload["working_dir"] = working_dir
    return c._post("/api/v1/orch/launch", payload)
