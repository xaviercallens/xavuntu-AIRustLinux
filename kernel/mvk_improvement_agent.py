#!/usr/bin/env python3
"""
MVK Improvement Agent - Autonomous Orchestrator

This script initializes an autonomous AI agent powered by the Google Antigravity SDK,
loaded with workspace-scoped skills for compilation auditing and Lean 4 spec verification,
to inspect, analyze, and optimize the Minimum Viable Kernel (MVK) codebase.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Try importing the Google Antigravity SDK
try:
    from google.antigravity import Agent, LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    print("Error: The 'google-antigravity' SDK is not installed or not in python path.", file=sys.stderr)
    print("Please install the SDK or ensure it is available in your active environment.", file=sys.stderr)
    sys.exit(1)

# Default paths
WORKSPACE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = WORKSPACE_DIR / "skills"
DEFAULT_APP_DATA_DIR = WORKSPACE_DIR / ".gemini" / "agent_workspace"


def parse_args():
    parser = argparse.ArgumentParser(
        description="MVK autonomous improvement agent powered by Google Antigravity SDK."
    )
    subparsers = parser.add_subparsers(dest="command", help="Agent execution commands")

    # dry-run subcommand
    subparsers.add_parser(
        "dry-run",
        help="Initialize the agent, verify configuration, and list loaded skills without starting a conversation."
    )

    # run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Start the agent with a specific query/task to analyze and improve the MVK code."
    )
    run_parser.add_argument(
        "--task",
        type=str,
        default="Inspect the MVK repository for any compile warnings or unproven Lean 4 stubs, and propose a concrete step to fix them.",
        help="The specific task prompt for the agent to run."
    )

    # interactive subcommand
    subparsers.add_parser(
        "interactive",
        help="Start an interactive chat loop with the MVK Improvement Agent in the terminal."
    )

    return parser.parse_args()


def get_agent_config() -> LocalAgentConfig:
    """Configures and returns the LocalAgentConfig with workspace skills and safe policies."""
    # Ensure app data directory exists
    app_data_dir = os.environ.get("GEMINI_APP_DATA_DIR", str(DEFAULT_APP_DATA_DIR))
    os.makedirs(app_data_dir, exist_ok=True)

    # Declarative safety policies: deny raw run_commands by default, allow standard workspace tools.
    # Restricts file operations to MVK workspace.
    policies = [
        policy.workspace_only([str(WORKSPACE_DIR)]),
        policy.confirm_run_command(),
    ]

    config = LocalAgentConfig(
        model="gemini-3.5-flash",  # Premium default model
        app_data_dir=app_data_dir,
        skills_paths=[str(SKILLS_DIR)],
        policies=policies,
        system_instructions=(
            "You are the MVK Improvement Agent, an elite systems engineering assistant "
            "specializing in idiomatic, FFI-compatible Rust and formal Lean 4 verification. "
            "Use your loaded 'kernel-compilation-audit' and 'lean4-spec-verification' skills "
            "to guide your audits, identify structure-packing errors, resolve Lean 4 stubs, "
            "and propose pristine no_std safety improvements."
        )
    )
    return config


async def run_dry_run():
    """Initializes the agent configuration and validates the environment setup."""
    print("=== [Dry-Run] Initializing MVK Improvement Agent ===")
    print(f"Workspace Directory: {WORKSPACE_DIR}")
    print(f"Skills Directory   : {SKILLS_DIR}")
    print(f"App Data Directory : {DEFAULT_APP_DATA_DIR}")

    # Initialize configuration
    config = get_agent_config()

    try:
        async with Agent(config) as agent:
            print("\n[Success] Antigravity Agent successfully initialized!")
            print(f"Conversation ID: {agent.conversation_id}")
            print("\nLoaded Custom Skills:")
            # List local workspace skills
            if SKILLS_DIR.exists():
                for skill_path in SKILLS_DIR.iterdir():
                    if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                        print(f" - {skill_path.name} (at {skill_path})")
            else:
                print("No skills directory found or skills path misconfigured.")
    except Exception as e:
        print(f"\n[Error] Agent initialization failed: {e}", file=sys.stderr)
        sys.exit(1)


async def run_task(task_prompt: str):
    """Runs a single conversation turn with a specific improvement task prompt."""
    config = get_agent_config()
    print(f"=== Starting Autonomous Task Turn ===")
    print(f"Prompt: {task_prompt}\n")

    async with Agent(config) as agent:
        response = await agent.chat(task_prompt)
        print("Agent Thoughts:")
        async for thought in response.thoughts:
            print(thought, end="", flush=True)
        print("\n\nAgent Output:")
        async for token in response:
            print(token, end="", flush=True)
        print()


async def run_interactive():
    """Starts the terminal interactive chat loop for direct human interaction."""
    config = get_agent_config()
    print("=== Starting MVK Agent Interactive Terminal Loop ===")
    async with Agent(config) as agent:
        await agent.run_interactive_loop()


def main():
    args = parse_args()

    if not args.command:
        # Default to dry-run if no command provided
        asyncio.run(run_dry_run())
    elif args.command == "dry-run":
        asyncio.run(run_dry_run())
    elif args.command == "run":
        asyncio.run(run_task(args.task))
    elif args.command == "interactive":
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
