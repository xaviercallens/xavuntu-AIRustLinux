# Wiki staging

GitHub Wikis can't be created via the API or a first `git push` — GitHub
requires one page to be created through the web UI first, after which
`https://github.com/xaviercallens/rust-linux-mini-kernel.wiki.git` becomes a
real, clonable/pushable repo. Until then, this content lives here so it's
tracked and versioned like everything else.

## To activate

1. Visit **Wiki** tab → **Create the first page** → paste `Home.md`'s
   content below (title it "Home") → Save.
2. Then push the rest in one step:
   ```bash
   git clone https://github.com/xaviercallens/rust-linux-mini-kernel.wiki.git /tmp/runux-wiki
   cp docs/wiki_staging/*.md /tmp/runux-wiki/   # except this README
   rm /tmp/runux-wiki/README.md
   cd /tmp/runux-wiki && git add -A && git commit -m "Add FAQ and Glossary" && git push
   ```

## Why these pages and not others

The wiki intentionally does **not** duplicate `README.md`, `CONTRIBUTING.md`,
or `ROADMAP.md` verbatim — that would create a second copy of the numbers
this project has spent real effort making accurate, which would drift out
of sync with the ratcheted, script-verified originals. The wiki holds
content that's genuinely additive: a living FAQ, and a glossary of the
project's own vocabulary (`core set`, `oracle`, `T1`/`T2` tier, `spec-defect`,
etc.) that newcomers hit immediately in issues and PRs but that doesn't
belong in the README's evidence tables.
