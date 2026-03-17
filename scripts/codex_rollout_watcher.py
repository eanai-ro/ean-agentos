#!/usr/bin/env python3
"""Codex CLI Rollout Watcher — monitorizeaza JSONL sessions pentru ean-cc-mem-kit."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = _PROJECT_ROOT / "codex_watcher_state.json"
MEMORY_DAEMON = _PROJECT_ROOT / "scripts" / "memory_daemon.py"
MEMORY_DIR = os.environ.get("MEMORY_DIR", str(_PROJECT_ROOT))

_CALL_LOOKUP: Dict[str, str] = {}
_CALL_LOOKUP_MAX = 10000


def log(message: str) -> None:
    print(f"[CODEX-WATCHER] {message}", file=sys.stderr, flush=True)


def find_jsonl_files() -> List[Path]:
    if not CODEX_SESSIONS_DIR.exists():
        return []
    files = [p for p in CODEX_SESSIONS_DIR.rglob("*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime)
    return files


def load_state() -> Dict:
    default = {
        "last_file": None,
        "offsets": {},
        "total_events": 0,
        "updated_at": None,
        "call_map": {},
    }
    if not STATE_FILE.exists():
        return default
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
        state = {**default, **data}
        if not isinstance(state.get("offsets"), dict):
            state["offsets"] = {}
        if not isinstance(state.get("call_map"), dict):
            state["call_map"] = {}
        return state
    except Exception as exc:
        log(f"state invalid ({STATE_FILE}): {exc}")
        return default


def save_state(state: Dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    tmp_path = STATE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(STATE_FILE)


def _extract_text_from_message_payload(payload: Dict) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if "text" in item and isinstance(item["text"], str):
                parts.append(item["text"])
            elif "message" in item and isinstance(item["message"], str):
                parts.append(item["message"])
        return "\n".join([p for p in parts if p])
    return ""


def _normalize_tool_input(arguments: object) -> Dict:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        raw = arguments.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except Exception:
            return {"raw": raw}
    if arguments is None:
        return {}
    return {"value": arguments}


def _remember_tool_call(call_id: str, tool_name: str) -> None:
    if not call_id:
        return
    _CALL_LOOKUP[call_id] = tool_name or "unknown"
    while len(_CALL_LOOKUP) > _CALL_LOOKUP_MAX:
        _CALL_LOOKUP.pop(next(iter(_CALL_LOOKUP)))


def parse_jsonl_line(line: str) -> Optional[Tuple[str, Dict]]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None

    rec_type = record.get("type")
    payload = record.get("payload", {})
    payload_type = payload.get("type") if isinstance(payload, dict) else None

    if rec_type == "session_meta":
        return "session_start", {"source": "codex_rollout", "session_meta": payload if isinstance(payload, dict) else {}}

    if rec_type == "event_msg" and payload_type == "user_message":
        prompt = payload.get("message", "") if isinstance(payload, dict) else ""
        if isinstance(prompt, str) and prompt.strip():
            return "user_prompt", {"prompt": prompt}
        return None

    if rec_type == "event_msg" and payload_type == "agent_message":
        response = payload.get("message", "") if isinstance(payload, dict) else ""
        if isinstance(response, str) and response.strip():
            return "assistant_response", {"response": response}
        return None

    if rec_type == "user_message":
        prompt = ""
        if isinstance(payload, dict):
            prompt = payload.get("message", "") or _extract_text_from_message_payload(payload)
        elif isinstance(record.get("message"), str):
            prompt = record.get("message", "")
        if prompt.strip():
            return "user_prompt", {"prompt": prompt}
        return None

    if rec_type in ("assistant_message", "agent_message"):
        response = ""
        if isinstance(payload, dict):
            response = payload.get("message", "") or _extract_text_from_message_payload(payload)
        elif isinstance(record.get("message"), str):
            response = record.get("message", "")
        if response.strip():
            return "assistant_response", {"response": response}
        return None

    # NOTE:
    # response_item.message often duplicates event_msg user/agent messages in Codex rollouts.
    # We prefer event_msg + top-level message events to avoid double-ingestion.

    if rec_type == "response_item" and payload_type == "function_call" and isinstance(payload, dict):
        tool_name = payload.get("name") or "unknown"
        call_id = payload.get("call_id") or ""
        tool_input = _normalize_tool_input(payload.get("arguments"))
        _remember_tool_call(call_id, tool_name)
        return "pre_tool", {"tool_name": tool_name, "tool_input": tool_input}

    if rec_type == "response_item" and payload_type == "function_call_output" and isinstance(payload, dict):
        call_id = payload.get("call_id") or ""
        tool_name = _CALL_LOOKUP.get(call_id, "unknown")
        tool_response = payload.get("output", "")
        if not isinstance(tool_response, str):
            tool_response = json.dumps(tool_response, ensure_ascii=False)
        return "post_tool", {"tool_name": tool_name, "tool_response": tool_response}

    return None


def _call_memory_daemon(handler_name: str, payload: Dict) -> bool:
    env = dict(os.environ)
    env["MEMORY_DIR"] = MEMORY_DIR
    env["MEMORY_CLI_NAME"] = "codex-cli"
    env["MEMORY_AGENT_NAME"] = "codex-cli"
    try:
        proc = subprocess.run(
            ["python3", str(MEMORY_DAEMON), handler_name],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
    except Exception as exc:
        log(f"daemon call failed ({handler_name}): {exc}")
        return False

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        log(f"daemon non-zero ({handler_name}) rc={proc.returncode} stderr={stderr[:200]} stdout={stdout[:200]}")
        return False
    return True


def process_file(path: Path, state: Dict) -> int:
    offsets = state.setdefault("offsets", {})
    key = str(path.resolve())
    start_offset = int(offsets.get(key, 0) or 0)
    processed_events = 0

    size = path.stat().st_size
    if start_offset > size:
        start_offset = 0

    with path.open("rb") as fh:
        fh.seek(start_offset)
        current_offset = start_offset

        while True:
            line_start = fh.tell()
            raw_line = fh.readline()
            if not raw_line:
                break

            if not raw_line.endswith(b"\n"):
                current_offset = line_start
                break

            current_offset = fh.tell()
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            parsed = parse_jsonl_line(line)
            if not parsed:
                continue

            handler_name, payload = parsed
            ok = _call_memory_daemon(handler_name, payload)
            if not ok:
                # Do not advance offset past a failed event; retry on next run.
                current_offset = line_start
                break
            processed_events += 1

    offsets[key] = current_offset
    state["last_file"] = key
    return processed_events


def run_once() -> int:
    state = load_state()
    _CALL_LOOKUP.clear()
    _CALL_LOOKUP.update({str(k): str(v) for k, v in state.get("call_map", {}).items()})

    files = find_jsonl_files()
    if not files:
        log(f"no JSONL files under {CODEX_SESSIONS_DIR}")
        return 0

    total_events = 0
    for path in files:
        try:
            events = process_file(path, state)
        except Exception as exc:
            log(f"process error ({path}): {exc}")
            continue
        if events:
            log(f"processed {events} events from {path}")
        total_events += events

    # Close stale sessions: files not modified in >60s
    _close_stale_sessions(state, files)

    state["total_events"] = int(state.get("total_events", 0) or 0) + total_events
    state["call_map"] = _CALL_LOOKUP
    save_state(state)
    return total_events


def _close_stale_sessions(state: Dict, current_files: List[Path]) -> None:
    """Close sessions whose JSONL files haven't been modified recently."""
    STALE_THRESHOLD = 60  # seconds
    closed_sessions = state.setdefault("closed_sessions", [])
    offsets = state.get("offsets", {})
    now = time.time()

    for path in current_files:
        key = str(path.resolve())
        # Skip files we haven't processed yet
        if int(offsets.get(key, 0) or 0) == 0:
            continue
        # Skip already closed
        if key in closed_sessions:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if now - mtime > STALE_THRESHOLD:
            log(f"closing stale session for {path.name}")
            _call_memory_daemon("session_end", {})
            closed_sessions.append(key)
            # Keep list bounded
            if len(closed_sessions) > 500:
                closed_sessions[:] = closed_sessions[-200:]


