export const meta = {
  name: 'runux-quickwins',
  description: 'Wave 1 RunuX hardening: SAFETY comments + static mut removal per crate; Haiku-first, independently verified, Sonnet only on failure',
  whenToUse: 'docs/roadmap/BUSINESS_CASE_PRIORITIZED_PLAN.md Wave 1. args: {pilot?: bool, units?: [...], open_pr?: bool}',
  phases: [
    { title: 'Fix (T1)', detail: 'one Haiku agent per crate, exact line list, small read windows', model: 'haiku' },
    { title: 'Verify', detail: 'independent Haiku runs scripts/check_unit.py; never edits; only it may push/PR', model: 'haiku' },
    { title: 'Escalate (T2)', detail: 'Sonnet, only for crates whose verification failed', model: 'sonnet' },
  ],
}

// Default work list: core-set crates, measured 2026-09-27 at main 2eca7d9 by
// scripts/rust_tools.py (unsafe blocks lacking a preceding SAFETY: comment, and
// `static mut` sites). Smallest first so a pilot run (args.pilot) is cheap.
// Regenerate before reuse -- line numbers drift as the tree changes.
const DEFAULT_UNITS = [
  {
    "crate": "vmalloc",
    "files": [
      "crates/vmalloc/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/vmalloc/src/lib.rs": [
        36
      ]
    },
    "static_mut_lines": {},
    "sites": 1
  },
  {
    "crate": "syscall_table",
    "files": [
      "crates/syscall_table/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/syscall_table/src/lib.rs": [
        295
      ]
    },
    "static_mut_lines": {
      "crates/syscall_table/src/lib.rs": [
        151
      ]
    },
    "sites": 2
  },
  {
    "crate": "netfilter",
    "files": [
      "crates/netfilter/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/netfilter/src/lib.rs": [
        476
      ]
    },
    "static_mut_lines": {
      "crates/netfilter/src/lib.rs": [
        481
      ]
    },
    "sites": 2
  },
  {
    "crate": "kernel_types",
    "files": [
      "crates/kernel_types/src/lib.rs",
      "crates/kernel_types/tests/integration_tests.rs"
    ],
    "unsafe_lines": {
      "crates/kernel_types/src/lib.rs": [
        912
      ],
      "crates/kernel_types/tests/integration_tests.rs": [
        73
      ]
    },
    "static_mut_lines": {
      "crates/kernel_types/src/lib.rs": [
        889,
        908
      ]
    },
    "sites": 4
  },
  {
    "crate": "immutable_logs",
    "files": [
      "crates/immutable_logs/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/immutable_logs/src/lib.rs": [
        325,
        448,
        449,
        461,
        462
      ]
    },
    "static_mut_lines": {},
    "sites": 5
  },
  {
    "crate": "ai_bridge",
    "files": [
      "crates/ai_bridge/src/lib.rs",
      "crates/ai_bridge/src/ring_buffer.rs"
    ],
    "unsafe_lines": {
      "crates/ai_bridge/src/lib.rs": [
        109,
        119,
        395,
        401,
        410,
        413,
        421,
        424,
        431,
        436,
        439,
        444,
        453,
        459,
        460,
        461
      ],
      "crates/ai_bridge/src/ring_buffer.rs": [
        90,
        124,
        145
      ]
    },
    "static_mut_lines": {},
    "sites": 19
  },
  {
    "crate": "page_alloc",
    "files": [
      "crates/page_alloc/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/page_alloc/src/lib.rs": [
        64,
        69,
        74,
        79,
        84,
        392,
        401,
        411,
        421,
        432,
        446,
        458,
        475,
        494,
        520,
        529,
        542,
        552,
        568,
        582,
        596,
        604,
        627,
        656,
        683,
        700,
        714,
        734,
        760,
        773
      ]
    },
    "static_mut_lines": {
      "crates/page_alloc/src/lib.rs": [
        35,
        161,
        162
      ]
    },
    "sites": 33
  },
  {
    "crate": "slab",
    "files": [
      "crates/slab/src/lib.rs"
    ],
    "unsafe_lines": {
      "crates/slab/src/lib.rs": [
        340,
        404,
        421,
        431,
        441,
        454,
        467,
        485,
        501,
        523,
        533,
        542,
        551,
        564,
        586,
        599,
        613,
        625,
        634,
        651,
        665,
        679,
        698,
        716,
        735,
        745,
        755,
        768,
        779,
        791,
        811,
        829,
        844,
        869,
        895,
        921,
        944,
        970,
        1010,
        1034,
        1059,
        1106
      ]
    },
    "static_mut_lines": {
      "crates/slab/src/lib.rs": [
        73,
        357,
        358
      ]
    },
    "sites": 45
  }
]

