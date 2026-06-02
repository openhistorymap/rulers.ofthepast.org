/* app.js — rulers.ofthepast.org (the synchronic chronicle)
 *
 * Loads data/manifest.json + data/rulers.json and renders a *synchronic* view:
 * the hero is a year on the Meridian, and the gallery shows who held power
 * across the world at that same moment, laid out in region lanes. Move the
 * meridian (drag, click, arrow keys, or "let time drift") and the world's
 * thrones re-light. A card opens the detail folio; the avatar opens from
 * chat.js. The reverse handoff points back to rulers.ofancientrome.org.
 *
 * The meridian scale is piecewise: each era gets screen width proportional to
 * how many rulers it holds (navigation, not a data viz — the dense ages get
 * room, the sparse deep past stays compact), and the year maps linearly within
 * its era band. Relative paths only.
 */

const state = {
  manifest: null,
  rulers: [],
  byId: {},
  regions: [],          // [{key,label,count}]
  segments: [],         // piecewise meridian segments
  detailCache: {},
  bounds: { min_year: 0, max_year: 0 },
  year: 800,
  mode: "synchronic",   // "synchronic" | "atlas"
  query: "",
  sweeping: false,
  current: null,
};

/* ---------- helpers ---------- */
function fmtYear(y) {
  if (y === null || y === undefined) return null;
  return y < 0 ? `${-y} BC` : `AD ${y}`;
}
function fmtRange(a, b) {
  const fa = fmtYear(a), fb = fmtYear(b);
  if (fa && fb) return fa === fb ? fa : `${fa} – ${fb}`;
  return fa || fb || "—";
}
function compactReign(a, b) {
  if (a == null && b == null) return "";
  if (a != null && b != null) {
    if (a < 0 && b < 0) return `r. ${-a}–${-b} BC`;
    if (a < 0 && b >= 0) return `r. ${-a} BC – AD ${b}`;
    return `r. ${a}–${b}`;
  }
  return "r. " + (fmtYear(a) || fmtYear(b));
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function esc(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function reigning(r, y) {
  return r.display_from != null && r.display_to != null && r.display_from <= y && y <= r.display_to;
}

/* ---------- piecewise meridian scale ---------- */
function buildSegments() {
  const { min_year, max_year } = state.bounds;
  const eras = state.manifest.eras || [];
  // Width per era is proportional to its ruler count (dense ages get room), but
  // floored so every band stays clickable — and the empty deep-time "dawn" band
  // gets a deliberate share so the meridian visibly reaches back to 9000 BC.
  const FLOOR = 11;
  const weights = eras.map((e) => Math.max(e.count || 0, FLOOR));
  const di = eras.findIndex((e) => e.key === "dawn");
  if (di >= 0) {
    const others = weights.reduce((s, w, j) => (j === di ? s : s + w), 0);
    weights[di] = Math.max(weights[di], others * 0.13);
  }
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  let x = 0;
  state.segments = eras.map((e, i) => {
    const lo = e.from == null ? min_year : e.from;
    const hi = e.to == null ? max_year : e.to;
    const w = weights[i] / total;
    const seg = { key: e.key, label: e.label, lo, hi, x, w, count: e.count || 0 };
    x += w;
    return seg;
  });
  if (state.segments.length) {
    const last = state.segments[state.segments.length - 1];
    last.w = 1 - last.x;
  }
}
function yearToPos(y) {
  const { min_year, max_year } = state.bounds;
  y = Math.max(min_year, Math.min(max_year, y));
  for (const s of state.segments) {
    if (y <= s.hi || s === state.segments[state.segments.length - 1]) {
      const span = s.hi - s.lo || 1;
      const frac = Math.max(0, Math.min(1, (y - s.lo) / span));
      return s.x + frac * s.w;
    }
  }
  return 1;
}
function posToYear(p) {
  p = Math.max(0, Math.min(1, p));
  for (const s of state.segments) {
    if (p <= s.x + s.w || s === state.segments[state.segments.length - 1]) {
      const frac = s.w ? (p - s.x) / s.w : 0;
      return Math.round(s.lo + frac * (s.hi - s.lo));
    }
  }
  return state.bounds.max_year;
}
function eraOfYear(y) {
  for (const s of state.segments) {
    if (y < s.hi || s === state.segments[state.segments.length - 1]) return s;
  }
  return state.segments[state.segments.length - 1];
}
function parseYear(str) {
  const s = (str || "").trim().toLowerCase();
  if (!s) return null;
  const bc = /\bb\.?c\.?(e)?\b/.test(s);
  const y = parseInt(s.replace(/a\.?d\.?|c\.?e\.?|b\.?c\.?(e)?/g, "").replace(/[^0-9-]/g, ""), 10);
  if (isNaN(y)) return null;
  return bc ? -Math.abs(y) : y;
}
// short region labels for the register strip
const REGION_SHORT = {
  "rome-byzantium": "Rome & Byz.", "italy": "Italy", "germany": "Germany",
  "europe-west": "W. Europe", "europe-east": "E. Europe", "middle-east": "Mid. East",
  "steppe": "Steppe", "south-asia": "S. Asia", "southeast-asia": "SE Asia",
  "east-asia": "E. Asia", "africa": "Africa", "north-america": "N. America",
  "south-america": "S. America",
};

/* ---------- boot ---------- */
async function boot() {
  try {
    const [manifest, rulers] = await Promise.all([
      fetch("data/manifest.json").then((r) => r.json()),
      fetch("data/rulers.json").then((r) => r.json()),
    ]);
    state.manifest = manifest;
    state.bounds = manifest.bounds || state.bounds;
    state.regions = manifest.regions || [];
    state.rulers = rulers.slice().sort((a, b) => (a.order || 0) - (b.order || 0));
    state.rulers.forEach((r) => (state.byId[r.id] = r));
  } catch (e) {
    document.getElementById("lanes").innerHTML =
      '<p class="empty-note">The atlas could not be loaded. Run the harvester to chart <code>data/</code>.</p>';
    return;
  }
  buildSegments();
  // a year that opens on a rich moment of simultaneity
  state.year = Math.max(state.bounds.min_year, Math.min(state.bounds.max_year, 800));
  buildMeridian();
  buildRegister();
  wireChrome();
  const hash = location.hash.replace(/^#/, "");
  setYear(state.year);
  if (hash && state.byId[hash]) openDetail(hash);
}

/* ---------- meridian ---------- */
function buildMeridian() {
  const bands = document.getElementById("rule-bands");
  const legend = document.getElementById("era-legend");
  bands.innerHTML = "";
  legend.innerHTML = "";
  const eraCount = {};
  (state.manifest.eras || []).forEach((e) => (eraCount[e.key] = e.count || 0));
  state.segments.forEach((s) => {
    const b = el("div", "rule-band");
    b.dataset.era = s.key;
    b.style.flex = `${s.w} 0 0`;
    b.title = `${s.label} · ${fmtYear(s.lo)} – ${fmtYear(s.hi)}`;
    if (s.w > 0.08) b.appendChild(el("span", "rule-band-label", s.label));
    bands.appendChild(b);

    const lg = el("button");
    lg.type = "button";
    lg.dataset.era = s.key;
    const swatch = el("i");
    swatch.dataset.era = s.key;
    lg.appendChild(swatch);
    lg.appendChild(document.createTextNode(s.label));
    if (eraCount[s.key]) lg.appendChild(el("span", "lg-n", ` ${eraCount[s.key]}`));
    lg.addEventListener("click", () => jumpToEra(s));
    legend.appendChild(lg);
  });

  // ticks at canonical years within the span
  const ticks = document.getElementById("rule-ticks");
  ticks.innerHTML = "";
  const marks = [-8000, -5000, -3000, -2000, -1000, 1, 500, 1000, 1400, 1700, 1900, 2000];
  marks.filter((m) => m >= state.bounds.min_year && m <= state.bounds.max_year).forEach((m) => {
    const t = el("div", "rule-tick");
    t.style.left = (yearToPos(m) * 100) + "%";
    t.appendChild(el("span", undefined, fmtYear(m)));
    ticks.appendChild(t);
  });

  const rule = document.getElementById("rule");
  rule.setAttribute("aria-valuemin", String(state.bounds.min_year));
  rule.setAttribute("aria-valuemax", String(state.bounds.max_year));
}

function jumpToEra(seg) {
  ensureSynchronic();
  const y = seg.key === "dawn" ? -3100
    : Math.round((Math.max(seg.lo, state.bounds.min_year) + seg.hi) / 2);
  setYear(y);
}

function buildRegister() {
  const reg = document.getElementById("register");
  reg.innerHTML = "";
  state.regCells = {};
  state.regions.forEach((region) => {
    const cell = el("button", "reg-cell");
    cell.type = "button";
    cell.dataset.region = region.key;
    cell.appendChild(el("span", "rc-glyph"));
    cell.appendChild(el("span", "rc-name", REGION_SHORT[region.key] || region.label));
    const n = el("span", "rc-n", "0");
    cell.appendChild(n);
    cell.addEventListener("click", () => {
      if (cell.classList.contains("is-empty")) return;
      const lane = document.getElementById("lane-" + region.key);
      if (lane) lane.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    reg.appendChild(cell);
    state.regCells[region.key] = { cell, n };
  });
}

function updateRegister(counts) {
  if (!state.regCells) return;
  state.regions.forEach((region) => {
    const c = state.regCells[region.key];
    const k = counts[region.key] || 0;
    c.n.textContent = String(k);
    c.cell.classList.toggle("is-empty", k === 0);
    c.cell.title = `${region.label}: ${k} reigning in ${fmtYear(state.year)}`;
  });
}

let laneRaf = 0;
function setYear(y) {
  state.year = Math.max(state.bounds.min_year, Math.min(state.bounds.max_year, Math.round(y)));
  const lbl = fmtYear(state.year);
  document.getElementById("year-value").textContent = lbl;
  document.getElementById("handle-flag").textContent = lbl;
  document.getElementById("rule-handle").style.left = (yearToPos(state.year) * 100) + "%";
  const rule = document.getElementById("rule");
  rule.setAttribute("aria-valuenow", String(state.year));
  rule.setAttribute("aria-valuetext", lbl);
  // bind the year to its age, and light the active era in the legend
  const seg = eraOfYear(state.year);
  document.getElementById("year-era").textContent = seg ? "· " + seg.label : "";
  document.querySelectorAll(".era-legend button").forEach((b) =>
    b.classList.toggle("is-here", !!seg && b.dataset.era === seg.key));
  // one pass for both the reading and the register counts
  const counts = {};
  state.rulers.forEach((r) => { if (reigning(r, state.year)) counts[r.region] = (counts[r.region] || 0) + 1; });
  updateRegister(counts);
  renderReading();
  // lanes re-render is cheap, but coalesce rapid drags/sweeps to a frame
  if (laneRaf) cancelAnimationFrame(laneRaf);
  laneRaf = requestAnimationFrame(() => { if (!state.query) render(); });
}

function renderReading() {
  const reading = document.getElementById("reading");
  if (state.query) {
    const n = state.rulers.filter(matchQuery).length;
    reading.innerHTML = `<b>${n}</b> ruler${n === 1 ? "" : "s"} in the atlas match “${esc(state.query)}”.`;
    return;
  }
  if (state.mode === "atlas") {
    reading.innerHTML =
      `The whole atlas — <b>${state.rulers.length}</b> rulers across <b>${state.regions.length}</b> regions, ` +
      `${fmtYear(state.bounds.min_year)} to ${fmtYear(state.bounds.max_year)}.`;
    return;
  }
  const live = state.rulers.filter((r) => reigning(r, state.year));
  const regions = new Set(live.map((r) => r.region));
  if (!live.length) {
    // The deep "Before the Kings" stretch: empty on purpose.
    if (state.year < -3300) {
      reading.innerHTML = `This is <b>before the first kings</b> — older than writing, older than the city. ` +
        `No ruler's name survives from this deep. The earliest the record reaches is ${fmtYear(-3100)}.`;
    } else {
      reading.innerHTML = `No throne in this atlas is charted in <b>${fmtYear(state.year)}</b> — sweep the meridian to another year.`;
    }
    return;
  }
  reading.innerHTML =
    `<b>${live.length}</b> ruler${live.length === 1 ? "" : "s"} held power across ` +
    `<b>${regions.size}</b> region${regions.size === 1 ? "" : "s"} of the world.`;
}

/* ---------- rendering ---------- */
function matchQuery(r) {
  if (!state.query) return true;
  const hay = (r.name + " " + (r.realm || "") + " " + (r.region_label || "") + " " +
    (r.wp_description || "") + " " + (r.blurb || "")).toLowerCase();
  return hay.includes(state.query);
}

function render() {
  if (state.query) return renderSearch();
  if (state.mode === "atlas") return renderAtlas();
  return renderSynchronic();
}

function medallionEl(r, i) {
  const m = el("button", "medallion");
  m.type = "button";
  m.dataset.id = r.id;
  m.dataset.region = r.region;
  m.style.setProperty("--i", String(Math.min(i, 30)));

  const roundel = el("div", "med-roundel" + (r.thumbnail ? "" : " no-img"));
  if (r.thumbnail) roundel.style.backgroundImage = `url("${r.thumbnail}")`;
  else roundel.textContent = r.name[0] || "·";
  roundel.appendChild(el("span", "med-ring"));
  roundel.appendChild(el("span", "med-num", String(r.order)));
  if (r.chat_ready) {
    const s = el("span", "med-speak");
    s.title = "Speak with them";
    s.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H8l-4 4z"/></svg>';
    roundel.appendChild(s);
  }
  m.appendChild(roundel);
  m.appendChild(el("div", "med-name", r.name));
  if (r.realm) m.appendChild(el("div", "med-realm", r.realm));
  const reign = compactReign(r.reign_from ?? r.display_from, r.reign_to ?? r.display_to);
  if (reign) m.appendChild(el("div", "med-reign", reign));

  m.addEventListener("click", () => openDetail(r.id));
  return m;
}

function laneEl(region, rulers, emptyText, meta, cap) {
  const lane = el("div", "lane" + (rulers.length ? "" : " is-empty"));
  lane.dataset.region = region.key;
  lane.id = "lane-" + region.key;

  const head = el("div", "lane-head");
  const name = el("div", "lane-name");
  name.appendChild(el("span", "lane-glyph"));
  name.appendChild(el("span", undefined, region.label));
  head.appendChild(name);
  head.appendChild(el("div", "lane-meta", meta != null ? meta
    : (rulers.length ? `${rulers.length} reigning` : `${region.count} in the atlas`)));
  lane.appendChild(head);

  const track = el("div", "lane-track");
  if (rulers.length) {
    const shown = cap && rulers.length > cap ? rulers.slice(0, cap) : rulers;
    shown.forEach((r, i) => track.appendChild(medallionEl(r, i)));
    if (cap && rulers.length > cap)
      track.appendChild(el("div", "lane-none", `+${rulers.length - cap} more — search to find them`));
  } else {
    track.appendChild(el("div", "lane-none", emptyText));
  }
  lane.appendChild(track);
  return lane;
}

function renderSynchronic() {
  const root = document.getElementById("lanes");
  root.className = "lanes";
  root.innerHTML = "";
  document.getElementById("register").hidden = false;
  let silent = 0;
  state.regions.forEach((region) => {
    const live = state.rulers
      .filter((r) => r.region === region.key && reigning(r, state.year))
      .sort((a, b) => (a.display_from || 0) - (b.display_from || 0));
    // With many lanes, show only the regions with a throne this year.
    if (live.length) root.appendChild(laneEl(region, live, "", null, 60));
    else silent++;
  });
  if (silent && root.children.length) {
    const note = el("p", "atlas-note",
      `${silent} of ${state.regions.length} regions hold no throne in this atlas at ${fmtYear(state.year)}.`);
    root.appendChild(note);
  }
  root.appendChild(handoffEl());
}

function renderAtlas() {
  const root = document.getElementById("lanes");
  root.className = "lanes atlas";
  root.innerHTML = "";
  document.getElementById("register").hidden = true;
  state.regions.forEach((region) => {
    const all = state.rulers
      .filter((r) => r.region === region.key)
      .sort((a, b) => (a.display_from || 0) - (b.display_from || 0));
    root.appendChild(laneEl(region, all, "—", `${all.length} in the atlas`, 80));
  });
  root.appendChild(handoffEl());
}

function renderSearch() {
  const root = document.getElementById("lanes");
  root.className = "lanes";
  root.innerHTML = "";
  document.getElementById("register").hidden = true;
  const hits = state.rulers.filter(matchQuery);
  if (!hits.length) {
    root.appendChild(el("p", "empty-note", `No ruler matches “${state.query}”.`));
    return;
  }
  // group hits by region so results still read as a world map
  state.regions.forEach((region) => {
    const inRegion = hits.filter((r) => r.region === region.key)
      .sort((a, b) => (a.display_from || 0) - (b.display_from || 0));
    if (inRegion.length) root.appendChild(laneEl(region, inRegion, "—", `${inRegion.length} match`, 80));
  });
}

function handoffEl() {
  const h = state.manifest.handoff;
  if (!h) return el("div");
  const card = el("div", "handoff");
  card.innerHTML =
    `<h2>Before this atlas — Rome</h2>` +
    `<p>${esc(h.note)}</p>` +
    `<a class="handoff-cta" href="${h.url}" target="_blank" rel="noopener">` +
    `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M20 12H5M11 6l-6 6 6 6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>` +
    ` Cross to ${esc(h.label)}</a>`;
  return card;
}

/* ---------- detail folio ---------- */
async function getDetail(id) {
  if (state.detailCache[id]) return state.detailCache[id];
  const d = await fetch(`data/rulers/${id}.json`).then((r) => r.json());
  state.detailCache[id] = d;
  return d;
}

async function openDetail(id) {
  const r = await getDetail(id);
  state.current = r;
  const drawer = document.getElementById("detail");
  drawer.dataset.region = r.region;
  document.getElementById("detail-body").innerHTML = renderDetail(r);
  wireDetail(r);
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  const scrim = document.getElementById("scrim");
  scrim.hidden = false;
  requestAnimationFrame(() => scrim.classList.add("show"));
  drawer.scrollTop = 0;
  history.replaceState(null, "", "#" + id);
}

function closeDetail() {
  const drawer = document.getElementById("detail");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  const scrim = document.getElementById("scrim");
  scrim.classList.remove("show");
  setTimeout(() => (scrim.hidden = true), 240);
  state.current = null;
  history.replaceState(null, "", "#");
}

function bioParas(extract) {
  return esc(extract).split(/\n+/).filter(Boolean).map((p) => `<p>${p}</p>`).join("");
}

function renderDetail(r) {
  const img = r.image || r.thumbnail;
  const hero = img
    ? `<img class="d-portrait" src="${img}" alt="${esc(r.name)}" loading="lazy"/>`
    : `<div class="d-portrait no-img">${esc(r.name[0] || "·")}</div>`;
  const aka = r.wd_label && r.wd_label !== r.name ? `<p class="d-aka">also known as ${esc(r.wd_label)}</p>` : "";

  const facts = [];
  if (r.realm) facts.push(["Realm", esc(r.realm)]);
  if (r.reign_from != null || r.reign_to != null) facts.push(["Reigned", fmtRange(r.reign_from, r.reign_to)]);
  const life = fmtRange(r.birth_year, r.death_year);
  if (life !== "—") facts.push(["Lived", life]);
  if (r.birthplace) facts.push(["Born at", esc(r.birthplace)]);
  if (r.deathplace) facts.push(["Died at", esc(r.deathplace)]);
  const fam = [r.father, r.mother].filter(Boolean).map(esc).join(" &amp; ");
  if (fam) facts.push(["Parents", fam]);
  if (r.children && r.children.length) facts.push(["Children", r.children.slice(0, 8).map(esc).join(", ")]);
  const factsHtml = facts.length
    ? `<div class="d-section"><dl class="d-facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl></div>`
    : "";

  const titles = (r.positions || []).filter(Boolean);
  const titlesHtml = titles.length
    ? `<div class="d-section"><p class="d-section-label">Titles &amp; offices</p>
       <div class="d-titles">${titles.slice(0, 16).map((t) => `<span class="d-chip">${esc(t)}</span>`).join("")}</div></div>`
    : "";

  const prevR = r.predecessor_id ? state.byId[r.predecessor_id] : null;
  const nextR = r.successor_id ? state.byId[r.successor_id] : null;
  const prevName = r.predecessor || (prevR && prevR.name);
  const nextName = r.successor || (nextR && nextR.name);
  const succ = (prevName || nextName)
    ? `<div class="d-section"><p class="d-section-label">Succession in ${esc(r.realm || "their realm")}</p><div class="succession">` +
      succBtn("prev", "Preceded by", prevName, prevR && prevR.id) +
      succBtn("next", "Succeeded by", nextName, nextR && nextR.id) +
      `</div></div>`
    : "";

  const links = [];
  if (r.wikipedia_url) links.push(linkBtn(r.wikipedia_url, "Wikipedia"));
  if (r.wikidata_url) links.push(linkBtn(r.wikidata_url, "Wikidata"));
  if (r.civ_wiki) links.push(linkBtn(r.civ_wiki, "Civilization wiki"));
  const linksHtml = `<div class="d-section"><div class="d-actions">${links.join("")}</div>
    <p class="d-source-note">Biography &amp; portrait via Wikipedia / Wikimedia Commons; reign, dates &amp; relations via Wikidata.</p></div>`;

  const speak = r.chat_ready
    ? `<div class="d-section"><button class="speak-btn" id="speak-btn">
         <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H8l-4 4z"/></svg>
         Speak with ${esc(r.name)}</button></div>`
    : "";

  const bio = r.extract
    ? `<div class="d-section"><div class="d-bio">${bioParas(r.extract)}</div></div>`
    : (r.blurb ? `<div class="d-section"><div class="d-bio"><p>${esc(r.blurb)}.</p></div></div>` : "");

  const contemporaries = contemporariesHtml(r);

  return (
    `<div class="d-hero">${hero}</div>` +
    `<div class="d-titleblock">` +
    `<span class="d-eyebrow">${esc(r.region_label || "")} · ${esc(r.era_label || "")}<span class="d-cat"> · № ${r.order}</span></span>` +
    `<h1 class="d-name">${esc(r.name)}</h1>${aka}` +
    `<p class="d-dates">${esc(r.wp_description || compactReign(r.reign_from, r.reign_to))}</p>` +
    `</div>` +
    factsHtml +
    speak +
    bio +
    contemporaries +
    succ +
    titlesHtml +
    linksHtml
  );
}

function contemporariesHtml(r) {
  // who else, elsewhere in the world, reigned during this ruler's reign?
  const a = r.display_from, b = r.display_to;
  if (a == null || b == null) return "";
  const others = state.rulers.filter((x) =>
    x.id !== r.id && x.region !== r.region &&
    x.display_from != null && x.display_to != null &&
    x.display_from <= b && a <= x.display_to);
  if (!others.length) return "";
  // one representative per region, nearest in time
  const mid = (a + b) / 2;
  const byRegion = new Map();
  others.forEach((x) => {
    const cur = byRegion.get(x.region);
    const d = Math.abs(((x.display_from + x.display_to) / 2) - mid);
    if (!cur || d < cur.d) byRegion.set(x.region, { x, d });
  });
  const picks = state.regions
    .map((reg) => byRegion.get(reg.key))
    .filter(Boolean)
    .map((o) => o.x)
    .slice(0, 8);
  const chips = picks.map((x) =>
    `<button class="d-chip" data-goto="${x.id}" style="cursor:pointer">${esc(x.name)} <span style="opacity:.6">· ${esc(x.region_label)}</span></button>`
  ).join("");
  return `<div class="d-section"><p class="d-section-label">Reigning elsewhere at the same time</p>
    <div class="d-titles">${chips}</div></div>`;
}

function succBtn(dir, label, name, id) {
  if (!name) return `<button class="succ-btn ${dir}" disabled><span class="sb-dir">${label}</span><span class="sb-name">—</span></button>`;
  return `<button class="succ-btn ${dir}" data-goto="${id || ""}"${id ? "" : " disabled"}><span class="sb-dir">${label}</span><span class="sb-name">${esc(name)}</span></button>`;
}
function linkBtn(href, label) {
  return `<a class="d-link" href="${href}" target="_blank" rel="noopener">${label}
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 L17 7 M9 7h8v8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></a>`;
}

function wireDetail(r) {
  const sb = document.getElementById("speak-btn");
  if (sb) sb.addEventListener("click", () => window.PastChat.open(r));
  document.querySelectorAll("[data-goto]").forEach((b) => {
    const id = b.dataset.goto;
    if (id) b.addEventListener("click", () => openDetail(id));
  });
}

/* ---------- chrome ---------- */
function setMode(mode) {
  state.mode = mode;
  document.getElementById("mode-toggle").textContent =
    mode === "atlas" ? "back to a single year" : "see the whole atlas";
  renderReading();
  render();
}

function wireChrome() {
  document.getElementById("detail-close").addEventListener("click", closeDetail);
  document.getElementById("scrim").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.current) closeDetail();
  });

  // search
  const search = document.getElementById("search");
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      state.query = search.value.trim().toLowerCase();
      renderReading();
      render();
    }, 120);
  });

  // type a year directly (precision across 11,000 years)
  const yv = document.getElementById("year-value");
  const yi = document.getElementById("year-input");
  const openYearInput = () => {
    ensureSynchronic();
    yi.value = String(state.year);
    yv.hidden = true; yi.hidden = false;
    yi.focus(); yi.select();
  };
  const commitYearInput = () => {
    if (yi.hidden) return;
    const y = parseYear(yi.value);
    yi.hidden = true; yv.hidden = false;
    if (y != null) setYear(y);
  };
  yv.addEventListener("click", openYearInput);
  yi.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitYearInput(); yv.focus(); }
    else if (e.key === "Escape") { yi.hidden = true; yv.hidden = false; yv.focus(); }
  });
  yi.addEventListener("blur", commitYearInput);

  // theme
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("otp-theme", next); } catch (e) {}
  });

  // mode + steps + sweep
  document.getElementById("mode-toggle").addEventListener("click", () =>
    setMode(state.mode === "atlas" ? "synchronic" : "atlas"));
  document.getElementById("step-back").addEventListener("click", () => { ensureSynchronic(); setYear(state.year - 1); });
  document.getElementById("step-fwd").addEventListener("click", () => { ensureSynchronic(); setYear(state.year + 1); });
  document.getElementById("sweep").addEventListener("click", toggleSweep);

  wireRule();
}

