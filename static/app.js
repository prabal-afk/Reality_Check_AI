/* RealityCheck AI - frontend (plain JavaScript, no framework).
   All user/server text is inserted with textContent, never innerHTML, so a claim such as
   "<script>alert(1)</script>" is displayed as text and cannot run. */
"use strict";

const view = document.getElementById("view");
const MIN_LEN = 10, MAX_LEN = 500;
const EXAMPLES = [
  "The Great Wall of China is visible from space with the naked eye.",
  "Humans only use 10% of their brain.",
  "The Earth is flat.",
  "The Moon landing was faked.",
  "Mount Everest is the highest mountain above sea level.",
  "Mount Everest is the tallest mountain in the world.",
];

/* ---------- tiny helpers ---------- */
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  let body = null;
  try { body = await res.json(); } catch (e) { /* non-JSON error */ }
  if (!res.ok) throw new Error((body && body.error) || `Request failed (${res.status}).`);
  return body;
}

function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s.includes("T") ? s : s.replace(" ", "T") + "Z");
  return isNaN(d) ? s : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function setActive(name) {
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("active", a.dataset.nav === name));
}

/* ---------- view: check ---------- */
function viewCheck() {
  setActive("check");
  const ta = el("textarea", { id: "claim", maxlength: 2000, placeholder: "Type or paste one factual claim, e.g. “The Great Wall of China is visible from space.”" });
  const count = el("span", { class: "count", id: "count" }, `0 / ${MAX_LEN}`);
  const msg = el("div", { class: "msg", id: "message", role: "alert" });
  const btn = el("button", { type: "submit", id: "check-btn" }, "Check claim");

  const update = () => {
    const n = ta.value.trim().length;
    count.textContent = `${n} / ${MAX_LEN}`;
    count.classList.toggle("bad", n > MAX_LEN);
  };
  ta.addEventListener("input", update);

  const form = el("form", { class: "card", novalidate: "novalidate",
    onsubmit: async (ev) => {
      ev.preventDefault();
      msg.textContent = "";
      const text = ta.value.trim();
      if (text.length < MIN_LEN) { msg.textContent = `Please enter at least ${MIN_LEN} characters.`; return; }
      if (text.length > MAX_LEN) { msg.textContent = `The claim is too long; the limit is ${MAX_LEN} characters.`; return; }
      btn.disabled = true;
      btn.replaceChildren(el("span", { class: "spinner" }), "Checking sources…");
      try {
        const result = await api("/api/claims", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ claim_text: text }),
        });
        location.hash = `#/result/${result.id}`;
      } catch (e) {
        msg.textContent = e.message;
        btn.disabled = false;
        btn.replaceChildren("Check claim");
      }
    } },
    el("label", { for: "claim" }, "Claim to check"),
    ta,
    el("div", { class: "row" }, count, btn),
    msg,
    el("div", { class: "chips", "aria-label": "Example claims" },
      EXAMPLES.map(t => el("button", { type: "button", class: "chip", onclick: () => { ta.value = t; update(); ta.focus(); } }, t))),
  );

  view.replaceChildren(
    el("h1", {}, "Check a claim in under a minute."),
    el("p", { class: "lede" }, "Paste a claim you saw in a message, post or headline. RealityCheck AI collects evidence, shows who supports and who contradicts it, and explains how it reached a verdict."),
    form,
    el("div", { class: "steps" },
      el("div", { class: "step" }, el("b", {}, "1 · Evidence"), "Sources are retrieved for the exact claim, never invented."),
      el("div", { class: "step" }, el("b", {}, "2 · Credibility"), "Each source gets a tier: 1 official/fact-checker, 2 reputable, 3 other."),
      el("div", { class: "step" }, el("b", {}, "3 · Verdict"), "Supported, Refuted, Mixed or Unverifiable, with the working shown."),
    ),
  );
}

/* ---------- view: result ---------- */
function sourceCard(ev) {
  return el("div", { class: "src" },
    el("div", {}, el("span", { class: `tier t${ev.credibility_tier}`, title: "Credibility tier" }, `Tier ${ev.credibility_tier}`),
      el("a", { class: "t", href: ev.url, target: "_blank", rel: "noopener noreferrer" }, ev.source_name)),
    el("p", {}, ev.snippet),
    el("div", { class: "meta" }, ev.domain, ev.published_date ? ` · updated ${ev.published_date}` : " · date not stated"),
    ev.reason ? el("div", { class: "why" }, "Why this label: " + ev.reason) : null,
  );
}

