"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = { cfg: null, searchId: null, results: [], selected: new Set(), status: {}, polling: null, folder: "", topic: "" };
const store = {
  get(k, d) { try { const v = localStorage.getItem("openshelf." + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("openshelf." + k, JSON.stringify(v)); } catch { } },
};

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch { }
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.className = "toast", err ? 6000 : 3000);
}

/* ------------------------------------------------------------ chips */
function chipBox(boxId, inputId) {
  const box = $(boxId), input = $(inputId), items = [];
  const render = () => {
    $$(".chip", box).forEach(c => c.remove());
    items.forEach((v, i) => {
      const c = document.createElement("span");
      c.className = "chip"; c.innerHTML = `${esc(v)}<button type="button" aria-label="Remove">×</button>`;
      c.querySelector("button").onclick = () => { items.splice(i, 1); render(); };
      box.insertBefore(c, input);
    });
  };
  const add = raw => raw.split(",").map(s => s.trim()).filter(Boolean).forEach(v => {
    if (!items.some(x => x.toLowerCase() === v.toLowerCase())) items.push(v);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(input.value); input.value = ""; render(); }
    else if (e.key === "Backspace" && !input.value && items.length) { items.pop(); render(); }
  });
  input.addEventListener("blur", () => { if (input.value.trim()) { add(input.value); input.value = ""; render(); } });
  input.addEventListener("paste", e => { const t = e.clipboardData.getData("text"); if (t.includes(",")) { e.preventDefault(); add(t); render(); } });
  box.addEventListener("click", () => input.focus());
  return { get: () => { if (input.value.trim()) { add(input.value); input.value = ""; render(); } return [...items]; }, set: a => { items.splice(0, items.length, ...a); render(); } };
}
const kw = chipBox("#kwBox", "#kwInput");
const ex = chipBox("#exBox", "#exInput");

function seg(id, onChange) {
  const el = $(id);
  el.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    $$("button", el).forEach(x => x.classList.toggle("on", x === b));
    onChange && onChange(b.dataset.v);
  });
  return { get: () => $("button.on", el).dataset.v, set: v => { const b = $(`button[data-v="${v}"]`, el); if (b) b.click(); } };
}
const ACCESS_HINT = {
  oa: "Free, legal PDFs you can download.",
  all: "Open and subscription papers. Subscription papers go into the reference list only.",
  closed: "Subscription papers only — for building a reference list.",
};
const match = seg("#match");
const access = seg("#access", v => { $("#accessHint").textContent = ACCESS_HINT[v]; $("#oaStatus").hidden = v !== "oa"; });

const MODE_HINT = {
  pdf: "Downloads free, legal PDFs into your topic folder.",
  refs: "Builds a citation list from all journals — open access and paid. No PDFs are downloaded.",
};
const mode = seg("#mode", v => {
  document.body.classList.toggle("refs-mode", v === "refs");
  $("#modeHint").textContent = MODE_HINT[v];
  $("#refsBtn").className = v === "refs" ? "primary" : "secondary";
  $("#refsBtn").textContent = v === "refs" ? "Save reference list" : "Save references only";
  if (!mode) return;                       // initial setup
  if (v === "refs") { access.set("all"); if ($("#quality").value === "any") $("#quality").value = "high"; }
  else { access.set("oa"); }
  if (state.results.length) { state.selected = new Set(state.results.filter(selectable).map(p => p.id)); renderList(); }
});

const checks = id => $$(`${id} input:checked`).map(i => i.value);
const setChecks = (id, vals) => vals && $$(`${id} input`).forEach(i => i.checked = vals.includes(i.value));

/* ------------------------------------------------------------ form */
function folderHint() {
  const t = $("#folderName").value.trim() || $("#topic").value.trim();
  const name = t.replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80) || "…";
  $("#folderHint").innerHTML = `Saved in <code>${esc((state.cfg?.settings.papers_dir || "Papers"))}${navigator.platform.startsWith("Win") ? "\\" : "/"}${esc(name)}</code>`;
}
$("#topic").addEventListener("input", folderHint);
$("#folderName").addEventListener("input", folderHint);
$("#topic").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#form").requestSubmit(); } });
$("#limitQuick").addEventListener("click", e => { const b = e.target.closest("button"); if (b) $("#limit").value = b.dataset.n; });
$("#yearQuick").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  const n = +b.dataset.y, y = state.cfg?.year || new Date().getFullYear();
  $("#yearFrom").value = n ? y - n + 1 : ""; $("#yearTo").value = n ? y : "";
});

