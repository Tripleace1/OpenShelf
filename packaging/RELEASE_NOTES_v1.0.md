# OpenShelf v1.0: find, download and cite open research papers

OpenShelf is a free desktop app that finds research papers on any topic, downloads the ones that are legally open access, and builds your reference list for you. Your papers stay on your own computer. It needs no login and no account, and there's nothing to install.

## Download

**Windows 10 / 11:** download **`OpenShelf.exe`** below and double-click it. You don't need Python or the command line.

> **First run:** Windows may show *"Windows protected your PC"* because the app isn't signed with a paid certificate. Click **More info → Run anyway**.

A small black window opens and OpenShelf opens in your browser. Keep that window open while you use the app, and close it when you're done. Your papers and settings are saved in **`Documents\OpenShelf`**.

macOS and Linux users can run it from the source code. See the README.

## What it does

**Search the way you think**
- Type your full project title. OpenShelf picks out the key terms, understands common abbreviations (ML, UAV, GNSS, IoT, PV…), and returns the closest matches even when no paper uses every word.
- Filter by keywords (match any or all), publication years, open access type (Gold, Diamond, Green, Hybrid, Bronze), paper type, venue and minimum citations.
- **Journal houses:** IEEE Xplore, MDPI, Springer Nature, Taylor & Francis, Elsevier, Wiley, Frontiers, PLOS, SAGE, IOP, ACS, ACM, Oxford, Cambridge and arXiv.
- **Journal quality:** established, high-impact or top-tier journals.
- **No limit** on the number of papers per search.

**Download PDFs, or just get the references**
- **Download PDFs:** only free, legal open access copies. If a paper can't be downloaded, OpenShelf can automatically try the next matching one.
- **Reference list only:** covers open access *and* paid papers from any journal, with no downloads. You get **BibTeX, RIS (Zotero/Mendeley/EndNote), CSV, APA 7, IEEE** and a clickable **Reading list**.
- **Save PDFs as:** separate files, **one ZIP file**, or both.

**Organised automatically**
- One folder per topic, with a short folder name you choose. Your full title is saved in `Project title.txt`.
- Clear file names, for example `2024 - Smith et al - Paper title.pdf` (you can change the style in Settings).
- **No duplicates:** a paper you already have is never downloaded twice, even into another topic folder or inside a ZIP.
- A *My collections* page lists all your topic folders, with one-click Open, Reading list and ZIP.

**Comfortable to use**
- A clean white, blue and red interface with **light and dark mode**.
- Automatically waits and retries when the search service is busy.

## Good to know

- **Only legal open access PDFs are downloaded.** Paywalls are never bypassed. Subscription papers go into your reference list only.
- **Some publishers block automatic downloads**, even of free papers (often MDPI and some Elsevier and Wiley titles). Those papers are listed under **"Open these in your browser"**, so you can save each one with a click.
- Searches use the free [OpenAlex](https://openalex.org) index. Without an API key, everyone on your internet connection shares a small daily search allowance. A **free key** from [openalex.org/settings/api](https://openalex.org/settings/api), pasted into **Settings** (the gear icon), gives you your own allowance, about 10 times larger.

## Credits

OpenShelf is built on **[PaperHarvest](https://github.com/Adetayo224/PaperHarvest)** by **Saka Adetayo Muhammed** (Samfred Robotics), used with permission. His original search and download engine is included and runs inside OpenShelf.

Released under the MIT licence.

## File details

| File | Size | SHA-256 |
|---|---|---|
| `OpenShelf.exe` | 9.2 MB | `98f37f3da382e7a69604af0dadac30aa4e72b6da131095f8f793556747bb0798` |