const units0 = Array.isArray(args && args.units) ? args.units : DEFAULT_UNITS
const units = (args && args.pilot) ? units0.slice(0, 2) : units0
const OPEN_PR = !(args && args.open_pr === false)
const TARGET = 'CARGO_TARGET_DIR=/tmp/runux_target'
const ATTR_COMMIT = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
const ATTR_PR = '🤖 Generated with [Claude Code](https://claude.com/claude-code)'

if (units.length < units0.length) log(`pilot mode: ${units.length}/${units0.length} crates (skipped: ${units0.slice(units.length).map(u => u.crate).join(', ')})`)

const FIX_SCHEMA = {
  type: 'object',
  properties: {
    crate: { type: 'string' }, branch: { type: 'string' }, worktree: { type: 'string' },
    base_sha: { type: 'string' }, committed: { type: 'boolean' },
    safety_added: { type: 'number' }, static_mut_removed: { type: 'number' },
    unjustified: { type: 'array', items: { type: 'object',
      properties: { file: { type: 'string' }, line: { type: 'number' }, reason: { type: 'string' } },
      required: ['file', 'line', 'reason'] } },
    note: { type: 'string' },
  },
  required: ['crate', 'committed', 'unjustified'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    pass: { type: 'boolean' }, partial: { type: 'boolean' },
    errors: { type: 'array', items: { type: 'string' } },
    diffstat: { type: 'string' }, pr_url: { type: 'string' },
  },
  required: ['pass', 'errors'],
}

const lineList = (m) => Object.entries(m).map(([f, ls]) => `${f}: ${ls.join(', ')}`).join('\n  ')
const fileArgs = (u) => u.files.map(f => `--file ${f}`).join(' ')
const hasStatic = (u) => Object.keys(u.static_mut_lines || {}).length > 0
const hasUnsafe = (u) => Object.keys(u.unsafe_lines || {}).length > 0

function fixPrompt(u) {
  const c = u.crate
  return `Harden Rust crate \`${c}\` in the RunuX repo (current dir). Edit ONLY: ${u.files.join(', ')}.

Each Bash call starts at the repo root and shell variables do not persist: prefix every command with \`cd /tmp/qw-${c} &&\`.
Setup (once):
  git fetch -q origin main && (git worktree add -q /tmp/qw-${c} -b qw/${c} origin/main || git worktree add -q /tmp/qw-${c} qw/${c})
  cd /tmp/qw-${c} && git merge-base HEAD origin/main     # record this as base_sha

Token rules: per file, handle ALL sites from A and B together in descending line order so the listed numbers stay valid; any new unsafe block you introduce also needs a SAFETY comment; read only ~25 lines around each site (e.g. sed -n 'A,Bp' FILE), never whole files.
${hasUnsafe(u) ? `
A) Add a \`// SAFETY:\` comment directly above each unsafe block at:
  ${lineList(u.unsafe_lines)}
  A SAFETY comment is a correctness claim. State the specific reason from the code: why each pointer is non-null, aligned and in bounds; why no aliasing &mut exists; why memory is initialized and alive. Never write generic text ("this is safe", "caller guarantees") without naming the guarantee and where it is enforced.
  If you cannot justify a block from the code, do NOT comment it; list it in "unjustified" with the reason. That is a valid result (possible UB for human review).` : ''}
