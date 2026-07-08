# CV Build Playbook — turning any CV into a focused AI-engineering résumé

A repeatable process for taking **anyone's** raw/verbose CV and producing a
focused, truthful, Harvard-format **AI-engineering** résumé from a single
display-agnostic source. It bakes in every editorial correction as a **rule**, so
following it produces the target result directly, without the back-and-forth.

Works for any candidate archetype — senior IC, founder, career-switcher,
early-career, or someone returning from a gap. Where a rule flexes by archetype,
that's called out inline (see §8).

- **Source of truth:** `cv/<person>/cv.yml` — display-agnostic YAML, one folder per person.
- **Renderer (shared):** `cv/render.py` — `uv run render.py <person>/cv.yml <person>/cv.html` → print to PDF.
- **Target:** Applied / AI Engineer roles; end-to-end; **1–2 pages** (1 page for light/early-career histories, 2 max otherwise).

The repo keeps a worked example per person under `cv/<person>/` — look at a couple
to see how the rules land across different archetypes (senior vs. early-career).

---

## 1. Philosophy (why the result looks like it does)

1. **One display-agnostic source, many outputs.** Content lives in YAML. A small
   shared renderer turns it into a Harvard-format HTML page you print to PDF.
   Editing = change YAML, re-render. Never hand-edit the HTML.
2. **Three layers, three different jobs — and none of them lies.**
   - **Headline** = *positioning / expertise* — what you offer the market. May be
     aspirational (AI-forward) as long as it's backed by real background.
   - **Role title** = *the literal truth of the job* — must be defensible if
     questioned in an interview.
   - **Bullets** = *the specifics* — where things are named concretely.
3. **Impact over mechanism.** Say what a thing achieves and what it is, not how it
   is wired. Leave low-level plumbing for the interview.
4. **Concise and truthful beats complete and impressive.** One or two pages, few
   focused groups, no jargon, no inflated titles.

---

## 2. The pipeline

```bash
# render one person (shared renderer, self-contained uv script — pulls pyyaml)
uv run render.py <person>                 # infers <person>/cv.yml -> <person>/cv.html

# optional role-specific variant (filters entries tagged with a variant)
uv run render.py <person> --variant fde

# make a PDF + confirm page count
chromium --headless --no-pdf-header-footer \
  --print-to-pdf=<person>/cv.pdf file://$PWD/<person>/cv.html
pdfinfo <person>/cv.pdf | grep Pages
```

**Layout:** each person or variant gets a folder (`cv/<person>/cv.yml` +
generated `cv.html`/`cv.pdf`). `render.py` is shared.

**Format:** single column, serif, black-on-white, ruled section headers, no photo,
no color, no columns → ATS-friendly and prints cleanly.

**Section order:** Header (name · headline · contact · optional note) → Summary →
Skills → Experience → Selected AI Engineering Projects → Earlier Experience →
Education → Certifications → Languages → Publications & Recognition.
*(All sections after Education are optional and render only if present.)*

---

## 3. Step-by-step algorithm

**Phase 0 — Inputs.** Gather the candidate's raw CV (and any positioning notes:
target role, work-authorization/location constraints, portfolio links). Decide the
single target — e.g. **Applied AI Engineer, end-to-end**.

**Phase 1 — Positioning.** Write the headline and summary first (§4). They set the
tone everything else must match.

**Phase 2 — Structure.** Copy the YAML skeleton (§6) into `cv/<person>/cv.yml`.
Reverse-chronological.

**Phase 3 — Fill each section by the rulebook (§5).** Titles → summary → skills →
experience bullets → projects → earlier experience → education → certs/languages.

**Phase 4 — Render & verify.** Render, print to PDF, confirm the page count, and
check no section header is orphaned at the foot of a page. If a light CV spills a
few lines onto a second page, use `density: compact` (§5.6) before cutting content.

