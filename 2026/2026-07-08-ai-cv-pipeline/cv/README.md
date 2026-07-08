# CV — display-agnostic source + renderer

One source of truth per person (`<person>/cv.yml`) → clean, ATS-friendly,
Harvard-format HTML → PDF. One shared renderer builds every CV.

## Layout

| Path | Purpose |
|------|---------|
| `render.py` | Shared renderer. Turns a `cv.yml` into `cv.html` (self-contained `uv` script, no install needed). |
| `<person>/cv.yml` | **Edit this.** All of that person's content lives here — the display-agnostic representation. |
| `<person>/cv.html`, `<person>/cv.pdf` | Generated (git-ignored). **Do not edit by hand.** |

Each person or variant gets its own folder (e.g. `<person>/cv.yml`). Generated
HTML/PDF outputs and local work-in-progress CVs stay out of git (see
`.gitignore`).

## Workflow

```bash
# 1. edit <person>/cv.yml
# 2. re-render (shorthand: a person folder infers <person>/cv.yml -> <person>/cv.html)
uv run render.py <person>

# optional: role-specific variant (filters entries tagged with a variant)
uv run render.py <person> --variant fde

# 3. make a PDF (open the HTML in Chrome -> Print -> Save as PDF, A4)
#    or headless:
chromium --headless --no-pdf-header-footer \
  --print-to-pdf=<person>/cv.pdf file://$PWD/<person>/cv.html
```

## Conventions

- Keep bullets tight — the layout targets **2 pages** (1 page is fine for
  early-career CVs).
- Any experience/project entry may carry `variant: [applied-ai, ai-platform, fde]`
  to appear only for that target role. Untagged entries appear in every variant.
- Plain YAML scalars can't contain `": "` — quote such strings.

## Optional sections

All render only if present in the YAML (so they never affect a CV that omits them):

- `basics.note` — a short line under the contact row (e.g. "No sponsorship needed").
- `certifications:` — list of strings, or `{name, issuer, year}`.
- `languages:` — list of `{name, level}` (or plain strings).

See [`../CV-PROCESS.md`](../CV-PROCESS.md) for the full build playbook.
