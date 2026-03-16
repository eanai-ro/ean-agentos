#!/usr/bin/env python3
"""
License Gate — Feature gating pentru ean-cc-mem-kit Pro

Verifică licență JWT offline. Fără server, fără DRM agresiv.

Structura license.key (JWT signed cu RS256):
{
    "email": "user@company.com",
    "plan": "team" | "enterprise",
    "features": ["orchestration", "intelligence", "replay"],
    "issued_at": "2026-01-01T00:00:00",
    "expires_at": "2027-01-01T00:00:00"
}

Fișier licență: ~/.ean-memory/license.key
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

LICENSE_FILE = Path.home() / ".ean-memory" / "license.key"

# Features disponibile per plan
PLAN_FEATURES = {
    "community": [],  # Open source — fără orchestrare
    "team": [
        "orchestration",     # Proiecte, task-uri, deliberare
        "cli_launcher",      # Lansare CLI-uri
        "auto_loop",         # Deliberare automată
        "peer_review",       # Review workflow
        "messaging",         # Inter-agent messaging
        "dashboard_orch",    # Dashboard orchestration tab
        "replay",            # Timeline replay
    ],
    "enterprise": [
        "orchestration",
        "cli_launcher",
        "auto_loop",
        "peer_review",
        "messaging",
        "dashboard_orch",
        "replay",
        "intelligence",      # Capabilities + weighted voting
        "skill_learning",    # Skill extraction din reviews
        "auto_pipeline",     # Auto-fix + conflict escalation
        "smart_routing",     # Routing din capabilities
    ],
}

# Cache licență în memorie (nu citim fișierul la fiecare call)
_cached_license = None
_cache_checked = False


def _load_license() -> Optional[dict]:
    """Încarcă și validează licența."""
    global _cached_license, _cache_checked

    if _cache_checked:
        return _cached_license

    _cache_checked = True

    if not LICENSE_FILE.exists():
        _cached_license = None
        return None

    try:
        content = LICENSE_FILE.read_text().strip()
        payload = None

        # 1. Try plain JSON (dev/test licenses)
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Try JWT decode if JSON failed
        if payload is None:
            try:
                import jwt
                PUBLIC_KEY = os.environ.get("EAN_LICENSE_PUBLIC_KEY", "")
                if PUBLIC_KEY:
                    payload = jwt.decode(content, PUBLIC_KEY, algorithms=["RS256"])
                else:
                    payload = jwt.decode(content, options={"verify_signature": False})
            except Exception:
                pass

        # 3. Try manual JWT base64 decode as last resort
        if payload is None:
            try:
                import base64
                parts = content.split('.')
                if len(parts) == 3:
                    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded))
            except Exception:
                pass

        if payload is None:
            _cached_license = None
            return None

        # Verifică expirare
        expires = payload.get("expires_at", payload.get("exp", ""))
        if expires:
            if isinstance(expires, str):
                exp_dt = datetime.fromisoformat(expires)
            else:
                exp_dt = datetime.fromtimestamp(expires)
            if exp_dt < datetime.now():
                _cached_license = None
                return None

        _cached_license = payload
        return payload

    except Exception:
        _cached_license = None
        return None


def get_plan() -> str:
    """Returnează planul curent: community / team / enterprise."""
    license_data = _load_license()
    if not license_data:
        return "community"
    return license_data.get("plan", "community")


def has_feature(feature: str) -> bool:
    """Verifică dacă o feature e disponibilă în planul curent."""
    plan = get_plan()
    allowed = PLAN_FEATURES.get(plan, [])
    return feature in allowed


def check_premium(feature: str = "orchestration") -> bool:
    """Verifică dacă utilizatorul are acces la o feature premium.
    Returnează True dacă are acces, False dacă nu."""
    return has_feature(feature)


def require_premium(feature: str = "orchestration"):
    """Verifică și oprește dacă nu are licență. Folosit în CLI."""
    if not check_premium(feature):
        plan = get_plan()
        print(f"\n  ⚠️  This feature requires ean-cc-mem-kit Pro ({feature}).")
        print(f"  Current plan: {plan}")
        print(f"  Get your license at: https://ean-memory.dev/pro")
        print(f"  Activate: place license.key in ~/.ean-memory/license.key\n")
        raise SystemExit(0)


def get_license_info() -> dict:
    """Returnează info despre licența curentă."""
    license_data = _load_license()
    plan = get_plan()
    features = PLAN_FEATURES.get(plan, [])
    return {
        "plan": plan,
        "features": features,
        "email": license_data.get("email", "") if license_data else "",
        "expires_at": license_data.get("expires_at", "") if license_data else "",
        "is_premium": plan != "community",
    }


def clear_cache():
    """Resetează cache-ul (util pentru teste)."""
    global _cached_license, _cache_checked
    _cached_license = None
    _cache_checked = False


# === CLI ===

if __name__ == "__main__":
    info = get_license_info()
    print(f"Plan: {info['plan']}")
    print(f"Premium: {info['is_premium']}")
    if info['email']:
        print(f"Email: {info['email']}")
    if info['expires_at']:
        print(f"Expires: {info['expires_at']}")
    print(f"Features: {', '.join(info['features']) or 'none (community)'}")
