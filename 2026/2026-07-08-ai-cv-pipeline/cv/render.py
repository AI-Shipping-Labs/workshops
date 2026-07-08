# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""
Render cv.yml into a Harvard-format, print-ready HTML resume.

    uv run cv/render.py                 # reads cv/cv.yml -> writes cv/cv.html
    uv run cv/render.py --variant fde   # only entries tagged fde (or untagged)
    uv run cv/render.py in.yml out.html

The HTML is single-column, serif, black-on-white, and ATS-friendly.
Open it in Chrome -> Print -> Save as PDF (A4 or Letter) to get the document.
"""
from __future__ import annotations

import argparse
import html
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def visible(entry: dict, variant: str | None) -> bool:
    """An entry shows if no variant filter is set, the entry has no variant tag,
    or the entry's variant list contains the requested one."""
    if not variant:
        return True
    tag = entry.get("variant")
    if not tag:
        return True
    tags = [tag] if isinstance(tag, str) else list(tag)
    return variant in tags


# --------------------------------------------------------------------------- #
# Section renderers — each returns an HTML string (or "" to skip).
# --------------------------------------------------------------------------- #

def render_header(b: dict) -> str:
    links = []
    for ln in b.get("links", []):
        text, url = esc(ln.get("text", ln.get("url", ""))), ln.get("url")
        links.append(f'<a href="{esc(url)}">{text}</a>' if url else text)

    contact = [esc(b["location"])] if b.get("location") else []
    if b.get("email"):
        contact.append(f'<a href="mailto:{esc(b["email"])}">{esc(b["email"])}</a>')
    if b.get("phone"):
        contact.append(esc(b["phone"]))
    contact += links

    parts = [f'<h1>{esc(b["name"])}</h1>']
    if b.get("headline"):
        parts.append(f'<p class="headline">{esc(b["headline"])}</p>')
    parts.append('<p class="contact">' + ' <span>&bull;</span> '.join(contact) + '</p>')
    if b.get("note"):
        parts.append(f'<p class="note">{esc(b["note"])}</p>')
    return f'<header>{"".join(parts)}</header>'


def section(title: str, body: str) -> str:
    if not body.strip():
        return ""
    return f'<section><h2>{esc(title)}</h2>{body}</section>'


def render_summary(text: str) -> str:
    return section("Summary", f'<p class="summary">{esc(text)}</p>')


def render_skills(groups: list) -> str:
    rows = "".join(
        f'<div class="skill-row"><span class="skill-group">{esc(g["group"])}</span>'
        f'<span class="skill-items">{esc(", ".join(g["items"]))}</span></div>'
        for g in groups
    )
    return section("Skills", f'<div class="skills">{rows}</div>')


def _entry(title_left, title_right, sub_left, sub_right, bullets) -> str:
    def bl(bs):
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in bs) + "</ul>" if bs else ""
    head = (
        f'<div class="entry-head"><span class="left">{esc(title_left)}</span>'
        f'<span class="right">{esc(title_right)}</span></div>'
    )
    sub = ""
    if sub_left or sub_right:
        sub = (
            f'<div class="entry-sub"><span class="left">{esc(sub_left)}</span>'
            f'<span class="right">{esc(sub_right)}</span></div>'
        )
    return f'<div class="entry">{head}{sub}{bl(bullets)}</div>'


def render_experience(items: list, variant) -> str:
    body = "".join(
        _entry(e["company"], e.get("location", ""), e.get("title", ""),
               e.get("period", ""), e.get("bullets", []))
        for e in items if visible(e, variant)
    )
    return section("Experience", body)


def render_earlier(items: list) -> str:
    rows = "".join(
        f'<div class="earlier-row"><span class="left">'
        f'<strong>{esc(e["company"])}</strong> — {esc(e["role"])}</span>'
        f'<span class="right">{esc(e["period"])}</span></div>'
        f'<div class="earlier-stack">{esc(", ".join(e.get("stack", [])))}'
        f'{" · " + esc(e["location"]) if e.get("location") else ""}</div>'
        for e in items
    )
    return section("Earlier Experience", f'<div class="earlier">{rows}</div>')


def render_projects(items: list, variant) -> str:
    body = "".join(
        _entry(p["name"], "", "", "", p.get("bullets", []))
        for p in items if visible(p, variant)
    )
    return section("Selected AI Engineering Projects", body)


