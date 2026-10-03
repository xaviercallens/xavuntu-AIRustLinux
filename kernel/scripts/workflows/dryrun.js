#!/usr/bin/env node
// Zero-token dry run of a Workflow script: mocks agent()/pipeline()/log(),
// executes the script's control flow, and reports every agent call with its
// model, effort and approximate prompt size (chars/4). Mock verifiers fail the
// first unit once so the escalation path is exercised.
// Usage: node scripts/workflows/dryrun.js .claude/workflows/runux-quickwins.js ['{"pilot":true}']
const fs = require('fs')
const [path, argJson] = process.argv.slice(2)
if (!path) { console.error('usage: dryrun.js <workflow.js> [argsJson]'); process.exit(2) }
const src = fs.readFileSync(path, 'utf8').replace('export const meta', 'const meta')
const calls = []
let failedOnce = false
global.args = argJson ? JSON.parse(argJson) : {}
global.log = (m) => console.log('LOG:', m)
global.budget = { total: null, spent: () => 0, remaining: () => Infinity }
global.phase = () => {}
global.agent = async (prompt, opts = {}) => {
  calls.push({ label: opts.label || '?', model: opts.model || 'inherit', effort: opts.effort || '-', tok: Math.round(prompt.length / 4) })
  const label = opts.label || ''
  if (/^(verify|reverify)/.test(label)) {
    if (!failedOnce && label.startsWith('verify')) { failedOnce = true; return { pass: false, errors: ['mock failure'] } }
    return { pass: true, partial: false, errors: [], pr_url: 'mock://pr/' + label }
  }
  return { crate: label.split(':')[1] || 'x', committed: true, base_sha: 'mock', unjustified: [] }
}
global.parallel = async (thunks) => Promise.all(thunks.map(t => t().catch(() => null)))
global.pipeline = async (items, ...stages) => Promise.all(items.map(async (it, i) => { let r; for (const s of stages) r = await s(r, it, i); return r }))
new Function('return (async () => {' + src + '\n})()')().then((res) => {
  console.log('\nresult totals:', JSON.stringify(res && res.totals))
  const by = {}
  for (const c of calls) { const k = c.model; by[k] = (by[k] || 0) + 1 }
  console.log(`agent calls: ${calls.length}  by model: ${JSON.stringify(by)}  prompt tokens total≈${calls.reduce((a, c) => a + c.tok, 0)}`)
  for (const c of calls) console.log(`  ${c.label.padEnd(24)} ${c.model.padEnd(7)} effort=${c.effort.padEnd(4)} prompt≈${c.tok}`)
}).catch((e) => { console.error('DRY RUN FAILED:', e); process.exit(1) })
