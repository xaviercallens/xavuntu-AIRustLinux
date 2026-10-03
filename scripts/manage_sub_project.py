#!/usr/bin/env python3
"""
Sub-Project Manager for AutoevolveAI
Integrates with ANSE and the Antigravity Harness.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SUB_PROJECTS_DIR = ROOT_DIR / "sub_projects"
TEMPLATE_DIR = SUB_PROJECTS_DIR / "TEMPLATE"


def run_command(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"==> Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT_DIR)
    return result.returncode


def cmd_create(args: argparse.Namespace) -> int:
    name = args.name
    target_dir = SUB_PROJECTS_DIR / name

    if target_dir.exists():
        print(f"❌ Sub-project '{name}' already exists at {target_dir}")
        return 1

    print(f"==> Creating sub-project '{name}'...")
    shutil.copytree(TEMPLATE_DIR, target_dir)
    
    # Initialize basic python module structure
    (target_dir / "__init__.py").touch()
    
    print(f"✅ Sub-project '{name}' created at {target_dir}")
    print(f"   Contains 'formal/' directory for Lean 4 specifications.")
    print(f"   Contains '.pre-commit-config.yaml' for harness auditing.")
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    url = args.url
    default_name = Path(url.rstrip("/").removesuffix(".git")).name.replace("-", "_")
    name = args.name or default_name
    target_dir = SUB_PROJECTS_DIR / name

    if target_dir.exists():
        print(f"❌ Sub-project '{name}' already exists at {target_dir}")
        return 1

    print(f"==> Creating sub-project '{name}' from template...")
    shutil.copytree(TEMPLATE_DIR, target_dir)
    (target_dir / "__init__.py").touch()

    repo_name = args.repo_dir or Path(url.rstrip("/").removesuffix(".git")).name
    repo_dir = target_dir / repo_name
    print(f"==> Cloning repository from {url} into {repo_dir}...")
    res = run_command(["git", "clone", url, str(repo_dir)])
    if res != 0:
        print(f"❌ Failed to clone repository from {url}")
        return res

    print(f"✅ Sub-project '{name}' created and repository cloned at {repo_dir}")
    print(f"   Contains 'formal/' directory for Lean 4 specifications.")
    print(f"   Contains '.pre-commit-config.yaml' for harness auditing.")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    name = args.name
    target_dir = SUB_PROJECTS_DIR / name

    if not target_dir.exists():
        print(f"❌ Sub-project '{name}' does not exist.")
        return 1

    audit_path = target_dir / args.path if getattr(args, "path", None) else target_dir
    print(f"==> Auditing '{audit_path}' via Antigravity Harness...")
    cmd = [
        sys.executable, "-m", "antigravity_harness", "audit", str(audit_path), "--include-tests"
    ]
    return run_command(cmd)


def cmd_verify(args: argparse.Namespace) -> int:
    name = args.name
    target_dir = SUB_PROJECTS_DIR / name
    formal_dir = target_dir / "formal"

    if not formal_dir.exists():
        print(f"❌ Formal directory not found at {formal_dir}")
        return 1

    print(f"==> Verifying Lean 4 proofs for sub-project '{name}'...")
    cmd = [
        sys.executable, "-m", "antigravity_harness", "verify", "--formal-dir", str(formal_dir)
    ]
    return run_command(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="manage_sub_project",
        description="AutoevolveAI Sub-Project Manager integrating ANSE and Harness.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Scaffold a new sub-project")
    p_create.add_argument("name", help="Name of the sub-project")

    # clone / gitclone
    for cmd_alias in ("clone", "gitclone"):
        p_clone = subparsers.add_parser(cmd_alias, help="Scaffold a new sub-project and git clone a repo")
        p_clone.add_argument("url", help="Git URL to clone")
        p_clone.add_argument("name", nargs="?", default=None, help="Name of the sub-project (defaults to repo name)")
        p_clone.add_argument("--repo-dir", default=None, help="Target directory name inside sub-project")

    # audit
    p_audit = subparsers.add_parser("audit", help="Run harness audit on a sub-project")
    p_audit.add_argument("name", help="Name of the sub-project")
    p_audit.add_argument("--path", default=None, help="Relative path inside sub-project to audit")

    # verify
    p_verify = subparsers.add_parser("verify", help="Run Lean 4 verification on a sub-project")
    p_verify.add_argument("name", help="Name of the sub-project")

    args = parser.parse_args()

    if args.command == "create":
        return cmd_create(args)
    elif args.command in ("clone", "gitclone"):
        return cmd_clone(args)
    elif args.command == "audit":
        return cmd_audit(args)
    elif args.command == "verify":
        return cmd_verify(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
