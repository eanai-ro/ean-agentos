#!/usr/bin/env python3
"""
Model Logger - Gestionare model/provider curent.

Comenzi:
    model_logger.py set <model_id> <provider>    Setează modelul curent
    model_logger.py show                         Afișează modelul curent
    model_logger.py clear                        Șterge modelul curent
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_current_model, set_current_model, clear_current_model,
    MODEL_FILE,
)


def cmd_set(args):
    """Setează modelul curent."""
    set_current_model(args.model_id, args.provider, args.agent)
    print(f"✅ Model setat: {args.model_id} ({args.provider})")
    if args.agent:
        print(f"   Agent: {args.agent}")
    print(f"   Fișier: {MODEL_FILE}")


def cmd_show(args):
    """Afișează modelul curent."""
    model_id, provider = get_current_model()

    if model_id == "unknown" and not MODEL_FILE.exists():
        print("\n  Niciun model setat.")
        print(f"  Setează cu: mem model set <model_id> <provider>")
        return

    print(f"\n  Model curent: {model_id}")
    print(f"  Provider:     {provider}")
    if MODEL_FILE.exists():
        import json
        try:
            data = json.loads(MODEL_FILE.read_text())
            if data.get("agent_name"):
                print(f"  Agent:        {data['agent_name']}")
            if data.get("set_at"):
                print(f"  Setat la:     {data['set_at'][:19]}")
        except (json.JSONDecodeError, OSError):
            pass
    print()


def cmd_clear(args):
    """Șterge modelul curent."""
    if MODEL_FILE.exists():
        clear_current_model()
        print("✅ Model șters.")
    else:
        print("⚠️  Niciun model setat.")


def main():
    parser = argparse.ArgumentParser(description="Gestionare model/provider curent")
    subparsers = parser.add_subparsers(dest="command")

    # SET
    set_p = subparsers.add_parser("set", help="Setează modelul curent")
    set_p.add_argument("model_id", help="ID model (ex: claude-opus-4-6, glm-5)")
    set_p.add_argument("provider", help="Provider (ex: anthropic, zai, qwen, local)")
    set_p.add_argument("--agent", help="Nume agent (opțional)")

    # SHOW
    subparsers.add_parser("show", help="Afișează modelul curent")

    # CLEAR
    subparsers.add_parser("clear", help="Șterge modelul curent")

    args = parser.parse_args()

    commands = {
        "set": cmd_set,
        "show": cmd_show,
        "clear": cmd_clear,
    }

    if args.command in commands:
        commands[args.command](args)
    elif args.command is None:
        cmd_show(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
