"""Search the free OpenAlex index (https://openalex.org) and normalise results.

OpenAlex indexes ~250M scholarly works from every major publisher, including
IEEE, MDPI, Springer Nature, Taylor & Francis, Elsevier, Wiley and arXiv.
No login is needed. An optional free API key raises the daily request budget.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.openalex.org/works"
UA = "OpenShelf/1.0 (local research paper finder; +https://openalex.org)"

# Publisher "lineage" IDs in OpenAlex. A lineage filter also matches imprints
# and subsidiaries (e.g. Springer Nature includes BMC, Nature Portfolio).
PUBLISHERS = [
    {"key": "ieee", "name": "IEEE (Xplore)", "id": "P4310319808"},
    {"key": "mdpi", "name": "MDPI", "id": "P4310310987"},
    {"key": "springer", "name": "Springer Nature", "id": "P4310319965"},
    {"key": "tandf", "name": "Taylor & Francis", "id": "P4310320547"},
    {"key": "elsevier", "name": "Elsevier", "id": "P4310320990"},
    {"key": "wiley", "name": "Wiley (incl. Hindawi)", "id": "P4310320595"},
    {"key": "frontiers", "name": "Frontiers", "id": "P4310320527"},
    {"key": "plos", "name": "PLOS", "id": "P4310315706"},
    {"key": "sage", "name": "SAGE", "id": "P4310320017"},
    {"key": "iop", "name": "IOP Publishing", "id": "P4310311669"},
    {"key": "acs", "name": "American Chemical Society", "id": "P4310320006"},
    {"key": "acm", "name": "ACM", "id": "P4310319798"},
    {"key": "oup", "name": "Oxford University Press", "id": "P4310311648"},
    {"key": "cup", "name": "Cambridge University Press", "id": "P4310311721"},
    {"key": "arxiv", "name": "arXiv (preprints)", "source": "S4306400194"},
]
PUB_BY_KEY = {p["key"]: p for p in PUBLISHERS}

OA_STATUSES = ["gold", "diamond", "green", "hybrid", "bronze"]
DOC_TYPES = {
    "article": "article",
    "review": "review",
    "preprint": "preprint",
    "book-chapter": "book-chapter",
    "dissertation": "dissertation",
}
VENUE_TYPES = ["journal", "conference", "repository", "book-series"]
SORTS = {
    "relevance": "relevance_score:desc",
    "cited": "cited_by_count:desc",
    "newest": "publication_date:desc",
    "oldest": "publication_date:asc",
}
SELECT = ("id,doi,display_name,publication_year,publication_date,cited_by_count,"
          "authorships,primary_location,best_oa_location,locations,type,ids,"
          "biblio,open_access,abstract_inverted_index,language")


class SearchError(Exception):
    pass


class Budget:
    """Tracks the OpenAlex daily budget reported in response headers."""
    remaining_usd = None
    limit_usd = None


def _clean_term(t):
    # Commas separate filters in OpenAlex URLs and quotes are added by us.
    t = re.sub(r'[,"()]', " ", t or "")
    return re.sub(r"\s+", " ", t).strip()


def _quote(t):
    t = _clean_term(t)
    return f'"{t}"' if " " in t else t


def build_query(topic, keywords=(), match="any", exclude=()):
    topic = _clean_term(topic)
    kws = [_quote(k) for k in keywords if _clean_term(k)]
    parts = []
    if topic:
        parts.append(f"({topic})")
    if kws:
        joiner = " OR " if match == "any" else " AND "
        parts.append("(" + joiner.join(kws) + ")")
    q = " AND ".join(parts)
    for ex in exclude:
        if _clean_term(ex):
            q += f" NOT {_quote(ex)}"
    return q


def build_filters(opts, source_only=None, publisher_ids=None):
    f = []
    field = {"title": "title.search", "fulltext": "fulltext.search"}.get(
        opts.get("search_in"), "title_and_abstract.search")
    q = build_query(opts.get("topic"), opts.get("keywords") or [],
                    opts.get("match", "any"), opts.get("exclude") or [])
    if q:
        f.append(f"{field}:{q}")
    y1, y2 = opts.get("year_from"), opts.get("year_to")
    if y1 and y2:
        f.append(f"publication_year:{min(y1, y2)}-{max(y1, y2)}")
    elif y1:
        f.append(f"publication_year:>{int(y1) - 1}")
    elif y2:
        f.append(f"publication_year:<{int(y2) + 1}")

    access = opts.get("access", "oa")
    if access == "oa":
        f.append("open_access.is_oa:true")
        statuses = [s for s in (opts.get("oa_status") or []) if s in OA_STATUSES]
        if statuses and len(statuses) < len(OA_STATUSES):
            f.append("open_access.oa_status:" + "|".join(statuses))
    elif access == "closed":
        f.append("open_access.is_oa:false")

    types = [DOC_TYPES[t] for t in (opts.get("doc_types") or []) if t in DOC_TYPES]
    if types:
        f.append("type:" + "|".join(types))
    venues = [v for v in (opts.get("venue_types") or []) if v in VENUE_TYPES]
    if venues and len(venues) < len(VENUE_TYPES):
        f.append("primary_location.source.type:" + "|".join(venues))
    if opts.get("min_citations"):
        f.append(f"cited_by_count:>{int(opts['min_citations']) - 1}")
    if opts.get("language"):
        f.append(f"language:{_clean_term(opts['language'])}")

    if source_only:
        f.append(f"locations.source.id:{source_only}")
    elif publisher_ids:
        f.append("primary_location.source.publisher_lineage:" + "|".join(publisher_ids))
    return ",".join(f)


def _get(params, settings):
    if settings.get("api_key"):
        params["api_key"] = settings["api_key"]
    if settings.get("email"):
        params["mailto"] = settings["email"]
    url = API + "?" + urllib.parse.urlencode(params, safe=":|,<>*")
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                rem = r.headers.get("X-RateLimit-Remaining-USD")
                lim = r.headers.get("X-RateLimit-Limit-USD")
                try:
                    Budget.remaining_usd = float(rem) if rem else Budget.remaining_usd
                    Budget.limit_usd = float(lim) if lim else Budget.limit_usd
                except ValueError:
                    pass
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read()[:600].decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = float(e.headers.get("Retry-After") or 0)
                except ValueError:
                    wait = 0
                if 0 < wait <= 30 and attempt < 2:
                    time.sleep(wait + 0.5)       # temporary busy period: wait and retry
                    continue
                msg = ""
                try:
                    msg = json.loads(body).get("message") or ""
                except Exception:
                    pass
                if wait and wait <= 120:
                    raise SearchError(f"OpenAlex is busy right now ({msg or 'rate limited'}). "
                                      "Wait a few seconds and search again, or add a free "
                                      "API key in Settings (gear icon).")
                raise SearchError(
                    "The free daily OpenAlex search budget for your network is used up. "
                    "Add a free OpenAlex API key in Settings (gear icon) to get your own "
                    "budget, or try again tomorrow.")
            if e.code in (400, 403):
                msg = body
                try:
                    msg = json.loads(body).get("message") or body
                except Exception:
                    pass
                raise SearchError(f"OpenAlex rejected the search: {msg}")
            last = e
        except Exception as e:  # network hiccup
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise SearchError(f"Could not reach OpenAlex ({last}). Check your internet connection.")


def _abstract(inv):
    if not inv:
        return ""
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    return " ".join(w for _, w in sorted(pos))


def _arxiv_id(work):
    for loc in work.get("locations") or []:
        for u in ((loc or {}).get("landing_page_url") or "", (loc or {}).get("pdf_url") or ""):
            m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$", u)
            if m:
                return m.group(1)
    doi = (work.get("doi") or "").lower()
    m = re.search(r"10\.48550/arxiv\.(.+)$", doi)
    return m.group(1) if m else ""


def normalise(work):
    prim = work.get("primary_location") or {}
    src = prim.get("source") or {}
    oa = work.get("open_access") or {}
    bib = work.get("biblio") or {}
    ids = work.get("ids") or {}
    pdfs = []
    for loc in [work.get("best_oa_location"), prim] + (work.get("locations") or []):
        u = (loc or {}).get("pdf_url")
        if u and u not in pdfs:
            pdfs.append(u)
    arx = _arxiv_id(work)
    if arx:
        u = f"https://arxiv.org/pdf/{arx}"
        if u not in pdfs:
            pdfs.append(u)
    pmcid = (ids.get("pmcid") or "").rstrip("/").split("/")[-1]
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    authors = []
    for a in work.get("authorships") or []:
        n = (a.get("author") or {}).get("display_name")
        if n:
            authors.append(n)
    pages = bib.get("first_page") or ""
    if bib.get("last_page") and bib.get("last_page") != pages:
        pages = f"{pages}-{bib['last_page']}"
    title = re.sub(r"<[^>]+>", "", work.get("display_name") or "Untitled").strip()
    return {
        "id": (work.get("id") or "").split("/")[-1],
        "doi": doi,
        "title": title,
        "year": work.get("publication_year"),
        "date": work.get("publication_date") or "",
        "authors": authors,
        "venue": src.get("display_name") or "",
        "venue_type": src.get("type") or "",
        "publisher": src.get("host_organization_name") or "",
        "issn": (src.get("issn_l") or ""),
        "type": work.get("type") or "",
        "is_oa": bool(oa.get("is_oa")),
        "oa_status": oa.get("oa_status") or "closed",
        "oa_url": oa.get("oa_url") or "",
        "cited_by": work.get("cited_by_count") or 0,
        "volume": bib.get("volume") or "",
        "issue": bib.get("issue") or "",
        "pages": pages,
        "pdf_urls": pdfs,
        "landing_url": prim.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else ""),
        "pmcid": pmcid,
        "arxiv_id": arx,
        "abstract": _abstract(work.get("abstract_inverted_index")),
        "language": work.get("language") or "",
    }


class Search:
    """A paged search. Supports several sub-queries (e.g. publishers + arXiv)
    merged round-robin so each source gets fair representation."""

    def __init__(self, opts, settings):
        self.opts = opts
        self.settings = settings
        keys = [k for k in (opts.get("publishers") or []) if k in PUB_BY_KEY]
        pub_ids = [PUB_BY_KEY[k]["id"] for k in keys if "id" in PUB_BY_KEY[k]]
        sources = [PUB_BY_KEY[k]["source"] for k in keys if "source" in PUB_BY_KEY[k]]
        self.streams = []
        if pub_ids or not sources:
            self.streams.append({"filter": build_filters(opts, publisher_ids=pub_ids),
                                 "cursor": "*", "buf": [], "done": False})
        for s in sources:
            self.streams.append({"filter": build_filters(opts, source_only=s),
                                 "cursor": "*", "buf": [], "done": False})
        self.sort = SORTS.get(opts.get("sort", "relevance"), SORTS["relevance"])
        self.total = 0
        self.seen = set()

    def _fill(self, st, per_page):
        if st["done"] or st["buf"]:
            return
        params = {"filter": st["filter"], "per_page": per_page,
                  "cursor": st["cursor"], "select": SELECT, "sort": self.sort}
        data = _get(params, self.settings)
        meta = data.get("meta") or {}
        if st["cursor"] == "*":
            self.total += meta.get("count") or 0
        st["cursor"] = meta.get("next_cursor")
        st["buf"] = [normalise(w) for w in data.get("results") or []]
        if not st["cursor"] or not st["buf"]:
            st["done"] = True

    def next_batch(self, n, per_page=100):
        out = []
        while len(out) < n:
            live = [s for s in self.streams if not (s["done"] and not s["buf"])]
            if not live:
                break
            progressed = False
            for st in live:
                self._fill(st, per_page)
                while st["buf"]:
                    w = st["buf"].pop(0)
                    key = w["doi"].lower() or w["id"]
                    if key in self.seen:
                        continue
                    self.seen.add(key)
                    out.append(w)
                    progressed = True
                    break
                if len(out) >= n:
                    break
            if not progressed and all(s["done"] and not s["buf"] for s in self.streams):
                break
        return out