**Phase 5 — Publish (optional).** Serve locally for review. Only publish CVs the
candidate has agreed to publish — keep other people's CVs and any private strategy
notes out of a public repo (see `.gitignore`).

---

## 4. Headline & summary (write these first)

**Headline** = `Target Role — crisp value phrase`.
- ✅ `Applied AI Engineer — End-to-End LLM Systems`
- ✅ `AI Product Engineer — End-to-End Production LLM Systems`
- ❌ Don't put a seniority *range* in the headline (`Senior / Staff …`) — it reads
  as self-assigned. Let scope and history carry seniority.

**Summary** = 3–4 lines: what you do end-to-end + impact + **credibility anchors**.
Anchors are whatever is true and strongest for this candidate:
- senior: years, founder status, prior senior role, scale;
- early-career/switcher: relevant foundation (degree/prior field), shipped
  projects, a concrete recent transition.
- ✅ (senior) "…I take AI ideas from raw form to production end-to-end. Founder of
  a large learner community; previously led an ML platform and production ML at a
  marketplace company."
- ✅ (early-career) "Applied AI engineer with a data-science and statistics
  foundation who turns business needs into deployable LLM systems … Backed by
  prior machine learning and computer vision delivery."
- ❌ **No technology lists** in the summary — no tool parenthetical like "(RAG,
  agents, evals, serverless…)". Focus on impact, not tools.
- ❌ Cut filler that doesn't earn its space.

---

## 5. The rulebook (every correction, as a reusable rule)

### 5.1 Titles & truthfulness — the highest-leverage rules
- **Never claim people leadership you don't have.** No `Lead` / `Head` / `Manager`
  without human reports. "Orchestrating AI agents" is *not* managing people.
- **Don't self-assign inflated IC ranks** (`Principal`/`Staff`) at your own
  company or on a portfolio project — it reads as puffery.
- **The role title must be literally true about the day-to-day.** If AI is only a
  slice of the work, don't title the role "AI Engineer" — use the honest title and
  let bullets surface the AI slice.
- **Reframe soft/support titles toward engineering.** "Community Manager" →
  lead with the build. A **career break / gap** is legitimate as an experience
  entry — title it for what you *did* ("Self-directed AI Engineering transition"),
  and reframe it toward the build, not the absence.

### 5.2 Skills — few, focused groups
- **3 groups maximum**, ordered by what the target role values most. For an
  applied-AI IC: **Applied AI / LLM** → **Evaluation & Monitoring** → **Platform &
  Data**. For a product-leaning role: **Product & Delivery** first.
- **Main technologies only** — drop granular/tiny items (individual cloud
  primitives, "model serving", "monitoring", "prompt chaining", "guardrails").
  Collapse near-duplicates (e.g. `Elasticsearch, Qdrant` → `vector databases`).
- **Cut buzzwords and laundry lists** — no "MLOps", no wall of one-word tags, no
  four-plus groups.
- **Keep detailed keywords in the bullets, not the skill lists** — that preserves
  ATS coverage without a tag wall.
- **Drop standalone soft-skill / "Personal skills" sections** ("self-driven",
  "team player", "critical thinking", "can-do attitude") — they add length, not
  signal, and read as filler. Cut the entire block.

### 5.3 Experience bullets — altitude and concision
- **~2–3 bullets per role. Merge overlapping ones.**
- **Convey breadth with examples, not a bullet per artifact.**
  - ✅ "Use AI across the business to automate operations — for example, a Slack
    FAQ assistant and internal tooling for recurring workflows."
  - ❌ One detailed bullet per app.
- **Don't over-specify deployment.** ✅ "…CI/CD, and deployment." ❌ "…serverless
  deployment, and usage/cost logging."