function column(cls, title, items) {
  return el("section", { class: `col ${cls}` },
    el("h2", {}, `${title} (${items.length})`),
    items.length ? items.map(sourceCard) : el("div", { class: "empty" }, "No sources on this side."));
}

async function viewResult(id) {
  setActive("");
  view.replaceChildren(el("p", { class: "lede" }, "Loading result…"));
  let c;
  try { c = await api(`/api/claims/${id}`); }
  catch (e) { view.replaceChildren(el("h1", {}, "Result not found"), el("p", { class: "lede" }, e.message), el("a", { href: "#/" }, "Check another claim")); return; }

  const sup = c.evidence.filter(e => e.stance === "SUPPORTS");
  const ref = c.evidence.filter(e => e.stance === "REFUTES");
  const neu = c.evidence.filter(e => e.stance === "NEUTRAL");
  const b = c.breakdown;
  const pct = c.confidence == null ? 0 : Math.round(c.confidence * 100);

  const fbMsg = el("div", { class: "meta", id: "fb-msg", role: "status" });
  const comment = el("input", { type: "text", maxlength: 300, placeholder: "Optional comment", "aria-label": "Feedback comment" });
  const sendFb = async (helpful) => {
    try {
      await api(`/api/claims/${c.id}/feedback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ helpful, comment: comment.value }) });
      fbMsg.textContent = "Thanks, your feedback was saved.";
    } catch (e) { fbMsg.textContent = e.message; }
  };

  view.replaceChildren(
    el("div", { class: "stack" },
      el("a", { href: "#/" }, "← Check another claim"),
      el("div", { class: `card verdict ${c.verdict}`, id: "verdict-card" },
        el("div", {}, el("span", { class: `badge ${c.verdict}`, id: "verdict" }, c.verdict.toUpperCase())),
        el("div", {},
          el("p", { class: "claim-text", id: "claim-text" }, c.claim_text),
          c.confidence != null
            ? el("div", {}, el("div", { class: "meta" }, `Confidence: ${c.confidence_label} (${pct}%)`),
                el("div", { class: "meter", role: "img", "aria-label": `Confidence ${pct} percent` }, el("i", { style: `width:${pct}%` })))
            : el("div", { class: "meta" }, c.verdict === "Mixed" ? "Confidence: not rated, the evidence is split." : "Confidence: not rated, too little evidence."),
          el("p", { id: "explanation" }, c.explanation),
          el("div", { class: "meta" }, `Check #${c.id} · ${fmtDate(c.created_at)} · evidence from: ${c.retrieval_mode}`),
        ),
      ),
      el("div", { class: "cols" }, column("sup", "Supporting evidence", sup), column("ref", "Conflicting evidence", ref)),
      neu.length ? el("details", {}, el("summary", {}, `Not directly relevant (${neu.length})`), neu.map(sourceCard)) : null,
      el("details", {},
        el("summary", {}, "How was this verdict calculated?"),
        el("p", { class: "meta" }, "Source weight: Tier 1 = 3, Tier 2 = 2, Tier 3 = 1" + (b.time_sensitive ? "; time-sensitive claim, so evidence older than 2 years counts half." : ".") +
          " Verdict: ≥ 70% of the weighted evidence on one side gives Supported/Refuted; otherwise Mixed; fewer than 2 relevant sources gives Unverifiable."),
        el("div", { class: "tablewrap" }, el("table", {},
          el("thead", {}, el("tr", {}, ["Side", "Sources", "Weighted score", "Share"].map(h => el("th", {}, h)))),
          el("tbody", {},
            el("tr", {}, el("td", {}, "Supports"), el("td", {}, b.supports_count), el("td", {}, b.supports_weight), el("td", {}, Math.round(b.share_support * 100) + "%")),
            el("tr", {}, el("td", {}, "Refutes"), el("td", {}, b.refutes_count), el("td", {}, b.refutes_weight), el("td", {}, Math.round(b.share_refute * 100) + "%")),
            el("tr", {}, el("td", {}, "Not relevant"), el("td", {}, b.neutral_count), el("td", {}, "-"), el("td", {}, "-")))))),
      el("div", { class: "card" }, el("h2", {}, "Was this result helpful?"),
        el("div", { class: "fb" },
          el("button", { class: "ghost", type: "button", onclick: () => sendFb(true) }, "Helpful"),
          el("button", { class: "ghost", type: "button", onclick: () => sendFb(false) }, "Not helpful"), comment),
        fbMsg),
    ));
}

