/* chat.js — the avatar shell (the séance).
 *
 * The avatar is answered by the shared people.ofthepast.org API
 * (chat.people.ofthepast.org, repo openfantasymap/avatars) — the one chat
 * service behind all the sibling ruler galleries. It grounds the avatar on this
 * atlas's published record and replies through an OpenAI-compatible model. What
 * lives here:
 *   1. buildPersonaPrompt(ruler) — a client-side mirror of the server's
 *      grounding prompt, powering the live "how this avatar is grounded" preview.
 *   2. a templated in-character greeting, so the avatar has a voice on open.
 *
 * It never fabricates history: a message POSTs to the API; if the backend is
 * unreachable (or not yet deployed) the reply is a self-aware holding message,
 * not invented history.
 */
(function () {
  const API = "https://chat.people.ofthepast.org";   // shared avatars API
  const SITE = "past";                                // this gallery's site key
  const HOLDING =
    "My full voice is not yet restored to this hall — the oracle that would let me " +
    "answer you is still being kindled. Return soon, and I shall speak with you properly.";

  function fmtYear(y) {
    if (y === null || y === undefined) return null;
    return y < 0 ? `${-y} BC` : `AD ${y}`;
  }
  function range(a, b) {
    const fa = fmtYear(a), fb = fmtYear(b);
    if (fa && fb) return fa === fb ? fa : `${fa} – ${fb}`;
    return fa || fb || "dates uncertain";
  }

  // The grounding prompt. The backend will send this as the system message; the
  // avatar must stay faithful to it. Mirrors chat/app/persona.py.
  function buildPersonaPrompt(r) {
    const lines = [];
    const who = r.wp_description ? `, ${r.wp_description.toLowerCase()}` : "";
    lines.push(`You are ${r.name}${who}. You speak in the first person, as yourself.`);
    lines.push("");
    lines.push("Hold faithfully to this record; do not invent biography beyond it or beyond well-established history:");
    if (r.birth_year || r.death_year) lines.push(`- Lived: ${range(r.birth_year, r.death_year)}.`);
    if (r.reign_from || r.reign_to) lines.push(`- Reigned: ${range(r.reign_from, r.reign_to)}.`);
    if (r.realm) lines.push(`- Realm: ${r.realm}.`);
    if (r.region_label) lines.push(`- Part of the world: ${r.region_label}.`);
    if (r.birthplace) lines.push(`- Born at: ${r.birthplace}.`);
    if (r.predecessor) lines.push(`- Came after: ${r.predecessor}.`);
    if (r.successor) lines.push(`- Followed by: ${r.successor}.`);
    if (r.father || r.mother) lines.push(`- Parents: ${[r.father, r.mother].filter(Boolean).join(" and ")}.`);
    if (r.children && r.children.length) lines.push(`- Children: ${r.children.slice(0, 6).join(", ")}.`);
    if (r.positions && r.positions.length) lines.push(`- Titles held: ${r.positions.slice(0, 8).join(", ")}.`);
    if (r.extract) {
      lines.push("");
      lines.push("Biography (from Wikipedia — your memory of your own life):");
      lines.push(r.extract);
    }
    lines.push("");
    lines.push("Manner: measured, period- and culture-appropriate, dignified but never modern. " +
      "Speak as someone of your own time and place. If asked about events after your death, about other " +
      "parts of the world you could not have known, or about anything beyond the record, admit the limits " +
      "of your knowledge. Never claim knowledge of the modern world. Keep replies to a few sentences. " +
      "Defer always to the historical record.");
    return lines.join("\n");
  }

  function greeting(r) {
    const reign = (r.reign_from != null || r.reign_to != null)
      ? ` I reigned ${range(r.reign_from, r.reign_to)}.` : "";
    return `So — you would speak with ${r.name}.${reign} Put your question, and I shall answer as the record of my life allows.`;
  }

  let host = null;
  function ensureHost() {
    if (host) return host;
    host = document.createElement("div");
    host.className = "chat-host";
    host.hidden = true;
    host.innerHTML = `
      <div class="chat-scrim" data-close></div>
      <div class="chat-panel" role="dialog" aria-modal="true" aria-label="Speak with a ruler">
        <button class="chat-close" data-close aria-label="Close">&times;</button>
        <div class="chat-head">
          <div class="chat-avatar" id="chat-avatar"></div>
          <div>
            <div class="chat-name" id="chat-name"></div>
            <div class="chat-sub">an avatar, grounded in the record</div>
          </div>
        </div>
        <div class="chat-log" id="chat-log"></div>
        <details class="chat-grounding">
          <summary>How this avatar is grounded</summary>
          <p class="chat-grounding-note">When the oracle is connected, the model is given only this — the facts and biography harvested from Wikidata &amp; Wikipedia — and told to stay faithful to it:</p>
          <pre id="chat-prompt"></pre>
        </details>
        <form class="chat-form" id="chat-form">
          <input id="chat-input" autocomplete="off" placeholder="Ask your question…" />
          <button type="submit" aria-label="Send">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11.5 L21 3 L13 21 L11 13 Z" fill="currentColor"/></svg>
          </button>
        </form>
        <div class="chat-foot" id="chat-foot"></div>
      </div>`;
    document.body.appendChild(host);
    host.querySelectorAll("[data-close]").forEach((el) =>
      el.addEventListener("click", close));
    document.addEventListener("keydown", (e) => {
      if (!host.hidden && e.key === "Escape") close();
    });
    return host;
  }

  let current = null;
  function bubble(role, text) {
    const log = host.querySelector("#chat-log");
    const b = document.createElement("div");
    b.className = "chat-msg " + role;
    b.textContent = text;
    log.appendChild(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }

  function open(ruler) {
    current = ruler;
    ensureHost();
    const av = host.querySelector("#chat-avatar");
    const img = ruler.thumbnail || ruler.image;
    av.style.backgroundImage = img ? `url("${img}")` : "";
    av.classList.toggle("no-img", !img);
    av.textContent = img ? "" : (ruler.name[0] || "·");
    host.querySelector("#chat-name").textContent = ruler.name;
    host.querySelector("#chat-log").innerHTML = "";
    host.querySelector("#chat-prompt").textContent = buildPersonaPrompt(ruler);
    host.querySelector("#chat-foot").innerHTML =
      `The avatar's voice is being awakened. Until then, read <a href="${ruler.wikipedia_url || "#"}" target="_blank" rel="noopener">the full life on Wikipedia</a>.`;
    host.hidden = false;
    document.body.style.overflow = "hidden";
    bubble("them", greeting(ruler));
    const input = host.querySelector("#chat-input");
    setTimeout(() => input.focus(), 60);

    const history = [];
    const form = host.querySelector("#chat-form");
    form.onsubmit = async (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      bubble("you", v);
      history.push({ role: "user", content: v });
      input.value = "";
      const pending = bubble("them", "…");
      pending.style.opacity = "0.55";
      try {
        const res = await fetch(`${API}/chat/${SITE}/${ruler.id}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ messages: history }),
        });
        if (!res.ok) throw new Error("status " + res.status);
        const data = await res.json();
        pending.style.opacity = "";
        pending.textContent = data.reply;
        history.push({ role: "assistant", content: data.reply });
      } catch (err) {
        // Backend not yet awakened (or unreachable) — stay in character, never invent.
        pending.style.opacity = "";
        pending.textContent = HOLDING;
      }
    };
  }

  function close() {
    if (!host) return;
    host.hidden = true;
    document.body.style.overflow = "";
    current = null;
  }

  window.PastChat = { open, close, buildPersonaPrompt };
})();
