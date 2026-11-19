"""Reference list exports: BibTeX, RIS, CSV, APA 7, IEEE and an HTML reading list."""

import csv
import html
import io
import json
import os
import re
import urllib.parse

from .library import ascii_fold, norm_title

TYPE_BIB = {"article": "article", "review": "article", "preprint": "misc",
            "book-chapter": "incollection", "dissertation": "phdthesis",
            "book": "book"}
TYPE_RIS = {"article": "JOUR", "review": "JOUR", "preprint": "UNPB",
            "book-chapter": "CHAP", "dissertation": "THES", "book": "BOOK"}


def _split(name):
    """'Jane A. Smith' -> ('Smith', 'Jane A.')"""
    name = (name or "").strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        return last, first
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _initials(first):
    return " ".join(p[0] + "." for p in re.split(r"[\s\-]+", first) if p)


def _is_conf(p):
    return p.get("venue_type") == "conference" or re.search(
        r"conference|proceedings|symposium|workshop", p.get("venue") or "", re.I)


def cite_key(p, used):
    last = re.sub(r"[^A-Za-z]", "", ascii_fold(_split((p.get("authors") or ["anon"])[0])[0])) or "anon"
    word = next((w for w in re.findall(r"[A-Za-z]{4,}", ascii_fold(p.get("title") or ""))
                 if w.lower() not in {"with", "from", "that", "this", "using", "based", "towards"}), "paper")
    key = f"{last.lower()}{p.get('year') or ''}{word.lower()}"
    k, i = key, 1
    while k in used:
        k = key + chr(ord("a") + i)
        i += 1
    used.add(k)
    return k