function readForm() {
  return {
    mode: mode.get(), quality: $("#quality").value, folder: $("#folderName").value.trim(),
    topic: $("#topic").value.trim(), keywords: kw.get(), match: match.get(), exclude: ex.get(),
    year_from: $("#yearFrom").value, year_to: $("#yearTo").value,
    access: access.get(), oa_status: checks("#oaStatus"),
    publishers: $$("#pubs button.on").map(b => b.dataset.k),
    doc_types: checks("#docTypes"), venue_types: checks("#venueTypes"),
    language: $("#englishOnly").checked ? "en" : "",
    search_in: $("#searchIn").value, min_citations: $("#minCit").value,
    sort: $("#sort").value, limit: Math.max(1, Math.round(+$("#limit").value || 25)),
  };
}
function writeForm(f) {
  if (!f) return;
  mode.set(f.mode || "pdf"); $("#quality").value = f.quality || "any";
  $("#folderName").value = f.folder || "";
  $("#topic").value = f.topic || ""; kw.set(f.keywords || []); ex.set(f.exclude || []);
  match.set(f.match || "any"); access.set(f.access || "oa");
  $("#yearFrom").value = f.year_from || ""; $("#yearTo").value = f.year_to || "";
  setChecks("#oaStatus", f.oa_status); setChecks("#docTypes", f.doc_types); setChecks("#venueTypes", f.venue_types);
  $$("#pubs button").forEach(b => b.classList.toggle("on", (f.publishers || []).includes(b.dataset.k)));
  $("#englishOnly").checked = f.language !== "";
  $("#searchIn").value = f.search_in || "title_abstract"; $("#minCit").value = f.min_citations || "";
  $("#sort").value = f.sort || "relevance"; $("#limit").value = f.limit || 25;
}

$("#form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = readForm();
  if (!f.topic && !f.keywords.length) return toast("Enter a topic or at least one keyword.", true);
  if (!f.doc_types.length) return toast("Pick at least one paper type under More filters.", true);
  store.set("form", f);
  const go = $("#go"); go.disabled = true; go.lastChild.textContent = " Searching…";
  // If OpenAlex asks us to wait, show a countdown while the server retries by itself.
  const busyTimer = setInterval(async () => {
    try {
      const b = await api("/api/busy");
      go.lastChild.textContent = b.wait ? ` OpenAlex is busy, retrying in ${b.wait}s…` : " Searching…";
    } catch { }
  }, 1500);
  try {
    const r = await api("/api/search", f);
    state.searchId = r.search_id; state.results = r.results; state.status = {};
    state.folder = r.folder; state.topic = f.topic || f.keywords.join(" ");
    state.folderName = f.folder || state.topic;
    state.selected = new Set(r.results.filter(selectable).map(p => p.id));
    $("#resTitle").textContent = state.topic;
    $("#resMeta").textContent = r.close
      ? (r.exact_shown
        ? `${r.exact_shown} papers match every key term, plus the closest matches · showing ${r.results.length}`
        : `No paper matches every key term, so these are the closest matches, ranked by relevance · showing ${r.results.length}`)
      : `${r.total.toLocaleString()} matching papers in OpenAlex · showing ${r.results.length}`;
    showBudget(r.budget);
    if (r.key_status === "not_activated") toast("Your OpenAlex API key isn't active yet. Click the link in the email “Activate your OpenAlex API key”. Searching without it for now.");
    else if (r.key_status === "invalid") toast("OpenAlex didn't accept the API key in Settings, so searching without it. Check the key.", true);
    $("#empty").hidden = true; $("#resWrap").hidden = false; $("#actionbar").hidden = false; $("#job").hidden = true;
    $("#loadMore").hidden = r.results.length < f.limit;
    renderList();
    if (!r.results.length) toast("No papers matched. Try fewer keywords, more years, or more publishers.", true);
  } catch (err) { toast(err.message, true); }
  finally { clearInterval(busyTimer); go.disabled = false; go.lastChild.textContent = " Find papers"; }
});

$("#loadMore").onclick = async () => {
  const b = $("#loadMore"); b.disabled = true;
  try {
    const r = await api("/api/more", { search_id: state.searchId, n: 50 });
    if (r.note) toast(r.note);
    r.results.forEach(p => { state.results.push(p); if (selectable(p)) state.selected.add(p.id); });
    $("#resMeta").textContent = $("#resMeta").textContent.replace(/showing \d+/, `showing ${state.results.length}`);
    if (r.results.length < 50) b.hidden = true;
    showBudget(r.budget); renderList();
  } catch (err) { toast(err.message, true); }
  b.disabled = false;
};

