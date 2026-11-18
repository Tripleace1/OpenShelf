#!/usr/bin/env python3
"""
OpenShelf - find, download and cite open access research papers.

    python openshelf.py          (Windows)
    python3 openshelf.py         (macOS / Linux)

Your browser opens a local page (nothing is hosted online, no login).
Only the Python standard library is used - nothing to install.

Based on PaperHarvest by Saka Adetayo Muhammed (MIT licence).
"""

import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if sys.version_info < (3, 8):
    sys.exit("OpenShelf needs Python 3.8 or newer. Get it from https://www.python.org/downloads/")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import fetch, refs                                 # noqa: E402
from engine.library import Library, NAMING, make_filename, folder_name  # noqa: E402
from engine.openalex import (PUBLISHERS, OA_STATUSES, Budget, Search,  # noqa: E402
                             SearchError)

VERSION = "1.0"
MAX_PAPERS = 100
WEB = os.path.join(HERE, "web")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
DEFAULT_SETTINGS = {
    "papers_dir": os.path.join(HERE, "Papers"),
    "naming": "year_author_title",
    "api_key": "",
    "email": "",
    "parallel": 3,
}

STATE_LOCK = threading.Lock()
SEARCHES = {}           # search_id -> {"search": Search, "opts": dict, "papers": {id: paper}}
JOB = {}
LIBRARY = None


# ------------------------------------------------------------------ settings
def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass
    return s


SETTINGS = load_settings()


def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(SETTINGS, f, indent=2)


def library():
    global LIBRARY
    root = os.path.abspath(os.path.expanduser(SETTINGS["papers_dir"]))
    if LIBRARY is None or LIBRARY.root != root:
        os.makedirs(root, exist_ok=True)
        LIBRARY = Library(root)
    return LIBRARY


def reset_job():
    JOB.clear()
    JOB.update(running=False, stop=False, finished=False, topic="", folder="",
               target=0, saved=0, dupes=0, failed=0, checked=0, log=[],
               status={}, manual=[], message="", started=None)


reset_job()


def log(msg, kind="info"):
    with STATE_LOCK:
        JOB["log"].append({"t": time.strftime("%H:%M:%S"), "msg": msg, "kind": kind})
        JOB["log"] = JOB["log"][-500:]


# ------------------------------------------------------------------ helpers
def clamp_int(v, lo, hi, default):
    try:
        return max(lo, min(int(v), hi))
    except (TypeError, ValueError):
        return default


def as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def parse_opts(body):
    year = dt.date.today().year
    y1 = clamp_int(body.get("year_from"), 1900, year + 1, None) if body.get("year_from") else None
    y2 = clamp_int(body.get("year_to"), 1900, year + 1, None) if body.get("year_to") else None
    return {
        "topic": (body.get("topic") or "").strip()[:200],
        "keywords": as_list(body.get("keywords"))[:20],
        "match": "all" if body.get("match") == "all" else "any",
        "exclude": as_list(body.get("exclude"))[:20],
        "search_in": body.get("search_in") if body.get("search_in") in ("title", "fulltext") else "title_abstract",
        "year_from": y1, "year_to": y2,
        "access": body.get("access") if body.get("access") in ("oa", "all", "closed") else "oa",
        "oa_status": [s for s in as_list(body.get("oa_status")) if s in OA_STATUSES],
        "doc_types": as_list(body.get("doc_types")),
        "venue_types": as_list(body.get("venue_types")),
        "publishers": as_list(body.get("publishers")),
        "quality": body.get("quality") if body.get("quality") in ("core", "high", "top") else "any",
        "language": "en" if body.get("language") == "en" else "",
        "min_citations": clamp_int(body.get("min_citations"), 0, 10**6, 0),
        "sort": body.get("sort") or "relevance",
        "limit": clamp_int(body.get("limit"), 1, MAX_PAPERS, 25),
    }


def annotate(paper):
    """Attach 'already in library' info to a result for the UI."""
    e = library().find(paper)
    p = dict(paper)
    p["in_library"] = {"topic": e.get("topic"), "file": e.get("file")} if e else None
    return p