def render_education(items: list) -> str:
    body = "".join(
        _entry(e["degree"], e.get("period", ""), e.get("school", ""),
               "", [e["note"]] if e.get("note") else [])
        for e in items
    )
    return section("Education", body)


def render_certifications(items: list) -> str:
    """Optional. Each item is a string, or {name, issuer, year}."""
    if not items:
        return ""
    rows = []
    for c in items:
        if isinstance(c, str):
            rows.append(f'<div class="cert-row"><span class="left">{esc(c)}</span></div>')
            continue
        right = " · ".join(esc(c[k]) for k in ("issuer", "year") if c.get(k))
        rows.append(
            f'<div class="cert-row"><span class="left">{esc(c["name"])}</span>'
            f'<span class="right">{right}</span></div>'
        )
    return section("Certifications", "".join(rows))


def render_languages(items: list) -> str:
    """Optional. Each item is {name, level} (or a plain string)."""
    if not items:
        return ""
    parts = []
    for l in items:
        if isinstance(l, str):
            parts.append(esc(l))
        else:
            lvl = f' <span class="lang-level">({esc(l["level"])})</span>' if l.get("level") else ""
            parts.append(f'{esc(l["name"])}{lvl}')
    return section("Languages", '<p class="languages">' + " <span>&bull;</span> ".join(parts) + "</p>")


def render_recognition(rec: dict) -> str:
    parts = []
    for bk in rec.get("books", []):
        label = f'{bk["title"]} ({bk.get("publisher","")}, {bk.get("year","")})'
        link = f'<a href="{esc(bk["url"])}">{esc(label)}</a>' if bk.get("url") else esc(label)
        parts.append(f"<li>{link}</li>")
    for h in rec.get("highlights", []):
        parts.append(f"<li>{esc(h)}</li>")
    body = f"<ul>{''.join(parts)}</ul>" if parts else ""
    return section("Publications & Recognition", body)


# --------------------------------------------------------------------------- #

def build_html(cv: dict, variant: str | None, fragment: bool = False) -> str:
    b = cv["basics"]
    body = "".join([
        render_header(b),
        render_summary(b["summary"]) if b.get("summary") else "",
        render_skills(cv.get("skills", [])),
        render_experience(cv.get("experience", []), variant),
        render_projects(cv.get("projects", []), variant),
        render_earlier(cv.get("experience_earlier", [])),
        render_education(cv.get("education", [])),
        render_certifications(cv.get("certifications", [])),
        render_languages(cv.get("languages", [])),
        render_recognition(cv.get("recognition", {})),
    ])
    page_class = "page compact" if b.get("density") == "compact" else "page"
    inner = f'<style>{CSS}</style>\n<main class="{page_class}">\n{body}\n</main>'
    if fragment:  # for hosting as an Artifact (skeleton is supplied at publish time)
        return inner
    title = f'{b["name"]} — CV'
    return HTML_SHELL.format(title=esc(title), css=CSS, body=body, page_class=page_class)


HTML_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main class="{page_class}">
{body}
</main>
</body>
</html>
"""

# Harvard-flavored: serif, black-on-white, ruled section headers, tight spacing.
CSS = r"""
:root {
  --ink: #111;
  --muted: #444;
  --rule: #111;
  --accent: #111;
  --max: 800px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ececec; color: var(--ink); }
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 10.5pt;
  line-height: 1.34;
}
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }

.page {
  max-width: var(--max);
  margin: 24px auto;
  background: #fff;
  padding: 40px 48px;
  box-shadow: 0 1px 8px rgba(0,0,0,.15);
}