/* ------------------------------------------------------------ results */
const selectable = p => mode.get() === "refs" || !p.in_library;
const TYPE_LABEL = { article: "Article", review: "Review", preprint: "Preprint", "book-chapter": "Book chapter", dissertation: "Thesis" };
const STATUS_LABEL = { saved: "✓ Saved", failed: "Open in browser", dupe: "Already saved", downloading: "Downloading" };

function renderList() {
  const only = $("#onlyPdf").checked;
  const html = state.results.map(p => {
    const hide = only && !p.has_pdf_link;
    if (hide) return "";
    const auth = p.authors.slice(0, 4).join(", ") + (p.authors.length > 4 ? " et al." : "");
    const st = state.status[p.id];
    const badges = [
      `<span class="b ${esc(p.oa_status)}">${p.is_oa ? esc(p.oa_status) + " OA" : "subscription"}</span>`,
      `<span class="b">${esc(TYPE_LABEL[p.type] || p.type)}</span>`,
      p.publisher ? `<span class="b" style="text-transform:none">${esc(p.publisher)}</span>` : "",
      p.match === "close" ? `<span class="b close">Close match</span>` : "",
      p.in_library ? `<span class="b lib">Already in “${esc(p.in_library.topic)}”</span>` : "",
      p.is_oa && !p.has_pdf_link ? `<span class="b nopdf">No direct PDF link</span>` : "",
    ].join("");
    const link = p.doi ? `https://doi.org/${p.doi}` : p.landing_url;
    return `<li class="item${p.in_library ? " dim" : ""}" data-id="${esc(p.id)}">
      <input type="checkbox" class="sel" ${state.selected.has(p.id) ? "checked" : ""} aria-label="Select">
      <div>
        <div class="t">${esc(p.title)}</div>
        <div class="m">${esc(auth || "Unknown authors")} · ${esc(p.year || "")} · <i>${esc(p.venue || "—")}</i></div>
        <div class="badges">${badges}</div>
        <div class="abs">${p.abstract ? esc(p.abstract) : "<i>No abstract available.</i>"}</div>
      </div>
      <div class="right">
        <div class="cit">${(p.cited_by || 0).toLocaleString()}</div>citations
        ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">View paper ↗</a>` : ""}
        ${st ? `<div class="st ${st}">${STATUS_LABEL[st] || ""}</div>` : ""}
      </div></li>`;
  }).join("");
  $("#list").innerHTML = html || `<li class="muted" style="padding:20px">Nothing to show with the current filter.</li>`;
  updateSel();
}

$("#list").addEventListener("click", e => {
  const li = e.target.closest(".item"); if (!li) return;
  if (e.target.classList.contains("sel")) {
    e.target.checked ? state.selected.add(li.dataset.id) : state.selected.delete(li.dataset.id);
    return updateSel();
  }
  if (e.target.classList.contains("t")) li.classList.toggle("open");
});
$("#selAll").onchange = e => {
  state.selected = new Set(e.target.checked ? state.results.filter(p => !$("#onlyPdf").checked || p.has_pdf_link).map(p => p.id) : []);
  renderList();
};
$("#onlyPdf").onchange = renderList;

function updateSel() {
  const sel = state.results.filter(p => state.selected.has(p.id));
  const dl = sel.filter(p => p.is_oa && !p.in_library);
  $("#selCount").textContent = sel.length;
  $("#dlBtn").textContent = dl.length ? `Download ${dl.length} PDF${dl.length > 1 ? "s" : ""}` : "Download PDFs";
  $("#dlBtn").disabled = !dl.length || !!state.polling;
  $("#refsBtn").disabled = !sel.length;
}

/* ------------------------------------------------------------ actions */
$("#dlBtn").onclick = async () => {
  const ids = state.results.filter(p => state.selected.has(p.id) && p.is_oa && !p.in_library).map(p => p.id);
  const refIds = [...state.selected].filter(i => !ids.includes(i));
  const skipped = refIds.length;
  try {
    await api("/api/download", { search_id: state.searchId, ids, ref_ids: refIds, fill: $("#fill").checked, zip: $("#wantZip").checked, topic: state.topic, folder: state.folderName });
    store.set("zip", $("#wantZip").checked);
    if (skipped) toast(`${skipped} selected paper(s) are subscription-only or already saved — they'll go in the reference list only.`);
    $("#job").hidden = false; $("#manual").hidden = true; $("#openListBtn").hidden = true;
    $("#stopBtn").hidden = false; $("#log").innerHTML = "";
    $("#job").scrollIntoView({ behavior: "smooth", block: "nearest" });
    poll();
  } catch (err) { toast(err.message, true); }
};

