#!/usr/bin/env python3
"""
Codex CLI Adapter — Universal Agent Memory API client.

Wrapper simplu care permite Codex CLI (sau orice agent OpenAI)
să folosească memoria universală via HTTP API.

Deleghează intern către UniversalMemoryClient.
Nu depinde de SDK-uri grele.

Exemplu:
    from adapters.codex_cli_adapter import CodexMemoryAdapter

    mem = CodexMemoryAdapter(
        base_url="http://192.168.205.222:19876",
        project_path="/mnt/lucru/proiecte/my-project",
        model_name="o3",
    )

    # Start session
    mem.start_session()

    # Get context
    ctx = mem.get_context(mode="compact", intent="feature")

    # Create entities
    mem.create_decision("Use PostgreSQL", description="For production DB")
    mem.create_fact("Project uses TypeScript", fact_type="convention")
    mem.create_task("Setup CI/CD", priority="high")

    # Log activity
    mem.log_activity("Analyzed codebase structure")
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure clients package is importable
_scripts_dir = Path(__file__).parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from clients.universal_memory_client import UniversalMemoryClient


class CodexMemoryAdapter:
    """Client adaptor pentru Universal Agent Memory API (OpenAI/Codex)."""

    def __init__(
        self,
        base_url: str = "http://localhost:19876",
        project_path: str = "",
        cli_name: str = "codex-cli",
        agent_name: str = "codex",
        provider: str = "openai",
        model_name: str = "o3",
        session_id: Optional[str] = None,
    ):
        self._client = UniversalMemoryClient(
            base_url=base_url,
            project_path=project_path,
            cli_name=cli_name,
            agent_name=agent_name,
            provider=provider,
            model_name=model_name,
            session_id=session_id,
            session_prefix="codex",
        )

    # Expose key attributes for backward compatibility
    @property
    def base_url(self) -> str:
        return self._client.base_url

    @property
    def project_path(self) -> str:
        return self._client.project_path

    @property
    def cli_name(self) -> str:
        return self._client.cli_name

    @property
    def agent_name(self) -> str:
        return self._client.agent_name

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model_name(self) -> str:
        return self._client.model_name

    @property
    def session_id(self) -> str:
        return self._client.session_id

    # Expose _get/_post for tests that use them directly
    def _get(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self._client._get(endpoint, params)

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client._post(endpoint, payload)

    # ================================================================
    # Delegate all public methods to client
    # ================================================================

    def start_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        return self._client.start_session(title)

    def get_context(self, mode: str = "compact", intent: Optional[str] = None) -> Dict[str, Any]:
        return self._client.get_context(mode=mode, intent=intent)

    def create_decision(self, title: str, description: str = "", category: str = "technical",
                        confidence: str = "high", rationale: str = "") -> Dict[str, Any]:
        return self._client.create_decision(title, description=description or None,
                                            category=category, confidence=confidence, rationale=rationale)

    def create_fact(self, fact: str, fact_type: str = "technical", category: str = "",
                    confidence: str = "high", is_pinned: bool = False, source: str = "") -> Dict[str, Any]:
        return self._client.create_fact(fact, fact_type=fact_type, category=category,
                                        confidence=confidence, is_pinned=is_pinned, source=source)

    def create_goal(self, title: str, description: str = "", priority: str = "medium",
                    target_date: str = "") -> Dict[str, Any]:
        return self._client.create_goal(title, description=description, priority=priority,
                                        target_date=target_date)

    def create_task(self, title: str, description: str = "", priority: str = "medium",
                    status: str = "todo", goal_id: Optional[int] = None) -> Dict[str, Any]:
        return self._client.create_task(title, description=description, priority=priority,
                                        status=status, goal_id=goal_id)

    def create_resolution(self, error_summary: str, resolution: str, resolution_type: str = "fix",
                          resolution_code: str = "", worked: bool = True) -> Dict[str, Any]:
        return self._client.create_resolution(error_summary, resolution, resolution_type=resolution_type,
                                              resolution_code=resolution_code, worked=worked)

    def log_activity(self, summary: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._client.log_activity(summary, payload=payload)

    def send_event(self, event_type: str, title: str = "",
                   payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._client.send_event(event_type, title=title, payload=payload)

    def get_activity(self, limit: int = 20) -> Dict[str, Any]:
        return self._client.get_activity(limit=limit)

    def get_health(self) -> Dict[str, Any]:
        return self._client.get_health()