/* ---------- view: history ---------- */
async function viewHistory() {
  setActive("history");
  const state = { q: "", verdict: "", page: 1 };
  const list = el("div", { class: "card", id: "history-list" });
  const pager = el("div", { class: "pager" });

  const load = async () => {
    const params = new URLSearchParams({ page: state.page, per_page: 8 });
    if (state.q) params.set("q", state.q);
    if (state.verdict) params.set("verdict", state.verdict);
    try {
      const data = await api("/api/claims?" + params);
      list.replaceChildren(...(data.items.length ? data.items.map(i =>
        el("div", { class: "hist" },
          el("div", {}, el("a", { href: `#/result/${i.id}` }, i.claim_text), el("div", { class: "meta" }, `#${i.id} · ${fmtDate(i.created_at)}`)),
          el("span", { class: `badge ${i.verdict}`, style: "font-size:.85rem;padding:5px 12px" }, i.verdict))) :
        [el("div", { class: "empty" }, state.q || state.verdict ? "No checks match your filters." : "No claims checked yet. Check one first.")]));
      const last = Math.max(1, Math.ceil(data.total / data.per_page));
      pager.replaceChildren(
        el("button", { class: "ghost", disabled: state.page <= 1 ? "disabled" : false, onclick: () => { state.page--; load(); } }, "Previous"),
        el("span", { class: "meta" }, `Page ${data.page} of ${last} · ${data.total} checks`),
        el("button", { class: "ghost", disabled: state.page >= last ? "disabled" : false, onclick: () => { state.page++; load(); } }, "Next"));
    } catch (e) { list.replaceChildren(el("div", { class: "msg" }, e.message)); }
  };

  let timer;
  const search = el("input", { type: "search", placeholder: "Search past claims", "aria-label": "Search past claims",
    oninput: (e) => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value.trim(); state.page = 1; load(); }, 250); } });
  const sel = el("select", { "aria-label": "Filter by verdict", onchange: (e) => { state.verdict = e.target.value; state.page = 1; load(); } },
    el("option", { value: "" }, "All verdicts"), ["Supported", "Refuted", "Mixed", "Unverifiable"].map(v => el("option", { value: v }, v)));

  view.replaceChildren(el("h1", {}, "History"), el("p", { class: "lede" }, "Every check is saved in the database, so you can reopen it later."),
    el("div", { class: "filters" }, search, sel), list, pager);
  load();
}

/* ---------- view: sources ---------- */
async function viewSources() {
  setActive("sources");
  view.replaceChildren(el("h1", {}, "Trusted sources"),
    el("p", { class: "lede" }, "Credibility tiers used to weight evidence. Unknown sites default to Tier 3. A tier is a guide, not a guarantee."));
  try {
    const data = await api("/api/sources");
    view.append(el("div", { class: "card tablewrap" }, el("table", { id: "sources-table" },
      el("thead", {}, el("tr", {}, ["Tier", "Source", "Domain", "Notes"].map(h => el("th", {}, h)))),
      el("tbody", {}, data.items.map(s => el("tr", {},
        el("td", {}, el("span", { class: `tier t${s.tier}` }, `Tier ${s.tier}`)), el("td", {}, s.name), el("td", {}, s.domain), el("td", {}, s.notes || "")))))));
  } catch (e) { view.append(el("div", { class: "msg" }, e.message)); }
}

/* ---------- router ---------- */
function route() {
  const h = location.hash || "#/";
  let m;
  if ((m = h.match(/^#\/result\/(\d+)$/))) viewResult(m[1]);
  else if (h === "#/history") viewHistory();
  else if (h === "#/sources") viewSources();
  else viewCheck();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
route();