- **Remove throwaway abstract bullets** ("Treat the business as a live deployment
  environment…").
- **Consultants / agency roles: merge client sub-projects into capability-grouped
  bullets — never one bullet per customer.** Group by *what you did* (LLM/agents,
  data platforms, technical lead), not by client. (A consulting CV's many
  "Customer: …" sub-projects collapse into ~3 bullets.)
- **Metrics rule (archetype-dependent):** a concrete, quantified *achievement*
  earns its place — **keep it, especially early-career**, where a real number
  (`+20% detection accuracy`, `+41% mAP`) is the main proof of capability. Drop
  metrics only when they're noise, unverifiable, or when the richer detail is
  better saved for the interview. **But never invent one** (§5.7) — many consulting
  CVs have no hard numbers; there, lead with scope and ownership instead.

### 5.4 Projects — impact, clarity, no jargon
- **The Projects section is optional.** Feature it when a portfolio build is the
  centerpiece (typical early-career). **Omit it** when the AI work already lives
  under Experience (typical for consultants/employees) rather than duplicating the
  same builds in two places.
- **Merge related projects** into one entry.
- **Titles are plain, not padded.** ✅ `Slack FAQ Assistant`, `Podcast Q&A Agent`.
  ❌ Drop "Production", "native", buzz-suffixes.
- **Describe at capability/outcome altitude; skip implementation minutiae.**
  - ✅ "End-to-end agentic RAG system — ingests and transcribes podcast audio,
    retrieves relevant passages, and uses an LLM agent with tool calling to deliver
    grounded, cited answers through a Streamlit app."
  - ❌ "RSS ingestion → transcription → chunking → embeddings → vector
    search/retrieval → agent orchestration", "hit@k, MRR", "BM25 index",
    "managed dependencies with uv and validated with pytest". (Great *interview*
    material, not CV lines.)
- **No ambiguous jargon.** Replace terms that read differently at a glance
  ("closed-loop") with a concrete *source → what it updates → outcome* statement.
- **Only feature projects with real impact or direct relevance.** Exclude course
  exercises, abandoned repos, off-topic libraries — even popular ones.
- **Other/starred repos** go in a small de-emphasized mention at the end (social
  proof), never as a focal section.

### 5.5 GitHub / portfolio analysis (how to pick what to include)
```bash
gh api "users/<user>/repos?per_page=100&type=owner" --paginate \
  | jq -s 'add | map(select(.fork==false)) | sort_by(-.stargazers_count)'
# also sort by .pushed_at to separate current work from old code
```
Categorize into themes (AI/RAG apps, agent tooling, deployment, high-reach
content). **Select by impact + relevance, not star count alone.** For an
early-career candidate the single strongest end-to-end project usually beats a
list of small ones.

### 5.6 Formatting & technical gotchas
- **Page count:** 1 page for light/early-career histories, **2 max** otherwise.
  Verify by printing to PDF (`pdfinfo … | grep Pages`), not by eyeballing HTML.
- **Strip photos, headshots, and decorative graphics** from the source — the format
  is single-column, no-photo, no-color (also the safest for ATS parsing). Common in
  European CVs; drop them.
- **A few lines spilling onto a 2nd page?** Set `basics.density: compact` (drops
  the base font to 10pt and tightens vertical rhythm) *before* cutting real
  content. Trim summary filler and merge bullets next; shrink font last.
- **Fix orphaned section headers** (header alone at the foot of a page):
  `h2 { break-after: avoid; page-break-after: avoid; }` (already in the renderer).
- **YAML:** plain scalars can't contain `": "` — quote or reword ("hit@k",
  "CI/CD", "community through mentoring").
- **Renderer** is a self-contained `uv` PEP-723 script (declares `pyyaml`), so it
  runs with no project install.

### 5.7 Truthfulness floor — never fabricate
The résumé must survive an interview line by line, so **never invent facts to fill
a gap**:
- **Missing contact details** (e.g. a source with blank email/phone/LinkedIn):
  leave a clearly-marked placeholder in the YAML (commented `# TODO`) and **flag it
  to the candidate** — never guess an address. The header simply shows less until
  it's filled in.
