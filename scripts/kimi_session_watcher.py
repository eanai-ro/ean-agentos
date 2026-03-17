#!/usr/bin/env python3
"""Kimi CLI Session Watcher — monitorizeaza wire.jsonl sessions pentru ean-cc-mem-kit."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


KIMI_SESSIONS_DIR = Path.home() / ".kimi" / "sessions"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = _PROJECT_ROOT / ".kimi_watcher_state.json"
MEMORY_DAEMON = _PROJECT_ROOT / "scripts" / "memory_daemon.py"
MEMORY_DIR = os.environ.get("MEMORY_DIR", str(_PROJECT_ROOT))

_CALL_LOOKUP: Dict[str, str] = {}
_CALL_LOOKUP_MAX = 10000


def log(message: str) -> None:
    print(f"[KIMI-WATCHER] {message}", file=sys.stderr, flush=True)


def find_jsonl_files() -> List[Path]:
    """Cauta wire.jsonl recursiv in ~/.kimi/sessions/<hash>/<uuid>/."""
    if not KIMI_SESSIONS_DIR.exists():
        return []
    files = [p for p in KIMI_SESSIONS_DIR.rglob("wire.jsonl") if p.is_file()]
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


def _extract_text(obj: object) -> str:
    """Extrage text din diverse formate de content (str, list of parts, dict)."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        parts = []
        for item in obj:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "message", "content"):
                    if key in item and isinstance(item[key], str):
                        parts.append(item[key])
                        break
        return "\n".join(p for p in parts if p)
    if isinstance(obj, dict):
        for key in ("text", "message", "content"):
            if key in obj and isinstance(obj[key], str):
                return obj[key]
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
            return parsed if isinstance(parsed, dict) else {"value": parsed}
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
    """Parseaza o linie wire.jsonl din Kimi CLI.

    Formate asteptate:
      {"type": "metadata", "protocol_version": "1.5"}
      {"timestamp": N, "message": {"type": "TurnBegin", "payload": {"user_input": "..."}}}
      {"timestamp": N, "message": {"type": "AssistantMessage", "payload": {"content": "..."}}}
      {"timestamp": N, "message": {"type": "ToolCall", "payload": {"name": "...", "arguments": ..., "call_id": "..."}}}
      {"timestamp": N, "message": {"type": "ToolResult", "payload": {"call_id": "...", "output": "..."}}}
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None

    # Metadata line — tratam ca session_start
    if record.get("type") == "metadata":
        return "session_start", {
            "source": "kimi_cli",
            "session_meta": {
                k: v for k, v in record.items() if k != "type"
            },
        }

    # Toate celelalte au structura {"timestamp": N, "message": {...}}
    message = record.get("message")
    if not isinstance(message, dict):
        return None

    msg_type = message.get("type", "")
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    # TurnBegin — user prompt
    if msg_type == "TurnBegin":
        prompt = payload.get("user_input", "")
        if not isinstance(prompt, str):
            prompt = _extract_text(prompt)
        if prompt.strip():
            return "user_prompt", {"prompt": prompt}
        return None

    # Assistant message / response
    if msg_type in ("AssistantMessage", "AssistantResponse", "TurnEnd"):
        content = payload.get("content", "") or payload.get("message", "")
        if not isinstance(content, str):
            content = _extract_text(content)
        if content.strip():
            return "assistant_response", {"response": content}
        return None

    # Tool call (pre_tool)
    if msg_type in ("ToolCall", "FunctionCall"):
        tool_name = payload.get("name") or payload.get("tool_name") or "unknown"
        call_id = payload.get("call_id") or payload.get("id") or ""
        tool_input = _normalize_tool_input(payload.get("arguments") or payload.get("input"))
        _remember_tool_call(call_id, tool_name)
        return "pre_tool", {"tool_name": tool_name, "tool_input": tool_input}

    # Tool result (post_tool)
    if msg_type in ("ToolResult", "FunctionCallOutput"):
        call_id = payload.get("call_id") or payload.get("id") or ""
        tool_name = _CALL_LOOKUP.get(call_id, "unknown")
        tool_response = payload.get("output", "")
        if not isinstance(tool_response, str):
            tool_response = json.dumps(tool_response, ensure_ascii=False)
        return "post_tool", {"tool_name": tool_name, "tool_response": tool_response}

    return None


def _call_memory_daemon(handler_name: str, payload: Dict) -> bool:
    env = dict(os.environ)
    env["MEMORY_DIR"] = MEMORY_DIR
    env["MEMORY_CLI_NAME"] = "kimi-cli"
    env["MEMORY_AGENT_NAME"] = "kimi-cli"
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
        log(f"no wire.jsonl files under {KIMI_SESSIONS_DIR}")
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

    state["total_events"] = int(state.get("total_events", 0) or 0) + total_events
    state["call_map"] = _CALL_LOOKUP
    save_state(state)
    return total_events


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
    log(f"sessions_dir={KIMI_SESSIONS_DIR}")
    log(f"daemon={MEMORY_DAEMON}")
    log(f"state_file={STATE_FILE}")
    log(f"wire_jsonl_files_found={len(files)}")
    log(f"tracked_files={len(offsets)}")
    log(f"tracked_files_with_offset>0={non_zero_offsets}")
    log(f"last_file={state.get('last_file')}")
    log(f"total_events={state.get('total_events', 0)}")
    log(f"updated_at={state.get('updated_at')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kimi CLI session watcher (incremental wire.jsonl -> memory_daemon)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Proceseaza evenimentele noi si iese.")
    mode.add_argument("--watch", action="store_true", help="Ruleaza continuu (poll).")
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