def run_watch(interval: int = 5) -> None:
    log(f"watch mode started; polling every {interval}s")
    while True:
        try:
            total = run_once()
            if total:
                log(f"run complete: {total} new events")
        except KeyboardInterrupt:
            log("watch stopped by user")
            break
        except Exception as exc:
            log(f"watch loop error: {exc}")
        time.sleep(interval)


def show_status() -> None:
    state = load_state()
    files = find_jsonl_files()
    offsets = state.get("offsets", {})
    non_zero_offsets = sum(1 for v in offsets.values() if int(v or 0) > 0)

    log("status")
    log(f"sessions_dir={CODEX_SESSIONS_DIR}")
    log(f"daemon={MEMORY_DAEMON}")
    log(f"state_file={STATE_FILE}")
    log(f"jsonl_files_found={len(files)}")
    log(f"tracked_files={len(offsets)}")
    log(f"tracked_files_with_offset>0={non_zero_offsets}")
    log(f"last_file={state.get('last_file')}")
    log(f"total_events={state.get('total_events', 0)}")
    log(f"updated_at={state.get('updated_at')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Codex CLI rollout watcher (incremental JSONL -> memory_daemon)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Proceseaza evenimentele noi si iese.")
    mode.add_argument("--watch", action="store_true", help="Ruleaza continuu (poll la 5 secunde).")
    mode.add_argument("--status", action="store_true", help="Afiseaza starea watcher-ului.")
    parser.add_argument("--interval", type=int, default=5, help="Interval watch in secunde (default 5).")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.once:
        total = run_once()
        log(f"once complete: {total} events")
        return

    run_watch(interval=max(1, args.interval))


if __name__ == "__main__":
    main()
