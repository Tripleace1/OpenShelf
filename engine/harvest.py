"""Bridge to the original PaperHarvest engine.

OpenShelf is built on PaperHarvest by Saka Adetayo Muhammed (used with
permission, MIT licence). His source lives unchanged in  PaperHarvest/  and is
loaded here directly, so his proven code does the core work:

  * pdf_links(work)   - finds the open access PDF links of an OpenAlex work
  * fetch_pdf(url, p) - downloads and validates a PDF
  * search(...)       - his original OpenAlex search, used as a backup when
                        OpenShelf's smarter search returns nothing

To update the engine, replace PaperHarvest/paperharvest.py with his latest version.
"""

import importlib.util
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PH_FILE = os.path.join(ROOT, "PaperHarvest", "paperharvest.py")

ph = None
error = ""
try:
    _spec = importlib.util.spec_from_file_location("paperharvest", PH_FILE)
    ph = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ph)          # safe: his server only starts under __main__
except Exception as e:                    # OpenShelf still works without it
    ph = None
    error = f"{type(e).__name__}: {e}"


def available():
    return ph is not None


def pdf_links(work):
    """PaperHarvest's own PDF link finder for a raw OpenAlex work."""
    if not ph:
        return []
    try:
        return ph.pdf_links(work)
    except Exception:
        return []


def fetch(url):
    """Download with PaperHarvest's fetch_pdf. Returns PDF bytes or None."""
    if not ph:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        if ph.fetch_pdf(url, tmp):
            with open(tmp, "rb") as f:
                return f.read()
        return None
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def search(topic, from_year, peer_only, pages=2):
    """PaperHarvest's original search (raw OpenAlex works)."""
    if not ph:
        return []
    out = []
    for page in range(1, pages + 1):
        try:
            res = ph.search(topic, from_year, page, peer_only)
        except Exception:
            res = []
        if not res:
            break
        out.extend(res)
    return out