def _bib_escape(s):
    return (s or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("&", "\\&")


def to_bibtex(papers):
    used, out = set(), []
    for p in papers:
        kind = "inproceedings" if _is_conf(p) and p.get("type") == "article" else TYPE_BIB.get(p.get("type"), "article")
        fields = [("title", "{" + _bib_escape(p.get("title")) + "}"),
                  ("author", _bib_escape(" and ".join(p.get("authors") or [])))]
        venue_field = {"article": "journal", "inproceedings": "booktitle",
                       "incollection": "booktitle"}.get(kind, "howpublished")
        if p.get("venue"):
            fields.append((venue_field, _bib_escape(p["venue"])))
        for f in ("year", "volume", "issue", "pages", "doi"):
            if p.get(f):
                fields.append(("number" if f == "issue" else f,
                               str(p[f]).replace("-", "--") if f == "pages" else str(p[f])))
        if p.get("publisher"):
            fields.append(("publisher", _bib_escape(p["publisher"])))
        url = p.get("oa_url") or p.get("landing_url")
        if url:
            fields.append(("url", url))
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
        out.append(f"@{kind}{{{cite_key(p, used)},\n{body}\n}}")
    return "\n\n".join(out) + "\n"


def to_ris(papers):
    out = []
    for p in papers:
        ty = "CPAPER" if _is_conf(p) and p.get("type") == "article" else TYPE_RIS.get(p.get("type"), "JOUR")
        lines = [f"TY  - {ty}", f"TI  - {p.get('title')}"]
        lines += [f"AU  - {'%s, %s' % _split(a) if ' ' in a else a}" for a in p.get("authors") or []]
        if p.get("year"):
            lines.append(f"PY  - {p['year']}")
        if p.get("date"):
            lines.append(f"DA  - {p['date'].replace('-', '/')}")
        if p.get("venue"):
            lines.append(f"T2  - {p['venue']}")
        for tag, f in (("VL", "volume"), ("IS", "issue"), ("PB", "publisher"), ("DO", "doi")):
            if p.get(f):
                lines.append(f"{tag}  - {p[f]}")
        if p.get("pages"):
            sp, _, ep = str(p["pages"]).partition("-")
            lines.append(f"SP  - {sp}")
            if ep:
                lines.append(f"EP  - {ep}")
        if p.get("landing_url"):
            lines.append(f"UR  - {p['landing_url']}")
        if p.get("abstract"):
            lines.append(f"AB  - {p['abstract']}")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


CSV_COLS = ["No", "Title", "Authors", "Year", "Venue", "Publisher", "Type",
            "Open Access", "Citations", "Volume", "Issue", "Pages", "DOI",
            "Link", "Saved PDF", "Abstract"]


def to_csv(papers):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for i, p in enumerate(papers, 1):
        w.writerow([i, p.get("title"), "; ".join(p.get("authors") or []), p.get("year"),
                    p.get("venue"), p.get("publisher"), p.get("type"), p.get("oa_status"),
                    p.get("cited_by"), p.get("volume"), p.get("issue"), p.get("pages"),
                    p.get("doi"), p.get("landing_url"), p.get("file") or "",
                    p.get("abstract")])
    return "﻿" + buf.getvalue()   # BOM so Excel opens UTF-8 correctly


def apa(p):
    names = []
    for a in (p.get("authors") or [])[:20]:
        last, first = _split(a)
        names.append(f"{last}, {_initials(first)}".strip(", "))
    if len(names) > 1:
        auth = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        auth = names[0] if names else (p.get("venue") or "Anonymous")
    s = f"{auth} ({p.get('year') or 'n.d.'}). {p.get('title')}."
    if p.get("venue"):
        s += f" {p['venue']}"
        if p.get("volume"):
            s += f", {p['volume']}"
            if p.get("issue"):
                s += f"({p['issue']})"
        if p.get("pages"):
            s += f", {p['pages']}"
        s += "."
    if p.get("doi"):
        s += f" https://doi.org/{p['doi']}"
    return s


def ieee(p, n):
    names = []
    for a in p.get("authors") or []:
        last, first = _split(a)
        names.append(f"{_initials(first)} {last}".strip())
    if len(names) > 6:
        auth = names[0] + " et al."
    elif len(names) > 1:
        auth = ", ".join(names[:-1]) + ", and " + names[-1]
    else:
        auth = names[0] if names else ""
    s = f"[{n}] {auth}, “{p.get('title')},”"
    if p.get("venue"):
        s += f" {'in ' if _is_conf(p) else ''}{p['venue']},"
    if p.get("volume"):
        s += f" vol. {p['volume']},"
    if p.get("issue"):
        s += f" no. {p['issue']},"
    if p.get("pages"):
        s += f" pp. {p['pages']},"
    s += f" {p.get('year') or 'n.d.'}"
    if p.get("doi"):
        s += f", doi: {p['doi']}"
    return s + "."


def to_apa(papers):
    def sort_key(p):
        first = (p.get("authors") or [""])[0]
        return ascii_fold(_split(first)[0] if first else (p.get("title") or "")).lower()
    return "\n\n".join(apa(p) for p in sorted(papers, key=sort_key)) + "\n"


def to_ieee(papers):
    return "\n".join(ieee(p, i) for i, p in enumerate(papers, 1)) + "\n"


def to_html(topic, papers):
    rows = []
    for i, p in enumerate(papers, 1):
        links = []
        if p.get("file") and "::" in p["file"]:
            zip_name = p["file"].split("::")[0].replace("\\", "/").split("/")[-1]
            links.append("<span>In " + html.escape(zip_name) + "</span>")
        elif p.get("file"):
            href = "/".join(urllib.parse.quote(part) for part in re.split(r"[\\/]", p["file"]))
            links.append(f'<a href="{html.escape(href)}">Open PDF</a>')
        if p.get("landing_url"):
            links.append(f'<a href="{html.escape(p["landing_url"])}" target="_blank">Publisher page</a>')
        if not p.get("file") and p.get("oa_url"):
            links.append(f'<a href="{html.escape(p["oa_url"])}" target="_blank">Free copy</a>')
        badge = "saved" if p.get("file") else ("oa" if p.get("is_oa") else "closed")
        label = {"saved": "PDF saved", "oa": "Open access", "closed": "Subscription"}[badge]
        rows.append(f"""<li><div class="t">{html.escape(p.get('title') or '')}</div>
<div class="m">{html.escape('; '.join((p.get('authors') or [])[:6]))}{' et al.' if len(p.get('authors') or []) > 6 else ''}
 &middot; {html.escape(str(p.get('year') or ''))} &middot; <i>{html.escape(p.get('venue') or '')}</i>
 &middot; {p.get('cited_by') or 0} citations <span class="b {badge}">{label}</span></div>
<div class="l">{' &middot; '.join(links)}</div></li>""")
    return f"""<!doctype html><meta charset="utf-8"><title>{html.escape(topic)} - reading list</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#1d2433}}
h1{{font-size:22px}}li{{margin:0 0 14px}}.t{{font-weight:600}}.m{{color:#556}}.l a{{color:#2457d6;margin-right:4px}}
.b{{font-size:11px;padding:1px 7px;border-radius:9px;margin-left:6px}}.saved{{background:#dcf5e3;color:#11632d}}
.oa{{background:#e3ecff;color:#1f45a8}}.closed{{background:#f1f1f1;color:#555}}</style>
<h1>{html.escape(topic)}</h1><p>{len(papers)} references, generated by OpenShelf.</p><ol>{''.join(rows)}</ol>"""


EXPORTERS = {
    "bib": ("references.bib", to_bibtex),
    "ris": ("references.ris", to_ris),
    "csv": ("references.csv", to_csv),
    "apa": ("References (APA 7).txt", to_apa),
    "ieee": ("References (IEEE).txt", to_ieee),
}


def merge_and_write(folder, topic, new_papers):
    """Merge new references into the folder's list (no duplicates) and rewrite
    every export file. Returns the merged list."""
    meta = os.path.join(folder, "references.json")
    existing = []
    if os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                existing = json.load(f)
        except (OSError, ValueError):
            existing = []

    def key(p):
        return (p.get("doi") or "").lower() or norm_title(p.get("title"))

    index = {key(p): i for i, p in enumerate(existing)}
    for p in new_papers:
        k = key(p)
        if k in index:
            old = existing[index[k]]
            if p.get("file") and not old.get("file"):
                old["file"] = p["file"]
        else:
            index[k] = len(existing)
            existing.append(dict(p))
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=1, ensure_ascii=False)
    for fname, fn in EXPORTERS.values():
        with open(os.path.join(folder, fname), "w", encoding="utf-8", newline="") as f:
            f.write(fn(existing))
    with open(os.path.join(folder, "Reading list.html"), "w", encoding="utf-8") as f:
        f.write(to_html(topic, existing))
    return existing
