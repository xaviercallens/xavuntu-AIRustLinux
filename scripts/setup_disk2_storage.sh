#!/usr/bin/env bash
#
# Relocate bulk, non-tracked storage to the second disk.
#
# Scope is deliberately narrow. An earlier version of this script also moved
# results/, data/ and adapters/ and replaced them with symlinks. Those are
# git-TRACKED (402, 6 and 7 files); swapping a tracked directory for a symlink
# registers every file as deleted. This version touches only paths that git
# ignores, and refuses anything it finds tracked.
#
# Dry-run by default. Pass --apply to make changes.
#
# Disk facts at time of writing: / has 81G free, /mnt/disks/disk-socrateai-local-1
# has 203G free, and formal/.lake alone is 2.5G.

set -euo pipefail

DISK2="/mnt/disks/disk-socrateai-local-1"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$DISK2/AutoevolveAI"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

say() { printf '%s\n' "$*"; }
run() {
    if (( APPLY )); then
        "$@"
    else
        say "    [dry-run] $*"
    fi
}

say "=== disk 2 storage relocation ==="
say "  repo:  $REPO"
say "  disk2: $DISK2"
if (( APPLY )); then say "  mode:  APPLY"; else say "  mode:  DRY-RUN (pass --apply to execute)"; fi
say ""

if ! mountpoint -q "$DISK2"; then
    say "ERROR: $DISK2 is not a mountpoint." >&2
    exit 1
fi
if [[ ! -w "$DISK2" ]]; then
    say "ERROR: $DISK2 is not writable by $(id -un)." >&2
    exit 1
fi

say "free before:  /=$(df -h / | awk 'NR==2{print $4}')  disk2=$(df -h "$DISK2" | awk 'NR==2{print $4}')"
say ""

# Only paths git ignores may be relocated. Checked, not assumed.
RELOCATABLE=("formal/.lake")

for rel in "${RELOCATABLE[@]}"; do
    src="$REPO/$rel"
    say "-> $rel"

    if [[ -L "$src" ]]; then
        say "    already a symlink -> $(readlink "$src"); skipping"
        continue
    fi
    if [[ ! -e "$src" ]]; then
        say "    not present; nothing to move"
        continue
    fi

    tracked=$(cd "$REPO" && git ls-files "$rel" | wc -l)
    if (( tracked > 0 )); then
        say "    REFUSING: $rel has $tracked git-tracked file(s)." >&2
        say "    Relocating it would register them as deleted. Skipping." >&2
        continue
    fi

    dest="$STAGE/${rel//\//_}"
    say "    $(du -sh "$src" | cut -f1) -> $dest"
    run mkdir -p "$STAGE"
    run mv "$src" "$dest"
    run ln -s "$dest" "$src"
done

# Staging directories for lake artifacts and caches. These are new paths, so
# there is nothing to move and nothing to break.
say ""
say "-> staging directories"
for d in datalake models hf-cache; do
    say "    $STAGE/$d"
    run mkdir -p "$STAGE/$d"
done

say ""
say "free after:   /=$(df -h / | awk 'NR==2{print $4}')  disk2=$(df -h "$DISK2" | awk 'NR==2{print $4}')"
say ""
say "Point caches at disk 2 by exporting these (the systemd unit already sets OLLAMA_MODELS):"
say "  export HF_HOME=$STAGE/hf-cache"
say "  export ANSE_DATALAKE_STAGE=$STAGE/datalake"
say ""
if (( APPLY )); then
    say "Done. Verify with: ls -la $REPO/formal/.lake"
else
    say "No changes made. Re-run with --apply to execute."
fi
