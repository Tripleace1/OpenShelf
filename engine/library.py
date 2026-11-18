"""The local paper library: topic folders, file naming and duplicate tracking.

Every saved paper is recorded in  <papers root>/.openshelf-library.json  keyed
by DOI, OpenAlex ID and normalised title, so the same paper is never downloaded
twice - not even into a different topic folder. If you delete a PDF by hand,
OpenShelf notices the file is gone and will download it again next time.
"""

import datetime as dt
import json
import os
import re
import threading
import unicodedata

LIB_FILE = ".openshelf-library.json"
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}

NAMING = {
    "year_author_title": "2024 - Smith et al - Paper title.pdf",
    "author_year_title": "Smith 2024 - Paper title.pdf",
    "numbered": "001 - 2024 - Paper title.pdf",
    "title": "Paper title.pdf",
    "doi": "10.3390_drones7040245.pdf",
}


def ascii_fold(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def safe_name(text, limit=120):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = ascii_fold(text)
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", text)
    text = re.sub(r"[^A-Za-z0-9 .,&()'_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].strip(" .,")
    if text.upper() in _RESERVED:
        text = "_" + text
    return text or "Untitled"


def folder_name(topic):
    return safe_name(topic, 80)


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", ascii_fold(t).lower())[:200]


def first_author_surname(authors):
    if not authors:
        return "Unknown"
    name = ascii_fold(authors[0]).strip()
    if "," in name:
        sur = name.split(",")[0]
    else:
        sur = name.split()[-1] if name.split() else "Unknown"
    sur = safe_name(sur, 40)
    return sur + (" et al" if len(authors) > 2 else (" & " + safe_name(
        (ascii_fold(authors[1]).split() or ["?"])[-1], 40) if len(authors) == 2 else ""))


def make_filename(paper, pattern, number=1):
    year = str(paper.get("year") or "n.d.")
    title = safe_name(paper.get("title"), 110)
    if pattern == "author_year_title":
        base = f"{first_author_surname(paper.get('authors'))} {year} - {title}"
    elif pattern == "numbered":
        base = f"{number:03d} - {year} - {title}"
    elif pattern == "title":
        base = title
    elif pattern == "doi" and paper.get("doi"):
        base = safe_name(paper["doi"].replace("/", "_"), 120)
    else:
        base = f"{year} - {first_author_surname(paper.get('authors'))} - {title}"
    return base[:150].rstrip(" .-") + ".pdf"


class Library:
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        self.path = os.path.join(root, LIB_FILE)
        self.data = {"papers": {}}
        self._load()

    # ------------------------------------------------------------ storage
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
            self.data.setdefault("papers", {})
        except (OSError, ValueError):
            self.data = {"papers": {}}

    def _save(self):
        os.makedirs(self.root, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    @staticmethod
    def keys_for(paper):
        keys = []
        if paper.get("doi"):
            keys.append("doi:" + paper["doi"].lower())
        if paper.get("id"):
            keys.append("oa:" + paper["id"])
        nt = norm_title(paper.get("title"))
        if len(nt) > 20:
            keys.append("t:" + nt)
        return keys

    # ------------------------------------------------------------ queries
    def find(self, paper):
        """Return the library entry if this paper is already saved on disk."""
        with self.lock:
            for k in self.keys_for(paper):
                e = self.data["papers"].get(k)
                if e and os.path.isfile(os.path.join(self.root, e["file"])):
                    return e
        return None

    def add(self, paper, abs_file, topic):
        rel = os.path.relpath(abs_file, self.root)
        entry = {"title": paper.get("title"), "doi": paper.get("doi"),
                 "id": paper.get("id"), "file": rel, "topic": topic,
                 "added": dt.datetime.now().isoformat(timespec="seconds")}
        with self.lock:
            for k in self.keys_for(paper):
                self.data["papers"][k] = entry
            self._save()
        return entry

    def topic_dir(self, topic):
        d = os.path.join(self.root, folder_name(topic))
        os.makedirs(d, exist_ok=True)
        return d

    def unique_path(self, folder, filename):
        base, ext = os.path.splitext(filename)
        path = os.path.join(folder, filename)
        i = 2
        while os.path.exists(path):
            path = os.path.join(folder, f"{base} ({i}){ext}")
            i += 1
        return path

    def next_number(self, folder):
        n = 0
        try:
            for f in os.listdir(folder):
                m = re.match(r"(\d{3,})\s", f)
                if m:
                    n = max(n, int(m.group(1)))
        except OSError:
            pass
        return n + 1

    def collections(self):
        out = []
        if not os.path.isdir(self.root):
            return out
        for name in sorted(os.listdir(self.root), key=str.lower):
            d = os.path.join(self.root, name)
            if not os.path.isdir(d) or name.startswith("."):
                continue
            files = os.listdir(d)
            pdfs = [f for f in files if f.lower().endswith(".pdf")]
            refs = 0
            meta = os.path.join(d, "references.json")
            if os.path.isfile(meta):
                try:
                    with open(meta, encoding="utf-8") as f:
                        refs = len(json.load(f))
                except (OSError, ValueError):
                    pass
            mtime = max([os.path.getmtime(os.path.join(d, f)) for f in files] or
                        [os.path.getmtime(d)])
            out.append({"name": name, "pdfs": len(pdfs), "references": refs,
                        "updated": dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")})
        out.sort(key=lambda c: c["updated"], reverse=True)
        return out

    def count(self):
        with self.lock:
            files = {e["file"] for e in self.data["papers"].values()}
        return sum(1 for f in files if os.path.isfile(os.path.join(self.root, f)))
