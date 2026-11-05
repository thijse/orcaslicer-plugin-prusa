---
description: "Use when editing the Prusa tab's HTML, CSS or JavaScript (prusa_orca/ui/page_html.py): styling, dark mode, buttons, dialogs, page messages."
applyTo: "prusa_orca/ui/**"
---
# Prusa tab page

- The page is one string, `PAGES_HTML`, with inline CSS and an ES5-style IIFE. There's no build step and no framework: keep it plain DOM and `var` functions.
- Colours come from Orca's injected variables (`--orca-bg`, `--orca-fg`, `--orca-accent`, `--orca-border`, `--orca-muted`). The page's tokens copy Orca's dialog theme, with dark values under `:root[data-orca-theme="dark"]`. Use the tokens (`--bd`, `--btn-bg`, `--ok`, `--warn`, `--danger`, ...) instead of hex colours, and check both themes.
- Buttons are grey by default. Add `class="primary"` for the one main action in an area and `class="danger"` for destructive actions.
- Talk to Python only with `post({ command: '...' })`, and handle replies in the `m.type === '...'` dispatch. Every new command needs a handler in `prusa_orca/app/pages/` (`tests/test_app_wiring.py` checks it).
- Put any text that comes from the printer or the user into the page with `textContent`, never with `innerHTML`.
- Long work shows through the busy bar automatically (Python tasks). Lock the button for that work by adding its resource to `LOCKS`.
- The page can't open native dialogs other than `confirm`/`alert`. Use the `#wiz`-style overlay pattern for multi-step flows.