${hasStatic(u) ? `
B) Replace each \`static mut\` at:
  ${lineList(u.static_mut_lines)}
  with a safe primitive, preserving behavior: core::sync::atomic::Atomic* for scalars; otherwise an UnsafeCell wrapper with a documented \`unsafe impl Sync\` (with its own SAFETY comment). No new dependencies.` : ''}

Forbidden: behavior or signature changes beyond (B); new allow(...), #[ignore], todo!, unimplemented!; editing other files; git push.
Self-check: cd /tmp/qw-${c} && ${TARGET} cargo check -q -p ${c}${hasStatic(u) ? ` && ${TARGET} cargo test -q -p ${c}` : ''}. Fix only errors you introduced.
Commit: cd /tmp/qw-${c} && git add ${u.files.join(' ')} && git commit -qm "harden(${c}): SAFETY comments${hasStatic(u) ? ', remove static mut' : ''}" -m "${ATTR_COMMIT}"
Return JSON: crate, branch "qw/${c}", worktree "/tmp/qw-${c}", base_sha (from setup), committed, counts, unjustified.`
}

function verifyPrompt(u, fix) {
  const c = u.crate
  const unj = (fix.unjustified || []).map(x => `${x.file}:${x.line} (${x.reason})`).join('; ') || 'none'
  return `You are an independent verifier for crate \`${c}\`. You did not write this change. Do NOT edit any file. Do not trust the fixer's report (including any base commit it claims); the base is always computed below from origin/main.

Each Bash call starts at the repo root; shell state does not persist. Run exactly:
  git worktree add -q --detach /tmp/qwv-${c} qw/${c}
${hasUnsafe(u) ? `  cd /tmp/qwv-${c} && ${TARGET} python3 scripts/check_unit.py --type unsafe_safety ${fileArgs(u)} --crate ${c} --base $(git merge-base HEAD origin/main)\n` : ''}${hasStatic(u) ? `  cd /tmp/qwv-${c} && ${TARGET} python3 scripts/check_unit.py --type static_mut ${fileArgs(u)} --crate ${c} --base $(git merge-base HEAD origin/main)\n` : ''}  cd /tmp/qwv-${c} && git diff --stat $(git merge-base HEAD origin/main)...HEAD

Decision:
- pass=true if every check_unit.py command exits 0.
- pass=true, partial=true if the ONLY failures are "lacks a preceding SAFETY: comment" at lines the fixer reported as unjustified: ${unj}
- otherwise pass=false; copy the exact failure lines into errors.
${OPEN_PR ? `If pass: cd /tmp/qwv-${c} && git push -q -u origin qw/${c}; then gh pr create --base main --head qw/${c} --title "harden(${c}): SAFETY comments${hasStatic(u) ? ' + static mut removal' : ''}" (append " (partial)" to the title if partial) with a body containing: the diffstat, the oracle output lines, and if partial a section "Possible UB, needs human review" listing each unjustified block and its reason. End the body with: ${ATTR_PR}` : 'Do not push or open a PR (open_pr=false).'}
Always finish with: git worktree remove --force /tmp/qwv-${c}
Return JSON: pass, partial, errors, diffstat, pr_url.`
}