function poll() {
  clearInterval(state.polling);
  const tick = async () => {
    let j; try { j = await api("/api/job"); } catch { return; }
    (j.added || []).forEach(p => { if (!state.results.some(x => x.id === p.id)) state.results.push(p); });
    state.status = j.status || {};
    const pct = j.target ? Math.min(100, Math.round(100 * j.saved / j.target)) : 0;
    $("#jobBar").style.width = (j.finished ? 100 : pct) + "%";
    $("#jobTitle").textContent = j.finished ? j.message : `Downloading… ${j.saved} of ${j.target} saved`;
    $("#jobCounts").textContent = `${j.checked} checked · ${j.dupes} already had · ${j.failed} to open manually`;
    $("#log").innerHTML = j.log.map(l => `<div class="${l.kind}">${esc(l.t)}  ${esc(l.msg)}</div>`).join("");
    $("#log").scrollTop = 1e9;
    if (j.manual.length) {
      $("#manual").hidden = false;
      $("#manualList").innerHTML = j.manual.map(m => `<li><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title)}</a> <span class="muted">— ${esc(m.reason)}</span></li>`).join("");
    }
    showBudget(j.budget);
    renderList();
    if (j.finished || !j.running) {
      clearInterval(state.polling); state.polling = null;
      state.results.forEach(p => {
        if (state.status[p.id] === "saved") { p.in_library = { topic: state.folderName }; state.selected.delete(p.id); }
        if (state.status[p.id] === "failed") state.selected.delete(p.id);
      });
      renderList();
      $("#stopBtn").hidden = true; $("#openListBtn").hidden = false; $("#zipBtn").hidden = false;
      refreshLibCount(); updateSel();
      toast(j.message);
    }
  };
  state.polling = setInterval(tick, 900); tick(); updateSel();
}

$("#stopBtn").onclick = () => api("/api/stop", {}).then(() => toast("Stopping after the current downloads…"));
const openRel = p => api("/api/open", { path: p }).catch(err => toast(err.message, true));
const folderOfTopic = () => state.folder.split(/[\\/]/).pop();
$("#openFolderBtn").onclick = () => openRel(folderOfTopic());
$("#openListBtn").onclick = () => openRel(folderOfTopic() + "/Reading list.html");
const makeZip = folder => api("/api/zip", { path: folder })
  .then(r => toast(`Saved “${r.file}” (${r.pdfs} PDFs) in the folder.`))
  .catch(err => toast(err.message, true));
$("#zipBtn").onclick = () => makeZip(folderOfTopic());

$("#refsBtn").onclick = async () => {
  const ids = [...state.selected];
  try {
    const r = await api("/api/references", { search_id: state.searchId, ids, topic: state.topic, folder: state.folderName });
    toast(`Saved ${r.added} references (${r.total} in this topic) as BibTeX, RIS, CSV, APA, IEEE and a reading list.`);
    $("#job").hidden = false; $("#stopBtn").hidden = true; $("#openListBtn").hidden = false;
    $("#jobTitle").textContent = `Reference list saved — ${r.total} references in “${state.folderName}”`;
    $("#jobCounts").textContent = r.files.join(" · ");
    $("#jobBar").style.width = "100%"; $("#manual").hidden = true; $("#log").innerHTML = "";
  } catch (err) { toast(err.message, true); }
};

$("#exportBtn").onclick = e => { e.stopPropagation(); $("#exportMenu").classList.toggle("open"); };
document.addEventListener("click", () => $("#exportMenu").classList.remove("open"));
$("#exportMenu").addEventListener("click", e => {
  const a = e.target.closest("a"); if (!a) return;
  $("#exportMenu").classList.remove("open");
  api("/api/save-export", { search_id: state.searchId, fmt: a.dataset.fmt, ids: [...state.selected], folder: state.folderName })
    .then(r => toast(`Saved “${r.file}” in your ${state.folderName} folder.`))
    .catch(err => toast(err.message, true));
});

