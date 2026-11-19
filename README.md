# OpenShelf

**Find, download and cite open access research papers, all on your own computer.**

Type a topic, add keywords, pick the years, the access type and the journal houses you trust (IEEE, MDPI, Springer Nature, Taylor & Francis, Elsevier and more). Then review the list and either **download the PDFs** or **save only the reference list** (BibTeX, RIS, CSV, APA 7, IEEE).

* Nothing to host. It runs locally and opens in your browser.
* No account or login.
* Nothing to install except Python. It uses only the Python standard library.
* Only **legal** open access copies are downloaded. Paywalls are never bypassed.

---

## Quick start

1. Install **Python 3.8+** from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add Python to PATH"** during setup.
2. Get OpenShelf: `git clone <this repo>`, or click **Code → Download ZIP** and unzip it.
3. Start it:

| System | How |
|---|---|
| **Windows** | Double-click **`Start OpenShelf (Windows).bat`** |
| **macOS** | Double-click **`Start OpenShelf (Mac).command`**. The first time, right-click it and choose **Open**. |
| **Linux** | `./start-linux.sh` or `python3 openshelf.py` |
| Any system | `python openshelf.py` in a terminal opened in this folder |

Your browser opens `http://127.0.0.1:8765`. Keep the small terminal window open while you use it, and close it when you're done. If that port is busy, OpenShelf picks the next free one.

---

## What you can set

| Option | What it does |
|---|---|
| **Mode** | **Download PDFs** (free, legal copies), or **Reference list only**, which lists papers from any journal, open access *and* paid, and downloads no PDFs. |
| **Journal quality** | Any venue, **Established** journals (the CWTS core list), **High-impact** (about 4+) or **Top-tier** (about 8+). Impact is OpenAlex's 2-year mean citations per article, an open equivalent of the impact factor. |
| **Topic** | Your research area. It is also the **folder name**. |
| **Keywords** | Extra terms. Choose **Match any** (broader) or **Match all** (stricter). |
| **Publication years** | From and to, with quick buttons (last 2, 5 or 10 years). |
| **Access** | **Open access** (downloadable), **All papers**, or **Subscription only** (useful for reference lists). |
| **OA categories** | Gold, Diamond, Green (repositories such as arXiv), Hybrid, Bronze. |
| **Journal houses** | IEEE Xplore, MDPI, Springer Nature, Taylor & Francis, Elsevier, Wiley/Hindawi, Frontiers, PLOS, SAGE, IOP, ACS, ACM, Oxford UP, Cambridge UP and arXiv. If you select none, every publisher is searched. |
| More filters | Paper type (article, review, preprint, chapter, thesis), venue (journal or conference), words to exclude, where to search (title, abstract or full text) and minimum citations. |
| **Sort** | Best match, most cited, newest or oldest. |
| **How many papers** | No limit (quick buttons for 25 to 1000). Each 100 papers uses one search from the daily OpenAlex budget. |

After a search you can expand any title to read its abstract, untick papers you don't want, and then:

* **Download PDFs.** This saves the open access papers you selected. If one can't be downloaded, OpenShelf can automatically try the next matching paper instead (the "Auto-replace" option).
* **Save references only.** No PDFs are downloaded. You get the reference files listed below.
* **Save PDFs as.** Choose **Separate PDF files**, **One ZIP file only** (each PDF goes straight into `<folder> - papers.zip` with no loose PDFs, and the reference files are added to it too), or **PDF files + a ZIP**. You can make a ZIP of any folder later with **Make ZIP of folder**, or with **ZIP** on the *My collections* page. Papers inside a ZIP still count for duplicate checking.
* **Save as.** Saves a single citation format for the papers you selected straight into the topic folder, with no browser Save dialog.

## Folders and file names

```
OpenShelf/
  Papers/
    UAV navigation in GNSS-denied environments/
      2024 - Smith et al - Deep reinforcement learning for UAV navigation.pdf
      2023 - Chen & Li - LiDAR based detect and avoid.pdf
      references.bib              <- LaTeX / Overleaf
      references.ris              <- Zotero, Mendeley, EndNote
      references.csv              <- Excel (includes abstracts)
      References (APA 7).txt
      References (IEEE).txt
      Reading list.html           <- clickable list with links to each PDF
    Federated learning for IoT/
      ...
```

* Each **topic gets its own folder**. If you search the same topic again, new papers are added to that folder and its reference files are merged without duplicates.
* You can change the file-name style in **Settings** (gear icon):
  `2024 - Smith et al - Title.pdf`, `Smith 2024 - Title.pdf`, `001 - 2024 - Title.pdf`, `Title.pdf`, or the DOI.
* You can also move the whole **Papers** folder anywhere, for example into OneDrive, from Settings.

## No duplicate downloads

OpenShelf keeps a small index (`Papers/.openshelf-library.json`) of every PDF it has saved. Each paper is matched by DOI, OpenAlex ID and title. A paper you already have is marked **"Already in <topic>"** in the results and is never downloaded again, even into a different topic folder. The reference list still includes it, with a link to the copy you already have. If you delete a PDF yourself, OpenShelf will download it again next time.

## Where papers come from

Searches use [OpenAlex](https://openalex.org), a free index of more than 250 million scholarly works from every major publisher. For each open access paper, OpenShelf tries the publisher's free PDF, repository copies (arXiv, PubMed Central, university archives), Semantic Scholar and, if you add an email in Settings, Unpaywall.

**Some publishers block automatic downloads**, even for free papers. This often happens with MDPI, Taylor & Francis and some Elsevier titles. Those papers are listed under **"Open these in your browser"** with a direct link, so you can save each one with a click. Subscription papers are never downloaded. They only go into your reference list, so get those through your library or institution.

## Search budget (optional free key)

Without a key, OpenAlex gives each internet connection a small shared daily budget of about 100 searches, and the header shows how much is left. If you search a lot, or share a university network, get a **free API key** at [openalex.org/settings/api](https://openalex.org/settings/api) and paste it into **Settings**. Your settings are saved only in `settings.json` on your computer.

## Troubleshooting

* **"python is not recognised"**: reinstall Python and tick *Add Python to PATH*, or try `py openshelf.py`.
* **Browser didn't open**: go to `http://127.0.0.1:8765` yourself.
* **Few results**: use fewer or broader keywords, choose *Match any*, widen the years, or select more publishers.
* **Different port**: set `OPENSHELF_PORT=8800` before starting.

## Credits

OpenShelf is built on [PaperHarvest](https://github.com/Adetayo224/PaperHarvest) by **Saka Adetayo Muhammed** (Samfred Robotics), used with his permission under the MIT licence.

His original source is included unchanged in the `PaperHarvest/` folder, and OpenShelf runs on it directly (see `engine/harvest.py`):

* **His PDF-link finder (`pdf_links`) and downloader (`fetch_pdf`)** are tried first for every paper.
* **His original OpenAlex search** is the backup whenever OpenShelf's search returns nothing.

To update the engine, replace `PaperHarvest/paperharvest.py` with his latest version.