function ensureSynchronic() {
  if (state.query) { state.query = ""; document.getElementById("search").value = ""; }
  if (state.mode !== "synchronic") setMode("synchronic");
}

/* dragging / clicking / keying the meridian rule */
function wireRule() {
  const rule = document.getElementById("rule");
  const ghost = document.getElementById("rule-ghost");
  const ghostLabel = document.getElementById("rule-ghost-label");
  let dragging = false;

  const posFromX = (clientX) => {
    const rect = rule.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  };
  const onDown = (e) => {
    dragging = true;
    ghost.hidden = true;
    stopSweep();
    ensureSynchronic();
    rule.setPointerCapture && e.pointerId != null && rule.setPointerCapture(e.pointerId);
    setYear(posToYear(posFromX(e.clientX)));
    e.preventDefault();
  };
  const onMove = (e) => {
    const p = posFromX(e.clientX);
    if (dragging) { setYear(posToYear(p)); return; }
    // a faint "sighting" of the year under the cursor, before you commit
    ghost.hidden = false;
    ghost.style.left = (p * 100) + "%";
    ghostLabel.textContent = fmtYear(posToYear(p));
  };
  const onUp = () => { dragging = false; };

  rule.addEventListener("pointerdown", onDown);
  rule.addEventListener("pointermove", onMove);
  rule.addEventListener("pointerleave", () => { ghost.hidden = true; });
  window.addEventListener("pointerup", onUp);

  rule.addEventListener("keydown", (e) => {
    const big = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") { ensureSynchronic(); setYear(state.year - big); e.preventDefault(); }
    else if (e.key === "ArrowRight" || e.key === "ArrowUp") { ensureSynchronic(); setYear(state.year + big); e.preventDefault(); }
    else if (e.key === "Home") { ensureSynchronic(); setYear(state.bounds.min_year); e.preventDefault(); }
    else if (e.key === "End") { ensureSynchronic(); setYear(state.bounds.max_year); e.preventDefault(); }
  });
}

/* "let time drift" — a constant-screen-speed sweep across the meridian */
let sweepRaf = 0, sweepLast = 0;
function toggleSweep() { state.sweeping ? stopSweep() : startSweep(); }
function startSweep() {
  ensureSynchronic();
  state.sweeping = true;
  document.getElementById("sweep").setAttribute("aria-pressed", "true");
  sweepLast = 0;
  const tick = (ts) => {
    if (!state.sweeping) return;
    if (!sweepLast) sweepLast = ts;
    const dt = ts - sweepLast; sweepLast = ts;
    let pos = yearToPos(state.year) + dt * 0.00006;   // ~16s full sweep
    if (pos >= 1) pos = 0;
    setYear(posToYear(pos));
    sweepRaf = requestAnimationFrame(tick);
  };
  sweepRaf = requestAnimationFrame(tick);
}
function stopSweep() {
  state.sweeping = false;
  if (sweepRaf) cancelAnimationFrame(sweepRaf);
  document.getElementById("sweep").setAttribute("aria-pressed", "false");
}

boot();
