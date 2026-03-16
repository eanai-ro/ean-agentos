#!/usr/bin/env python3
"""
Universal Memory Client — Generic Python SDK for Universal Agent Memory API.

Client reutilizabil care centralizează:
- HTTP request handling (GET/POST via urllib)
- JSON payload creation
- Common metadata (cli_name, agent_name, provider, model_name, session_id)

Zero dependențe externe — doar urllib din stdlib.

Utilizare directă:
    from clients.universal_memory_client import UniversalMemoryClient

    mem = UniversalMemoryClient(
        base_url="http://192.168.205.222:19876",
        project_path="/mnt/lucru/proiecte/my-project",
        cli_name="my-tool",
        agent_name="planner",
        provider="openai",
        model_name="o3",
    )

    mem.start_session("planning session")
    ctx = mem.get_context(mode="compact", intent="feature")
    mem.create_decision("Use SQLite", category="architectural")
    mem.create_fact("Project uses Python 3.11", fact_type="technical")
    mem.create_task("Implement adapter", priority="high")
    mem.send_event("agent_activity", title="Planning done")

Ca bază pentru adaptoare:
    class MyAdapter:
        def __init__(self, base_url, project_path, ...):
            self._client = UniversalMemoryClient(
                base_url=base_url, project_path=project_path,
                cli_name="my-cli", ...
            )
        def do_something(self):
            return self._client.create_decision("Use X")
"""

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class UniversalMemoryClient:
    """Generic Python client for Universal Agent Memory API."""

    def __init__(
        self,
        base_url: str = "http://localhost:19876",
        project_path: str = "",
        cli_name: str = "python-client",
        agent_name: str = "generic",
        provider: str = "unknown",
        model_name: str = "unknown",
        session_id: Optional[str] = None,
        session_prefix: str = "mem",
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.project_path = project_path
        self.cli_name = cli_name
        self.agent_name = agent_name
        self.provider = provider
        self.model_name = model_name
        self.timeout = timeout
        self.session_id = session_id or self._generate_session_id(session_prefix)

    @staticmethod
    def _generate_session_id(prefix: str) -> str:
        return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # ================================================================
    # HTTP helpers
    # ================================================================

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST JSON to API, return parsed response."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {body[:200]}"}
        except URLError as e:
            return {"ok": False, "error": f"Connection failed: {e.reason}"}

    def _get(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """GET from API, return parsed response."""
        url = f"{self.base_url}{endpoint}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v)
            if qs:
                url += f"?{qs}"
        req = Request(url, method="GET")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {body[:200]}"}
        except URLError as e:
            return {"ok": False, "error": f"Connection failed: {e.reason}"}

    def _meta(self) -> Dict[str, str]:
        """Common metadata fields for all requests."""
        return {
            "cli_name": self.cli_name,
            "agent_name": self.agent_name,
            "provider": self.provider,
            "model_name": self.model_name,
            "session_id": self.session_id,
            "project_path": self.project_path,
        }

    # ================================================================
    # Session
    # ================================================================

    def start_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Start a new session — sends session_start event."""
        payload = {
            **self._meta(),
            "event_type": "session_start",
            "title": title or f"{self.cli_name} session {self.session_id}",
            "payload": {
                "model": self.model_name,
                "provider": self.provider,
                "started_at": datetime.now().isoformat(),
            },
        }
        return self._post("/api/v1/events", payload)

    # ================================================================
    # Context
    # ================================================================

    def get_context(
        self,
        mode: str = "compact",
        intent: Optional[str] = None,
        budget: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Get memory context for the current project."""
        params = {
            "project": self.project_path,
            "mode": mode,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
        }
        if intent:
            params["intent"] = intent
        if budget:
            params["budget"] = str(budget)
        params.update({k: str(v) for k, v in kwargs.items() if v is not None})
        return self._get("/api/v1/context", params)

    # ================================================================
    # Create entities
    # ================================================================

    def create_decision(
        self,
        title: str,
        description: Optional[str] = None,
        category: str = "technical",
        confidence: str = "high",
        rationale: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a decision."""
        payload = {
            **self._meta(),
            "title": title,
            "description": description or title,
            "category": category,
            "confidence": confidence,
        }
        if rationale:
            payload["rationale"] = rationale
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/decisions", payload)

    def create_fact(
        self,
        fact: str,
        fact_type: str = "technical",
        category: str = "",
        confidence: str = "high",
        is_pinned: bool = False,
        source: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a learned fact."""
        payload = {
            **self._meta(),
            "fact": fact,
            "fact_type": fact_type,
            "confidence": confidence,
            "is_pinned": is_pinned,
        }
        if category:
            payload["category"] = category
        if source:
            payload["source"] = source
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/facts", payload)

    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        target_date: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a goal."""
        payload = {
            **self._meta(),
            "title": title,
            "priority": priority,
        }
        if description:
            payload["description"] = description
        if target_date:
            payload["target_date"] = target_date
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/goals", payload)

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        status: str = "todo",
        goal_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a task."""
        payload = {
            **self._meta(),
            "title": title,
            "priority": priority,
            "status": status,
        }
        if description:
            payload["description"] = description
        if goal_id:
            payload["goal_id"] = goal_id
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/tasks", payload)

    def create_resolution(
        self,
        error_summary: str,
        resolution: str,
        resolution_type: str = "fix",
        resolution_code: str = "",
        worked: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create an error resolution."""
        payload = {
            **self._meta(),
            "error_summary": error_summary,
            "resolution": resolution,
            "resolution_type": resolution_type,
            "worked": worked,
        }
        if resolution_code:
            payload["resolution_code"] = resolution_code
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/resolutions", payload)

    # ================================================================
    # Events
    # ================================================================

    def send_event(
        self,
        event_type: str,
        title: str = "",
        payload: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a generic event."""
        event_payload = {
            **self._meta(),
            "event_type": event_type,
            "title": title or event_type,
        }
        if payload:
            event_payload["payload"] = payload
        event_payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/events", event_payload)

    def log_activity(
        self,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log an agent activity event (shortcut for send_event)."""
        return self.send_event(
            event_type="agent_activity",
            title=summary,
            payload=payload or {"summary": summary},
        )

    # ================================================================
    # Read operations
    # ================================================================

    def get_activity(self, limit: int = 20, **kwargs) -> Dict[str, Any]:
        """Get recent activity log."""
        params = {
            "project": self.project_path,
            "limit": str(limit),
        }
        params.update({k: str(v) for k, v in kwargs.items() if v is not None})
        return self._get("/api/v1/activity", params)

    def get_health(self) -> Dict[str, Any]:
        """Get memory health counters."""
        return self._get("/api/v1/health", {"project": self.project_path})

    # ================================================================
    # Agent Event Stream
    # ================================================================

    def send_agent_event(
        self,
        event_type: str,
        title: str = "",
        summary: str = "",
        event_phase: str = "end",
        status: str = "completed",
        related_table: str = "",
        related_id: Optional[int] = None,
        parent_event_id: Optional[int] = None,
        duration_ms: Optional[int] = None,
        success_flag: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a fine-grained agent event to the event stream."""
        payload = {
            **self._meta(),
            "event_type": event_type,
            "title": title or event_type,
            "event_phase": event_phase,
            "status": status,
            "success_flag": success_flag,
        }
        if summary:
            payload["summary"] = summary
        if related_table:
            payload["related_table"] = related_table
        if related_id is not None:
            payload["related_id"] = related_id
        if parent_event_id is not None:
            payload["parent_event_id"] = parent_event_id
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if metadata:
            payload["metadata"] = metadata
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/api/v1/agent-events", payload)

    def get_agent_events(
        self,
        limit: int = 30,
        event_type: str = "",
        branch: str = "",
        failed: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Query agent events."""
        params = {
            "project": self.project_path,
            "limit": str(limit),
        }
        if event_type:
            params["type"] = event_type
        if branch:
            params["branch"] = branch
        if failed:
            params["failed"] = "1"
        params.update({k: str(v) for k, v in kwargs.items() if v is not None})
        return self._get("/api/v1/agent-events", params)