- **Missing metrics:** see §5.3 — lead with scope/ownership, don't manufacture a
  number.
- **Dates, employers, titles, certifications:** transcribe exactly (keep a cert's
  validity/expiry as given). If the source is ambiguous, ask rather than assume.

---

## 6. YAML skeleton (the target structure)

```yaml
basics:
  name: ...
  headline: <Target Role> — <crisp value phrase>   # no seniority range
  location: ...
  email: ...
  note: ...            # optional — e.g. "No sponsorship needed" (work authorization)
  density: compact     # optional — only to pull a light CV onto one page
  links: [ {label, text, url}, ... ]
  summary: >-          # 3–4 lines, impact + credibility anchors, no tool list
    ...

skills:                                    # exactly 3 focused groups
  - {group: Applied AI / LLM,       items: [...]}
  - {group: Evaluation & Monitoring, items: [...]}
  - {group: Platform & Data,        items: [...]}

experience:                                # ~2–3 bullets each, merged/high-altitude
  - {company, title, location, period, bullets: [...]}

projects:                                  # only real impact / relevance
  - {name, bullets: [...]}                 # plain titles, capability-level, no minutiae

experience_earlier: [ ... ]                # compact one-liners for older/off-topic roles
education: [ ... ]
certifications:                            # optional — string or {name, issuer, year}
  - {name, issuer}
languages:                                 # optional — {name, level}
  - {name, level}
recognition:                               # optional — books, highlights, small OSS mention
  books: [...]
  highlights: [...]
```

Each `experience`/`project` entry may carry `variant: [applied-ai, ai-platform,
fde]` to appear only for that target role (untagged = always shown):
`uv run render.py <person>/cv.yml <person>/cv.html --variant fde`.

---

## 7. Candidate archetypes — how the rules flex

| Archetype | Headline anchor | Metrics (§5.3) | Length | Notes |
|---|---|---|---|---|
| Senior IC / founder | years, scale, prior senior role | often leave for interview | 2 pages | let history carry seniority |
| Career-switcher / early-career | prior-field foundation + recent transition | **keep concrete wins** — main proof | 1 page (`density: compact`) | frame gaps/breaks for what you *did* |
| Returning from a break | shipped project + upskilling | keep | 1 page | break is a titled experience entry, reframed toward the build |
| Consultant / agency | breadth of client delivery + recent AI builds | often none in source — **don't invent** | 1–2 pages | merge client sub-projects by capability, not per-client; Projects section usually omitted (§5.4) |

The rules in §5 are the same for everyone; only these dials move.

---

## 8. Before → after (worked examples)

| Element | Raw | Final | Rule |
|---|---|---|---|
| Title (founder) | Founder and Community Manager | **Founder & Product Engineer** | 5.1 |
| Title (returning break) | Career Break — Caregiving & AI Upskilling | **kept, retitled "Self-directed AI Engineering transition"**, reframed toward the build | 5.1 |
| Headline | verbose / role-only | `Target Role — crisp value phrase` | §4 |
| Summary | tech-heavy | impact-first, no tool list | §4 |
| Skills | 4–6 groups incl. buzzwords | **3 focused groups** | 5.2 |
| Project | metric/jargon-heavy, pipeline arrows | **one entry, capability-level, no minutiae** | 5.4 |
| Off-topic role | full entry | **compact one-liner in Earlier Experience** | 5.3 |
| Client work (consultant) | ~8 "Customer: …" sub-projects | **3 capability-grouped bullets**; Projects section omitted | 5.3 / 5.4 |
| Personal skills (consultant) | "self-driven, team player…" block | **cut entirely** | 5.2 |
| Contact (consultant) | blank email/phone in source | **placeholder + flagged, not invented** | 5.7 |
| Photo (consultant) | headshot in source | **removed** | 5.6 |
| Certs/Languages | scattered | dedicated optional sections | §6 |
| Length | multi-page | **1–2 pages, ATS-friendly** | 5.6 |
