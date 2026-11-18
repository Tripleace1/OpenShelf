"""Download legal open access PDFs.

For each paper we try, in order:
  1. every PDF link OpenAlex knows (publisher OA copy, repositories, arXiv)
  2. the PubMed Central copy via Europe PMC (if the paper has a PMCID)
  3. the open access PDF Semantic Scholar knows about
  4. Unpaywall (only if you set a contact email in Settings)
If a link returns an article web page instead of a PDF, we follow the standard
<meta name="citation_pdf_url"> tag that publishers publish for indexers.

Nothing here bypasses paywalls, logins or bot protection. When a publisher
blocks automated downloads, the paper is listed under "Open in browser" so you
can save it yourself with one click.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MIN_PDF_BYTES = 15_000
MAX_PDF_BYTES = 80 * 1024 * 1024


def _open(url, accept, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA, "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9"})
    return urllib.request.urlopen(req, timeout=timeout)


def _json(url, timeout=20):
    try:
        with _open(url, "application/json", timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _read_limited(r):
    chunks, size = [], 0
    while True:
        c = r.read(256 * 1024)
        if not c:
            break
        size += len(c)
        if size > MAX_PDF_BYTES:
            raise ValueError("file too large")
        chunks.append(c)
    return b"".join(chunks)


def _citation_pdf(html_bytes, base):
    text = html_bytes[:400_000].decode("utf-8", "ignore")
    for pat in (r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url'):
        m = re.search(pat, text, re.I)
        if m:
            return urllib.parse.urljoin(base, unescape(m.group(1)))
    return None


def fetch_pdf(url, timeout=60, follow_meta=True):
    """Return (pdf_bytes or None, reason)."""
    try:
        with _open(url, "application/pdf,text/html;q=0.8,*/*;q=0.5", timeout) as r:
            data = _read_limited(r)
            final = r.geturl()
            ctype = (r.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            return None, "blocked by publisher (open it in your browser)"
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"network error ({type(e).__name__})"
    if data[:5] == b"%PDF-" or data[:1024].lstrip()[:5] == b"%PDF-":
        if len(data) < MIN_PDF_BYTES:
            return None, "file too small to be a full paper"
        return data, "ok"
    if follow_meta and "html" in ctype:
        nxt = _citation_pdf(data, final)
        if nxt and nxt != url:
            return fetch_pdf(nxt, timeout, follow_meta=False)
        if re.search(rb"captcha|just a moment|access denied|cf-chl", data[:20000], re.I):
            return None, "blocked by publisher (open it in your browser)"
        return None, "page has no PDF"
    return None, "not a PDF"


def candidate_urls(paper, settings):
    urls = list(paper.get("pdf_urls") or [])
    if paper.get("pmcid"):
        urls.append("https://europepmc.org/backend/ptpmcrender.fcgi?accid="
                    f"{paper['pmcid']}&blobtype=pdf")
    return urls


def extra_urls(paper, settings):
    """Slower lookups, only used when the OpenAlex links all failed."""
    doi = paper.get("doi")
    if not doi:
        return []
    out = []
    s2 = _json("https://api.semanticscholar.org/graph/v1/paper/DOI:"
               + urllib.parse.quote(doi) + "?fields=openAccessPdf")
    u = ((s2 or {}).get("openAccessPdf") or {}).get("url")
    if u:
        out.append(u)
    if settings.get("email"):
        up = _json(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email="
                   + urllib.parse.quote(settings["email"]))
        for loc in (up or {}).get("oa_locations") or []:
            if loc.get("url_for_pdf"):
                out.append(loc["url_for_pdf"])
    return out


def download(paper, settings, should_stop=lambda: False):
    """Try every legal source. Returns (bytes or None, source_url, reason)."""
    tried, reason = set(), "no open access PDF link found"
    for stage in (candidate_urls, extra_urls):
        for url in stage(paper, settings):
            if url in tried or should_stop():
                continue
            tried.add(url)
            data, why = fetch_pdf(url)
            if data:
                return data, url, "ok"
            reason = why
    return None, None, reason
