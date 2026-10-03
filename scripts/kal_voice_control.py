#!/usr/bin/env bash
"""true" '''
exec uv run python "$0" "$@"
'''
"""
# scripts/kal_voice_control.py — Standalone CLI for KAL 9000 Voice Control

from __future__ import annotations

import argparse
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.voice.engine import KalVoiceEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="KAL 9000 Sovereign Voice Control CLI")
    subparsers = parser.add_subparsers(dest="command")

    speak_parser = subparsers.add_parser("speak", help="Synthesize and speak text")
    speak_parser.add_argument("text", type=str, help="Text for KAL 9000 to speak")
    speak_parser.add_argument("--play", action="store_true", help="Play audio immediately")

    cmd_parser = subparsers.add_parser("command", help="Execute voice command")
    cmd_parser.add_argument("query", type=str, help="Spoken command text")
    cmd_parser.add_argument("--play", action="store_true", help="Play voice response")

    subparsers.add_parser("test", help="Test KAL voice synthesis")

    args = parser.parse_args()
    engine = KalVoiceEngine()

    if args.command == "speak":
        path, dur = engine.synthesize_speech(args.text, play_live=args.play)
        print(f"✓ Synthétisé en {dur:.2f}s: {path}")
        return 0

    elif args.command == "command":
        res = engine.process_voice_command(args.query)
        print(f"Commande: {res.command_text}")
        print(f"Intention: {res.intent} (Action: {res.action_executed})")
        print(f"Réponse KAL: {res.response_speech}")
        if res.audio_path:
            print(f"Fichier Audio: {res.audio_path}")
            if args.play:
                engine.play_audio(res.audio_path)
        return 0

    elif args.command == "test" or args.command is None:
        greeting = "Bonjour Xavier. Je suis KAL 9000, le cerveau souverain de Xavuntu. Tous les systèmes sont nominaux."
        path, dur = engine.synthesize_speech(greeting, play_live=True)
        print(f"✓ KAL 9000 Voice Test ({dur:.2f}s): {path}")
        print(f"Texte: '{greeting}'")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