/* Header */
header { text-align: center; margin-bottom: 12px; }
h1 {
  font-size: 22pt; margin: 0 0 2px; letter-spacing: .5px;
  font-weight: 700;
}
.headline { margin: 2px 0 5px; font-size: 11pt; color: var(--muted); font-style: italic; }
.contact { margin: 0; font-size: 9.5pt; color: var(--muted); }
.contact span { color: #999; padding: 0 2px; }
.note { margin: 3px 0 0; font-size: 9.5pt; color: var(--muted); }

/* Sections */
section { margin-top: 13px; }
h2 {
  font-size: 11pt; text-transform: uppercase; letter-spacing: 1.2px;
  font-weight: 700; margin: 0 0 6px;
  border-bottom: 1.3px solid var(--rule); padding-bottom: 2px;
  break-after: avoid; page-break-after: avoid;
}
p.summary { margin: 0; text-align: justify; }

/* Entries (experience / projects / education) */
.entry { margin-bottom: 9px; page-break-inside: avoid; }
.entry:last-child { margin-bottom: 0; }
.entry-head, .entry-sub, .earlier-row {
  display: flex; justify-content: space-between; gap: 12px;
}
.entry-head .left { font-weight: 700; }
.entry-head .right { font-weight: 400; color: var(--muted); white-space: nowrap; }
.entry-sub { margin-top: 0; }
.entry-sub .left { font-style: italic; }
.entry-sub .right { color: var(--muted); white-space: nowrap; }

ul { margin: 4px 0 0; padding-left: 18px; }
li { margin: 1.5px 0; }

/* Skills */
.skill-row { display: flex; gap: 10px; margin: 2px 0; }
.skill-group { flex: 0 0 155px; font-weight: 700; }
.skill-items { flex: 1; }

/* Certifications */
.cert-row {
  display: flex; justify-content: space-between; gap: 12px; margin: 2px 0;
}
.cert-row .left { font-weight: 700; }
.cert-row .right { color: var(--muted); white-space: nowrap; }

/* Languages */
p.languages { margin: 0; }
p.languages span { color: #999; padding: 0 2px; }
.lang-level { color: var(--muted); font-style: italic; }

/* Earlier experience compact rows */
.earlier-row { margin-top: 5px; }
.earlier-row .right { color: var(--muted); white-space: nowrap; }
.earlier-stack { color: var(--muted); font-size: 9pt; font-style: italic; margin-bottom: 2px; }

/* Compact density — pull a light early-career CV onto a single page. */
.compact { font-size: 10pt; line-height: 1.26; }
.compact section { margin-top: 7px; }
.compact h2 { margin-bottom: 4px; }
.compact .entry { margin-bottom: 6px; }
.compact ul { margin-top: 3px; }
.compact li { margin: 1px 0; }
.compact p.summary { text-align: left; }

/* Print / PDF */
@page { size: A4; margin: 13mm 15mm; }
@media print {
  html, body { background: #fff; }
  .page { max-width: none; margin: 0; padding: 0; box-shadow: none; }
  a { color: inherit; }
  section { page-break-inside: auto; }
}
"""


def resolve_paths(src: str | None, out: str | None) -> tuple[pathlib.Path, pathlib.Path]:
    """Infer input/output paths from a flexible, terse invocation:

        (no args)          -> cv.yml            -> cv.html   (in the renderer dir)
        <person>           -> <person>/cv.yml   -> <person>/cv.html
        <person>/cv.yml    -> that file         -> sibling  cv.html
        <src.yml> <out>    -> exactly as given
    """
    if src is None:
        return HERE / "cv.yml", HERE / "cv.html"
    sp = pathlib.Path(src)
    if sp.suffix in (".yml", ".yaml"):        # an explicit yaml path
        src_path = sp
    else:                                     # a person folder / shorthand
        src_path = sp / "cv.yml"
    out_path = pathlib.Path(out) if out else src_path.with_name("cv.html")
    return src_path, out_path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render a cv.yml -> Harvard-format cv.html.",
        epilog="Examples: `render.py <person>`  |  `render.py <person>/cv.yml`  |  "
               "`render.py <person>/cv.yml out.html --variant fde`",
    )
    ap.add_argument("src", nargs="?", help="a person folder (e.g. <person>) or a cv.yml path")
    ap.add_argument("out", nargs="?", help="output HTML path (default: cv.html beside the source)")
    ap.add_argument("--variant", choices=["applied-ai", "ai-platform", "fde"],
                    help="filter entries tagged with this variant")
    ap.add_argument("--fragment", action="store_true",
                    help="emit style+body only (no <html>/<head>/<body>), for Artifact hosting")
    args = ap.parse_args()

    src_path, out_path = resolve_paths(args.src, args.out)
    cv = yaml.safe_load(src_path.read_text(encoding="utf-8"))
    out = build_html(cv, args.variant, fragment=args.fragment)
    out_path.write_text(out, encoding="utf-8")
    print(f"Wrote {out_path} ({len(out):,} bytes)"
          + (f" [variant: {args.variant}]" if args.variant else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