def public(paper):
    p = dict(paper)
    p.pop("pdf_urls", None)
    p["has_pdf_link"] = bool(paper.get("pdf_urls") or paper.get("pmcid"))
    return p


def open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ------------------------------------------------------------------ download job
def run_download(search_id, ids, fill, topic, ref_ids=()):
    lib = library()
    entry = SEARCHES.get(search_id)
    folder = lib.topic_dir(topic)
    naming = SETTINGS.get("naming", "year_author_title")
    queue = [entry["papers"][i] for i in ids if i in entry["papers"]]
    target = len(queue)
    q_lock, done_papers = threading.Lock(), []
    budget = {"extra": max(target * 4, 20)}

    with STATE_LOCK:
        reset_job()
        JOB.update(running=True, topic=topic, folder=folder, target=target,
                   started=time.time())
    log(f"Saving to {folder}")
    log(f"Downloading {target} paper{'s' if target != 1 else ''} on \"{topic}\".")

    def next_paper():
        with q_lock:
            if JOB["stop"] or JOB["saved"] >= target:
                return None
            if queue:
                return queue.pop(0)
            if not fill or budget["extra"] <= 0:
                return None
            try:
                more = entry["search"].next_batch(10)
            except SearchError as e:
                log(str(e), "error")
                return None
            for p in more:
                entry["papers"][p["id"]] = p
            budget["extra"] -= len(more)
            if not more:
                return None
            log(f"Looking further down the results for replacements ({len(more)} more).")
            with STATE_LOCK:
                JOB.setdefault("added", []).extend(public(annotate(p)) for p in more)
            queue.extend(more[1:])
            return more[0]

    def set_status(pid, s):
        with STATE_LOCK:
            JOB["status"][pid] = s

    def work():
        while True:
            p = next_paper()
            if p is None:
                return
            with STATE_LOCK:
                JOB["checked"] += 1
            existing = lib.find(p)
            rec = dict(p)
            if existing:
                rec["file"] = os.path.relpath(os.path.join(lib.root, existing["file"]), folder)
                set_status(p["id"], "dupe")
                with STATE_LOCK:
                    JOB["dupes"] += 1
                log(f"Already have it ({existing.get('topic')}): {p['title'][:90]}", "dupe")
                done_papers.append(rec)
                continue
            set_status(p["id"], "downloading")
            data, src, why = fetch.download(p, SETTINGS, lambda: JOB["stop"])
            if data:
                with q_lock:
                    if JOB["saved"] >= target:       # another thread filled the quota
                        queue.insert(0, p)
                        set_status(p["id"], "")
                        return
                    num = lib.next_number(folder) if naming == "numbered" else 1
                    path = lib.unique_path(folder, make_filename(p, naming, num))
                    with open(path, "wb") as f:
                        f.write(data)
                    lib.add(p, path, topic)
                    with STATE_LOCK:
                        JOB["saved"] += 1
                rec["file"] = os.path.basename(path)
                set_status(p["id"], "saved")
                host = urllib.parse.urlparse(src).netloc
                log(f"Saved: {os.path.basename(path)}  ({host})", "ok")
            else:
                set_status(p["id"], "failed")
                with STATE_LOCK:
                    JOB["failed"] += 1
                    JOB["manual"].append({"id": p["id"], "title": p["title"],
                                          "url": p.get("oa_url") or p.get("landing_url"),
                                          "reason": why})
                log(f"Could not download: {p['title'][:90]} - {why}", "warn")
            done_papers.append(rec)

    try:
        n = clamp_int(SETTINGS.get("parallel"), 1, 6, 3)
        for i in ref_ids:                  # subscription / already-saved picks
            p = entry["papers"].get(i)
            if p and i not in ids:
                rec = dict(p)
                e = lib.find(p)
                if e:
                    rec["file"] = os.path.relpath(os.path.join(lib.root, e["file"]), folder)
                done_papers.append(rec)
        with ThreadPoolExecutor(max_workers=n) as ex:
            for f in [ex.submit(work) for _ in range(n)]:
                f.result()
        if done_papers:
            refs.merge_and_write(folder, topic, done_papers)
            log("Reference list updated (BibTeX, RIS, CSV, APA, IEEE, Reading list.html).")
    except Exception as e:  # keep the UI alive whatever happens
        log(f"Unexpected error: {e}", "error")

    with STATE_LOCK:
        s, t = JOB["saved"], target
        msg = ("Stopped. " if JOB["stop"] else "Finished. ") + f"{s} of {t} PDFs saved."
        if JOB["dupes"]:
            msg += f" {JOB['dupes']} you already had."
        if JOB["manual"]:
            msg += f" {len(JOB['manual'])} need to be opened in your browser."
        JOB.update(running=False, finished=True, message=msg)
    log(msg, "done")


