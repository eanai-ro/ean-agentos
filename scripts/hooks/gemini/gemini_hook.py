#!/usr/bin/env python3
"""
Gemini CLI Hook Wrapper — Traducător payload Gemini → memory_daemon.py.

Gemini CLI trimite JSON pe stdin și CERE JSON valid pe stdout.
Acest script:
1. Citește payload-ul Gemini de pe stdin
2. Traduce câmpurile unde e necesar (tool names, keys)
3. Apelează memory_daemon.py cu handler-ul corect
4. Returnează {} pe stdout (obligatoriu pentru Gemini)

Utilizare (din settings.json):
    "command": "python3 /path/to/gemini_hook.py <handler>"

Unde <handler> este: session_start, user_prompt, pre_tool, post_tool,
                      assistant_response, session_end, pre_compact
"""

import sys
import os
import json
import subprocess
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent          # hooks/gemini/
HOOKS_DIR = SCRIPT_DIR.parent               # hooks/
PROJECT_ROOT = HOOKS_DIR.parent.parent      # ean-cc-mem-kit/
MEMORY_DAEMON = PROJECT_ROOT / "scripts" / "memory_daemon.py"

# Gemini tool names → Claude tool names (pentru compatibilitate cu daemon)
TOOL_NAME_MAP = {
    "replace": "Edit",
    "write_file": "Write",
    "read_file": "Read",
    "run_shell_command": "Bash",
    "glob": "Glob",
    "grep": "Grep",
    "ls": "LS",
    "search_files": "Grep",
    "list_directory": "LS",
}


def translate_tool_name(gemini_name: str) -> str:
    """Traduce tool name din format Gemini în format Claude."""
    return TOOL_NAME_MAP.get(gemini_name, gemini_name)


def translate_payload(handler: str, payload: dict) -> dict:
    """Traduce payload-ul Gemini în formatul așteptat de memory_daemon.py."""

    if handler == "user_prompt":
        # Gemini BeforeAgent: {"prompt": "...", "cwd": "..."}
        # Daemon: data.get('prompt', '') — deja compatibil!
        return payload

    elif handler == "assistant_response":
        # Gemini AfterAgent: {"prompt": "...", "prompt_response": "...", "cwd": "..."}
        # Daemon: data.get('response', '') sau data.get('prompt_response', '')
        result = dict(payload)
        # Copiază prompt_response în response (cheia pe care o caută daemon-ul)
        if "prompt_response" in result and "response" not in result:
            result["response"] = result["prompt_response"]
        return result

    elif handler in ("pre_tool", "post_tool"):
        # Gemini: {"tool_name": "write_file", "tool_input": {...}, ...}
        # Traducem tool names
        result = dict(payload)
        if "tool_name" in result:
            result["tool_name"] = translate_tool_name(result["tool_name"])

        # Gemini AfterTool include tool_response ca dict cu llmContent/returnDisplay
        if handler == "post_tool" and "tool_response" in result:
            resp = result["tool_response"]
            if isinstance(resp, dict):
                # Extrage conținutul util din formatul Gemini
                llm_content = resp.get("llmContent", resp.get("returnDisplay", ""))
                if isinstance(llm_content, list):
                    # Array de parts — concatenăm text-urile
                    texts = []
                    for part in llm_content:
                        if isinstance(part, dict) and "text" in part:
                            texts.append(part["text"])
                        elif isinstance(part, str):
                            texts.append(part)
                    llm_content = "\n".join(texts)
                result["tool_response"] = llm_content if isinstance(llm_content, str) else str(llm_content)

        return result

    # session_start, session_end, pre_compact — fără traducere necesară
    return payload


def main():
    if len(sys.argv) < 2:
        # Gemini expects JSON on stdout
        print("{}")
        return

    handler = sys.argv[1]

    # Citește payload Gemini din stdin
    payload = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                payload = json.loads(raw)
    except Exception:
        pass

    # Traduce payload
    translated = translate_payload(handler, payload)

    # Setează environment
    env = os.environ.copy()
    env["MEMORY_DIR"] = env.get("MEMORY_DIR", str(PROJECT_ROOT))

    # Apelează memory_daemon.py cu handler-ul tradus
    try:
        proc = subprocess.run(
            ["python3", str(MEMORY_DAEMON), handler],
            input=json.dumps(translated),
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        # Log stderr to daemon debug (nu pe stdout — ar rupe Gemini!)
        if proc.stderr:
            debug_log = Path(env["MEMORY_DIR"]) / "gemini_hook_debug.log"
            try:
                with open(debug_log, "a") as f:
                    f.write(f"[{handler}] stderr: {proc.stderr[:500]}\n")
            except Exception:
                pass
    except Exception as e:
        # Log error but don't break Gemini
        debug_log = Path(env.get("MEMORY_DIR", str(Path.home() / ".ean-memory"))) / "gemini_hook_debug.log"
        try:
            with open(debug_log, "a") as f:
                f.write(f"[{handler}] error: {e}\n")
        except Exception:
            pass

    # OBLIGATORIU: Gemini CLI așteaptă JSON valid pe stdout
    print("{}")


if __name__ == "__main__":
    main()