/* ------------------------------------------------------------ header bits */
function showBudget(b) {
  const el = $("#budget");
  if (b == null) return;
  const lim = state.cfg?.settings.api_key ? 1 : 0.1;
  const left = Math.max(0, Math.round(b / 0.001));
  el.hidden = false; el.textContent = `~${left.toLocaleString()} searches left today`;
  el.className = "pill " + (b < lim * 0.15 ? "low" : "subtle");
}
async function refreshLibCount() {
  try { const c = await api("/api/config"); state.cfg = c; $("#libCount").textContent = `${c.library_count} paper${c.library_count === 1 ? "" : "s"}`; } catch { }
}

/* ------------------------------------------------------------ views */
$$(".tab").forEach(t => t.onclick = () => {
  $$(".tab").forEach(x => x.classList.toggle("active", x === t));
  $("#view-search").hidden = t.dataset.view !== "search";
  $("#view-collections").hidden = t.dataset.view !== "collections";
  if (t.dataset.view === "collections") loadCollections();
});
async function loadCollections() {
  try {
    const r = await api("/api/collections");
    $("#colRoot").textContent = r.root;
    $("#colGrid").innerHTML = r.collections.length ? r.collections.map(c => `
      <div class="panel card"><b>${esc(c.name)}</b>
        <div class="nums"><span><b>${c.pdfs}</b> PDFs</span><span><b>${c.references}</b> references</span></div>
        <div class="muted" style="font-size:12px">Updated ${esc(c.updated)}</div>
        <div class="acts"><button class="ghost" data-open="${esc(c.name)}">Open folder</button>
        ${c.references ? `<button class="ghost" data-open="${esc(c.name)}/Reading list.html">Reading list</button>` : ""}
        <button class="ghost" data-zip="${esc(c.name)}">ZIP</button>
        <button class="ghost" data-again="${esc(c.name)}">Search again</button></div></div>`).join("")
      : `<p class="muted">No collections yet. Run a search and download papers or save a reference list.</p>`;
  } catch (err) { toast(err.message, true); }
}
$("#colGrid").addEventListener("click", e => {
  const o = e.target.closest("[data-open]"); if (o) return openRel(o.dataset.open);
  const z = e.target.closest("[data-zip]"); if (z) return makeZip(z.dataset.zip).then(loadCollections);
  const a = e.target.closest("[data-again]");
  if (a) { $("#folderName").value = a.dataset.again; folderHint(); $(".tab[data-view=search]").click(); $("#topic").focus(); }
});
$("#openRoot").onclick = () => openRel("");

/* ------------------------------------------------------------ settings */
$("#openSettings").onclick = () => {
  const s = state.cfg.settings;
  $("#sDir").value = s.papers_dir; $("#sKey").value = s.api_key || ""; $("#sEmail").value = s.email || ""; $("#sPar").value = s.parallel || 3;
  $("#sNaming").innerHTML = Object.entries(state.cfg.naming).map(([k, ex]) =>
    `<label><input type="radio" name="naming" value="${k}" ${k === s.naming ? "checked" : ""}> <code>${esc(ex)}</code></label>`).join("");
  $("#settings").showModal();
};
$("#settings").addEventListener("close", async () => {
  if ($("#settings").returnValue !== "save") return;
  try {
    const r = await api("/api/settings", {
      papers_dir: $("#sDir").value, api_key: $("#sKey").value, email: $("#sEmail").value,
      parallel: +$("#sPar").value, naming: ($("input[name=naming]:checked") || {}).value,
    });
    state.cfg.settings = r.settings; folderHint(); refreshLibCount(); toast("Settings saved.");
  } catch (err) { toast(err.message, true); }
});

/* ------------------------------------------------------------ theme */
$("#themeBtn").onclick = () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("openshelf.theme", next); } catch { }
};

/* ------------------------------------------------------------ boot */
(async function boot() {
  try {
    state.cfg = await api("/api/config");
  } catch { return toast("Can't reach OpenShelf. Is the terminal window still open?", true); }
  $("#pubs").innerHTML = state.cfg.publishers.map(p => `<button type="button" data-k="${p.key}">${esc(p.name)}</button>`).join("");
  $("#pubs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) b.classList.toggle("on"); });
  $("#yearFrom").max = $("#yearTo").max = state.cfg.year + 1;
  const saved = store.get("form");
  if (saved) writeForm(saved); else { $("#yearFrom").value = state.cfg.year - 4; $("#yearTo").value = state.cfg.year; }
  $("#libCount").textContent = `${state.cfg.library_count} paper${state.cfg.library_count === 1 ? "" : "s"}`;
  folderHint();
  $("#wantZip").checked = store.get("zip", false);
  try { const j = await api("/api/job"); if (j.running) { $("#job").hidden = false; poll(); } } catch { }
})();