# ------------------------------------------------------------------ HTTP
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/icon.svg": ("icon.svg", "image/svg+xml")}


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenShelf/" + VERSION

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def err(self, code, msg):
        self.send(code, {"error": msg})

    # -------------------------------------------------------------- GET
    def do_GET(self):
        if not self._host_ok():
            return self.err(403, "forbidden")
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if url.path in STATIC:
            name, ctype = STATIC[url.path]
            with open(os.path.join(WEB, name), "rb") as f:
                return self.send(200, f.read(), ctype)
        if url.path == "/api/config":
            lib = library()
            return self.send(200, {
                "version": VERSION, "max_papers": MAX_PAPERS,
                "publishers": [{"key": p["key"], "name": p["name"]} for p in PUBLISHERS],
                "naming": NAMING, "settings": {**SETTINGS, "papers_dir": lib.root},
                "library_count": lib.count(), "year": dt.date.today().year})
        if url.path == "/api/collections":
            return self.send(200, {"root": library().root,
                                   "collections": library().collections()})
        if url.path == "/api/job":
            with STATE_LOCK:
                snap = json.loads(json.dumps(JOB))
                JOB.pop("added", None)
            snap["budget"] = Budget.remaining_usd
            return self.send(200, snap)
        if url.path == "/api/export":
            sid = (qs.get("search_id") or [""])[0]
            fmt = (qs.get("fmt") or ["bib"])[0]
            ids = [i for i in (qs.get("ids") or [""])[0].split(",") if i]
            entry = SEARCHES.get(sid)
            if not entry or fmt not in refs.EXPORTERS:
                return self.err(404, "Search expired - run it again.")
            papers = [entry["papers"][i] for i in ids if i in entry["papers"]] or list(entry["papers"].values())
            fname, fn = refs.EXPORTERS[fmt]
            stem = folder_name(entry["opts"]["topic"])
            out = f"{stem} - {fname}"
            return self.send(200, fn(papers), "application/octet-stream", {
                "Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote(out)})
        return self.err(404, "not found")

    # -------------------------------------------------------------- POST
    def do_POST(self):
        if not self._host_ok():
            return self.err(403, "forbidden")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.err(415, "JSON expected")
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = {}
        route = {"/api/search": self.api_search, "/api/more": self.api_more,
                 "/api/download": self.api_download, "/api/stop": self.api_stop,
                 "/api/references": self.api_references, "/api/settings": self.api_settings,
                 "/api/open": self.api_open}.get(self.path)
        if not route:
            return self.err(404, "not found")
        try:
            route(body)
        except SearchError as e:
            self.err(502, str(e))
        except Exception as e:
            self.err(500, f"{type(e).__name__}: {e}")

    def api_search(self, body):
        opts = parse_opts(body)
        if not opts["topic"] and not opts["keywords"]:
            return self.err(400, "Please enter a topic or at least one keyword.")
        s = Search(opts, SETTINGS)
        found = s.next_batch(opts["limit"])
        sid = uuid.uuid4().hex[:12]
        with STATE_LOCK:
            SEARCHES[sid] = {"search": s, "opts": opts,
                             "papers": {p["id"]: p for p in found}}
            while len(SEARCHES) > 20:
                SEARCHES.pop(next(iter(SEARCHES)))
        self.send(200, {"search_id": sid, "total": s.total,
                        "close": s.used_close, "close_total": s.close_total,
                        "exact_shown": sum(1 for p in found if p.get("match") == "exact"),
                        "results": [public(annotate(p)) for p in found],
                        "budget": Budget.remaining_usd,
                        "folder": os.path.join(library().root, folder_name(opts["topic"] or " ".join(opts["keywords"])))})

    def api_more(self, body):
        entry = SEARCHES.get(body.get("search_id"))
        if not entry:
            return self.err(404, "Search expired - run it again.")
        room = MAX_PAPERS - len(entry["papers"])
        if room <= 0:
            return self.send(200, {"results": [], "note": f"The maximum is {MAX_PAPERS} papers per search."})
        found = entry["search"].next_batch(min(room, clamp_int(body.get("n"), 1, 100, 25)))
        for p in found:
            entry["papers"][p["id"]] = p
        self.send(200, {"results": [public(annotate(p)) for p in found],
                        "budget": Budget.remaining_usd})

    def _topic(self, entry, body):
        return (body.get("topic") or entry["opts"]["topic"] or
                " ".join(entry["opts"]["keywords"]) or "Untitled topic").strip()

    def api_download(self, body):
        if JOB.get("running"):
            return self.err(409, "A download is already running.")
        entry = SEARCHES.get(body.get("search_id"))
        if not entry:
            return self.err(404, "Search expired - run it again.")
        ids = [i for i in body.get("ids") or [] if i in entry["papers"]][:MAX_PAPERS]
        if not ids:
            return self.err(400, "Select at least one paper.")
        threading.Thread(target=run_download, daemon=True,
                         args=(body["search_id"], ids, bool(body.get("fill", True)),
                               self._topic(entry, body),
                               [i for i in body.get("ref_ids") or [] if i in entry["papers"]][:MAX_PAPERS])).start()
        self.send(200, {"ok": True})

    def api_stop(self, body):
        JOB["stop"] = True
        self.send(200, {"ok": True})

    def api_references(self, body):
        entry = SEARCHES.get(body.get("search_id"))
        if not entry:
            return self.err(404, "Search expired - run it again.")
        ids = body.get("ids") or list(entry["papers"])
        papers = []
        lib = library()
        topic = self._topic(entry, body)
        folder = lib.topic_dir(topic)
        for i in ids:
            p = entry["papers"].get(i)
            if not p:
                continue
            rec = dict(p)
            e = lib.find(p)
            if e:
                rec["file"] = os.path.relpath(os.path.join(lib.root, e["file"]), folder)
            papers.append(rec)
        merged = refs.merge_and_write(folder, topic, papers)
        self.send(200, {"ok": True, "folder": folder, "added": len(papers),
                        "total": len(merged),
                        "files": [f for f, _ in refs.EXPORTERS.values()] + ["Reading list.html"]})

    def api_settings(self, body):
        if JOB.get("running"):
            return self.err(409, "Wait for the current download to finish.")
        if "papers_dir" in body:
            d = os.path.abspath(os.path.expanduser(str(body["papers_dir"]).strip() or DEFAULT_SETTINGS["papers_dir"]))
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                return self.err(400, f"Cannot use that folder: {e}")
            SETTINGS["papers_dir"] = d
        if body.get("naming") in NAMING:
            SETTINGS["naming"] = body["naming"]
        for k in ("api_key", "email"):
            if k in body:
                SETTINGS[k] = str(body[k]).strip()[:200]
        if "parallel" in body:
            SETTINGS["parallel"] = clamp_int(body["parallel"], 1, 6, 3)
        save_settings()
        self.send(200, {"ok": True, "settings": {**SETTINGS, "papers_dir": library().root}})

    def api_open(self, body):
        lib = library()
        target = os.path.abspath(os.path.join(lib.root, body.get("path") or ""))
        if os.path.commonpath([target, lib.root]) != lib.root or not os.path.exists(target):
            return self.err(400, "That folder does not exist yet.")
        open_path(target)
        self.send(200, {"ok": True})


def main():
    port = int(os.environ.get("OPENSHELF_PORT", "8765"))
    server = None
    for p in range(port, port + 15):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if not server:
        sys.exit("Could not find a free port. Set OPENSHELF_PORT to another number.")
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print(f"  OpenShelf {VERSION} is running at  {url}")
    print(f"  Papers are saved in  {library().root}")
    print("  Keep this window open while you use it. Ctrl+C to quit.")
    print("=" * 60)
    if not os.environ.get("OPENSHELF_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