function escalatePrompt(u, fix, ver) {
  const c = u.crate
  return `A faster model hardened crate \`${c}\` in worktree /tmp/qw-${c} (branch qw/${c}); an independent verifier rejected it. Continue in that worktree; do not recreate it. Edit ONLY: ${u.files.join(', ')}.

Verifier errors:
${(ver.errors || []).map(e => '- ' + e).join('\n') || '- (none reported)'}
Blocks the first pass could not justify:
${(fix.unjustified || []).map(x => `- ${x.file}:${x.line}: ${x.reason}`).join('\n') || '- none'}

Fix the errors. For each unjustified block: justify it with a specific SAFETY comment; or, if it is genuinely unsound, make the minimal code change that makes it sound and keep tests passing; or leave it uncommented and keep it in "unjustified" with a precise reason. Same rules as before: no allow(...), #[ignore], todo!, unimplemented!, no other files, no push.
Each Bash call starts at the repo root: prefix commands with \`cd /tmp/qw-${c} &&\`.
Self-check: cd /tmp/qw-${c} && ${TARGET} cargo check -q -p ${c}${hasStatic(u) ? ` && ${TARGET} cargo test -q -p ${c}` : ''}
Commit on top (never amend or reset): cd /tmp/qw-${c} && git commit -qam "harden(${c}): address verifier findings" -m "${ATTR_COMMIT}"
Return JSON per schema (crate, branch, worktree, base_sha, committed, counts, unjustified).`
}

const results = await pipeline(
  units,
  (_, u) => agent(fixPrompt(u), { label: `fix:${u.crate}`, phase: 'Fix (T1)', model: 'haiku', effort: 'low', schema: FIX_SCHEMA }),
  async (fix, u) => {
    if (!fix || !fix.committed) return { crate: u.crate, sites: u.sites, status: 'no_change', fix }
    const ver = await agent(verifyPrompt(u, fix), { label: `verify:${u.crate}`, phase: 'Verify', model: 'haiku', effort: 'low', schema: VERIFY_SCHEMA })
    return { crate: u.crate, sites: u.sites, fix, ver, tier: 'T1' }
  },
  async (r, u) => {
    if (r.status === 'no_change' || (r.ver && r.ver.pass)) return r
    log(`${u.crate}: verification failed at T1, escalating to Sonnet`)
    const fix2 = await agent(escalatePrompt(u, r.fix, r.ver || { errors: ['verifier returned nothing'] }), { label: `escalate:${u.crate}`, phase: 'Escalate (T2)', model: 'sonnet', schema: FIX_SCHEMA })
    if (!fix2 || !fix2.committed) return { ...r, tier: 'T1->T2', status: 'escalation_no_change' }
    const ver2 = await agent(verifyPrompt(u, { ...fix2, base_sha: fix2.base_sha || r.fix.base_sha }), { label: `reverify:${u.crate}`, phase: 'Verify', model: 'haiku', effort: 'low', schema: VERIFY_SCHEMA })
    return { crate: u.crate, sites: u.sites, fix: fix2, ver: ver2, tier: 'T1->T2' }
  },
)

const done = results.filter(Boolean)
const passed = done.filter(r => r.ver && r.ver.pass)
const unjustified = done.flatMap(r => (r.fix && r.fix.unjustified || []).map(x => ({ crate: r.crate, ...x })))
for (const r of done) log(`${r.crate}: ${r.ver ? (r.ver.pass ? (r.ver.partial ? 'PASS (partial)' : 'PASS') : 'FAIL') : r.status} tier=${r.tier || '-'} pr=${(r.ver && r.ver.pr_url) || 'none'}`)
log(`crates passed ${passed.length}/${units.length}; possible-UB blocks for human review: ${unjustified.length}`)

return {
  totals: { crates: units.length, passed: passed.length, partial: passed.filter(r => r.ver.partial).length,
            escalated: done.filter(r => r.tier === 'T1->T2').length, unjustified: unjustified.length },
  unjustified,
  results: done.map(r => ({ crate: r.crate, sites: r.sites, tier: r.tier || null, status: r.ver ? (r.ver.pass ? (r.ver.partial ? 'partial' : 'pass') : 'fail') : r.status,
                            pr_url: (r.ver && r.ver.pr_url) || null, errors: (r.ver && r.ver.errors) || [] })),
}
