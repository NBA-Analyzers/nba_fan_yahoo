const pathParts = location.pathname.split("/").filter(Boolean);
const espn = pathParts[0] === "draft" && pathParts[1] === "espn";   // /draft/espn/<id> follows an ESPN league
const leagueId = espn ? pathParts[2] : pathParts[1];
// /manual/<id> is a hand-entered league; /draft/<id> follows Yahoo
const manual = pathParts[0] === "manual";
const base = `/${manual ? "manual" : "draft"}/${espn ? "espn/" : ""}${leagueId}`;
const POLL_MS = 10000;
const AUCTION_POLL_MS = 4000; // bid clocks are short, so check Yahoo more often
const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(`draft:${leagueId}:${key}`)) ?? fallback; }
    catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`draft:${leagueId}:${key}`, JSON.stringify(value)); } catch (e) {}
  },
};

let punts = store.get("punts", []);
let mock = manual ? false : store.get("mock", false);
let jevMode = store.get("jevMode", "manual");
let preference = store.get("preference", "");
let draftPosition = store.get("draftPosition", "");
let mockTaken = store.get("mockTaken", []);
let mockMine = store.get("mockMine", []);
let mockCosts = store.get("mockCosts", {});
let nominee = store.get("nominee", "");
let autoPunts = store.get("autoPunts", false);
let lastData = null;
let timer = null;
let activePoll = null;
let playerListLoaded = false;

function zColor(z) {
  const strength = Math.min(Math.abs(z) / 2.5, 1);
  const rgb = z >= 0 ? "31,157,85" : "214,69,69";
  return `rgba(${rgb},${(0.12 + strength * 0.55).toFixed(2)})`;
}

function fetchState() {
  const punted = encodeURIComponent(punts.join(","));
  const url = `${base}/state`;
  return mock
    ? jsonRequest(url, "POST", {
        mock: true, punts, mock_taken: mockTaken, mock_mine: mockMine,
        mode: jevMode, preference, draft_position: draftPosition,
        nominee, mock_costs: mockCosts, auto_punts: autoPunts,
      })
    : fetchJson(`${url}?punts=${punted}&mode=${jevMode}&preference=${encodeURIComponent(preference)}&draft_position=${draftPosition}&nominee=${encodeURIComponent(nominee)}&auto_punts=${autoPunts ? 1 : 0}`);
}

async function refresh() {
  try {
    lastData = await fetchState();
    showError("");
    render(lastData);
    if (!mock && pollInterval() !== activePoll) applyMode();
  } catch (e) {
    showError("Could not load draft data: " + e.message);
  }
}

function render(d) {
  $("title").textContent = d.league_name ? `Draft help · ${d.league_name}` : "Draft help";
  renderStatus(d);
  renderWarnings(d);
  renderPunts(d);
  renderNominee(d);
  renderMoney(d);
  renderAdvice(d);
  renderDecision(d);
  renderTable(d);
  renderRoster(d);
  renderPicks(d);
  if (manual) renderManual(d);
}

function renderStatus(d) {
  const s = $("status");
  s.textContent = "";
  const parts = [];
  if (manual) parts.push(d.draft_status === "finished" ? "Draft finished" : "Manual league");
  else if (d.mock) parts.push("Practice mode");
  else if (d.draft_status) parts.push(`Draft: ${d.draft_status}`);
  parts.push(`${d.taken_names.length} players taken`);
  s.append(parts.join(" · "));
  if (d.is_auction) {
    s.append(" · Your budget left: ", el("strong", `$${d.my_budget_left}`));
  } else if (d.my_next_pick) {
    const n = d.picks_until_my_turn;
    s.append(" · ", el("strong", n === 0 ? "You're on the clock!" : `You pick in ${n} pick${n === 1 ? "" : "s"}`),
      ` (pick #${d.my_next_pick})`);
  }
}

function renderWarnings(d) {
  const lines = [];
  if (d.taken_unmatched && d.taken_unmatched.length) {
    lines.push(`No stats match for drafted players: ${d.taken_unmatched.join(", ")}. If they are in the pool under another spelling, they may still show as available.`);
  }
  const warn = $("warn");
  warn.textContent = lines.join(" ");
  warn.style.display = lines.length ? "block" : "none";
  // Snake drafts: ask for the manager's slot if Yahoo doesn't expose it
  $("slotbox").style.display = !manual && !d.is_auction && (d.needs_draft_position || draftPosition) ? "" : "none";
}

// Categories skipped right now: the ones you tapped plus any the agent chose for you
function isSkipped(cat) {
  return ((lastData && lastData.effective_punts) || punts).includes(cat);
}

function renderPunts(d) {
  const box = $("punts");
  box.textContent = "";
  for (const cat of d.categories) {
    const byYou = punts.includes(cat);
    const byAgent = !byYou && (d.effective_punts || []).includes(cat);
    const chip = el("label", cat, "punt" + (byYou ? " on" : byAgent ? " on auto" : ""));
    if (byAgent) chip.title = "Chosen for you";
    chip.onclick = () => togglePunt(cat);
    box.append(chip);
  }

  const hint = $("suggest");
  hint.textContent = "";
  const idea = d.build_suggestion;
  if (!idea) return;
  const note = el("div", undefined, "idea");
  const avg = idea.avg_z.toFixed(1);
  if (d.auto_punts) {
    note.append("Skipping ", el("b", idea.category), ` for you, because your players average ${avg} there. Best available now: ${idea.if_skipped.join(", ")}.`);
  } else {
    note.append("Idea: skip ", el("b", idea.category), `. Your players average ${avg} there, your weakest category. `,
      `If you skip it, the best available change from ${idea.now.join(", ")} to ${idea.if_skipped.join(", ")}.`);
    const button = el("button", `Skip ${idea.category}`, "btn mini");
    button.onclick = () => togglePunt(idea.category);
    note.append(el("br"), button);
  }
  hint.append(note);
}

function togglePunt(cat) {
  punts = punts.includes(cat) ? punts.filter((c) => c !== cat) : [...punts, cat];
  store.set("punts", punts);
  refresh();
}

function renderDecision(d) {
  const box = $("decision");
  box.textContent = "";
  const dec = d.decision;
  if (!dec) { box.style.display = "none"; return; }
  box.style.display = "";

  const title = el("div");
  const label = dec.source === "jev" ? "Jev picks " : "Top pick: ";
  title.append(label, el("span", dec.pick, "pick"));
  if (dec.confidence != null) title.append(` (${Math.round(dec.confidence * 100)}% sure)`);
  title.append(el("span", dec.needs_manager ? "you decide" : "auto-pick", "tag" + (dec.needs_manager ? " manager" : "")));
  box.append(title);

  if (dec.reason) box.append(el("div", dec.reason, "meta"));
  if (dec.note) box.append(el("div", dec.note, "meta"));
  if (dec.needs_manager && dec.options.length > 1) {
    box.append(el("div", "Likeliest: " + dec.options.map((o) => `${o.name} ${Math.round(o.probability * 100)}%`).join(" · "), "meta"));
  }
  if (!dec.agrees_with_engine) box.append(el("div", `The ranking's #1 is ${dec.engine_pick}.`, "meta"));
}

function setNominee(name, scroll) {
  nominee = name;
  store.set("nominee", nominee);
  $("nominee").value = name;
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
  refresh();
}

async function ensurePlayerList() {
  if (playerListLoaded) return;
  playerListLoaded = true;
  try {
    const data = await fetchJson(`${base}/players`);
    const list = $("playernames");
    list.textContent = "";
    (data.players || []).forEach((n) => { const o = document.createElement("option"); o.value = n; list.append(o); });
  } catch (e) { playerListLoaded = false; }
}

function fact(label, value) {
  const s = el("span", label + " ");
  s.append(el("b", value));
  return s;
}

function renderNominee(d) {
  $("nomineebox").style.display = d.is_auction ? "" : "none";
  if (!d.is_auction) return;
  ensurePlayerList();
  if (document.activeElement !== $("nominee")) $("nominee").value = nominee;

  const box = $("nominee-card");
  box.textContent = "";
  const c = d.nominee_card;
  if (!c) {
    box.append(el("div", "Type the name of the player who was just nominated. You will see how much to bid. Tip: press / to jump to this box.", "hint"));
    return;
  }
  if (!c.found) {
    box.append(el("div", `No player called "${c.query}" in the list. Check the spelling.`, "notice bad"));
    return;
  }

  const card = el("div", undefined, "bidcard");
  const who = el("div", c.name, "who");
  who.append(el("small", `${c.team || "FA"}${c.my_rank ? ` · #${c.my_rank} for your team` : ""}`));
  card.append(who);

  if (c.sold) {
    card.append(el("div", c.sold_to ? `Sold to ${c.sold_to}${c.cost ? ` for $${c.cost}` : ""}.` : "Already drafted.", "big fair"));
    box.append(card);
    return;
  }

  const words = { target: "Good deal for you", fair: "Fair price", overpriced: "Probably too pricey" };
  const big = el("div", undefined, `big ${c.verdict}`);
  big.append(`Bid up to $${c.bid_up_to}`, el("span", words[c.verdict], "verdict"));
  card.append(big);

  const facts = el("div", undefined, "facts");
  facts.append(fact("Worth to you", `$${c.my_value}`), fact("Others will likely pay", `about $${c.market}`));
  if (c.yahoo_avg_cost != null) facts.append(fact("Yahoo's average", `$${Math.round(c.yahoo_avg_cost)}`));
  facts.append(fact("You can bid at most", `$${c.max_bid}`));
  card.append(facts);
  if (c.bid_up_to < c.my_value) card.append(el("div", "Your money limits this bid.", "line hint"));
  if (c.walk_away_above != null) {
    card.append(el("div", `Walk away above $${c.walk_away_above}.`, "line"));
    if (c.spots_after_bid > 0) {
      const text = `If you win at $${c.bid_up_to}: $${c.left_after_bid} left for ${c.spots_after_bid} spots ` +
        `(about $${c.per_spot_after_bid} each; the room averages $${c.room_avg_per_spot}).`;
      card.append(el("div", c.thin_after_bid ? `${text} That leaves you thin for the rest of the draft.` : text,
        c.thin_after_bid ? "line notice bad" : "line hint"));
    }
  }

  if (c.strengths.length || c.weaknesses.length) {
    const line = el("div", undefined, "line");
    if (c.strengths.length) line.append("Strong in ", el("b", c.strengths.join(", ")), ". ");
    if (c.weaknesses.length) line.append("Weak in ", el("b", c.weaknesses.join(", ")), ".");
    card.append(line);
  }
  if (c.fills_open_slot === true) card.append(el("div", "He fills one of your open starting spots.", "line"));
  else if (c.fills_open_slot === false) card.append(el("div", "No open starting spot for him. He would be bench or flex.", "line hint"));

  if (c.rivals_who_can_pay_market != null) {
    const total = (d.teams || []).filter((t) => !t.is_mine).length;
    const richest = c.richest_rivals.map((r) => `${r.name} ($${r.max_bid})`).join(", ");
    card.append(el("div", `${c.rivals_who_can_pay_market} of ${total} rivals can afford about $${c.market}. Most money: ${richest}.`, "line hint"));
  }

  if (mock) {
    const btns = el("div", undefined, "mini-btns");
    const lost = el("button", "Someone else won", "btn secondary mini");
    lost.onclick = () => markMock(c.name, false);
    const won = el("button", "I won him", "btn mini");
    won.onclick = () => markMock(c.name, true);
    btns.append(lost, won);
    card.append(btns);
  }
  box.append(card);
}

const ADVICE_LABELS = { cash: "Your cash", rivals: "Rivals", nominate: "Nominate", drain: "Make them spend" };

function renderAdvice(d) {
  const items = d.cash_advice || [];
  $("advicecard").style.display = d.is_auction && items.length ? "" : "none";
  const list = $("advice");
  list.textContent = "";
  items.forEach((item) => {
    const li = el("li");
    li.append(el("b", (ADVICE_LABELS[item.kind] || "Tip") + ": "), item.text);
    list.append(li);
  });
}

function renderMoney(d) {
  const card = $("moneycard");
  card.style.display = d.is_auction ? "" : "none";
  if (!d.is_auction) return;
  const box = $("money");
  box.textContent = "";
  box.append(el("div", `$${d.my_budget_left} left`, "money-big"));
  box.append(el("div", `You can bid at most $${d.auction.max_bid}. ${d.my_open_spots} roster spots still open.`, "money-line"));

  const p = d.auction.inflation_pct;
  box.append(el("div", Math.abs(p) < 1 ? "Prices are about where they started."
    : `Players now cost about ${Math.abs(p)}% ${p > 0 ? "more" : "less"} than before the draft.`, "money-line"));

  if (d.teams && d.teams.length) {
    const rivals = d.teams.filter((t) => !t.is_mine).sort((a, b) => b.max_bid - a.max_bid);
    const table = (rows) => {
      const t = el("table", undefined, "rivals");
      const head = el("tr");
      ["Team", "Left", "Max bid", "Spots"].forEach((h) => head.append(el("th", h)));
      t.append(head);
      rows.forEach((r) => {
        const row = el("tr");
        row.append(el("td", r.name), el("td", `$${r.budget_left}`), el("td", `$${r.max_bid}`), el("td", r.spots_left));
        t.append(row);
      });
      return t;
    };
    box.append(el("h2", "Richest rivals"));
    box.append(table(rivals.slice(0, 5)));
    if (rivals.length > 5) {
      const more = el("details");
      more.append(el("summary", `All ${rivals.length} rivals`), table(rivals.slice(5)));
      box.append(more);
    }
  }
}

function renderTable(d) {
  const head = $("thead");
  head.textContent = "";
  const row = el("tr");
  const cols = ["#", "Player", "Score"];
  if (d.is_auction) cols.push("Worth to you", "Others pay");
  cols.forEach((c) => row.append(el("th", c)));
  d.categories.forEach((c) => row.append(el("th", c, "cat")));
  if (d.has_yahoo_ranks) ["Y! rank", "ADP"].forEach((c) => row.append(el("th", c)));
  if (mock || manual) row.append(el("th", ""));
  head.append(row);

  const body = $("tbody");
  body.textContent = "";
  d.recommendations.forEach((r, i) => {
    const tr = el("tr");
    if (d.decision && d.decision.pick === r.name) tr.className = "picked";
    if (d.is_auction) {
      tr.className += " clickable";
      tr.title = "Click to see the bid card";
      tr.onclick = (ev) => { if (!ev.target.closest("button")) setNominee(r.name, true); };
    }
    tr.append(el("td", i + 1));
    const name = el("td", r.name, "name");
    const sub = el("small", `${r.team || "FA"} · ${r.games_played} GP · ${r.minutes} min`);
    if (r.value) sub.append(" ", el("span", "value", "badge"));
    name.append(sub);
    tr.append(name, el("td", r.score.toFixed(1)));
    if (d.is_auction) {
      tr.append(el("td", r.bid != null ? `$${r.bid}` : "–"), el("td", r.market != null ? `$${r.market}` : "–"));
    }
    d.categories.forEach((c) => {
      const cell = el("td", undefined, "cat");
      const z = r.z[c];
      const chip = el("span", z.toFixed(1), "z" + (isSkipped(c) ? " punted" : ""));
      if (!isSkipped(c)) chip.style.background = zColor(z);
      cell.append(chip);
      tr.append(cell);
    });
    if (d.has_yahoo_ranks) {
      tr.append(el("td", r.yahoo_rank ?? "–"), el("td", r.adp != null ? r.adp.toFixed(1) : "–"));
    }
    if (manual) {
      const cell = el("td");
      const log = el("button", "Log", "btn secondary mini");
      log.onclick = () => { $("pk_player").value = r.name; $("pk_player").focus(); window.scrollTo({ top: 0, behavior: "smooth" }); };
      cell.append(log);
      tr.append(cell);
    }
    if (mock) {
      const cell = el("td");
      const taken = el("button", "Taken", "btn secondary mini");
      taken.onclick = () => markMock(r.name, false);
      const mine = el("button", "Mine", "btn mini");
      mine.style.marginLeft = "4px";
      mine.onclick = () => markMock(r.name, true);
      cell.append(taken, mine);
      tr.append(cell);
    }
    body.append(tr);
  });
}

function renderRoster(d) {
  const box = $("roster");
  box.textContent = "";
  if (!d.my_roster.length) {
    box.append(el("div", "No players yet. Your picks will show up here.", "hint"));
    return;
  }
  const names = el("ul");
  d.my_roster.forEach((n) => names.append(el("li", n)));
  box.append(names);
  if (d.positions && d.positions.unfilled.length) {
    const need = el("div", "Starting spots you still need: ", "need");
    need.append(el("b", d.positions.unfilled.join(", ")));
    if (d.positions.incomplete) need.append(" (Yahoo didn't list every player's positions)");
    box.append(need);
  }
  if (d.roster_unmatched.length) {
    box.append(el("div", `No stats for: ${d.roster_unmatched.join(", ")}`, "hint"));
  }
  box.append(el("h2", "Where your team is strong"));
  d.categories.forEach((c) => {
    const z = d.roster_profile[c];
    const row = el("div", undefined, "bar");
    const track = el("div", undefined, "track");
    const fill = el("div", undefined, "fill");
    const pct = Math.min(Math.abs(z) / 2, 1) * 50;
    fill.style.cssText = `background:${z >= 0 ? "var(--good)" : "var(--bad)"};` +
      (z >= 0 ? `left:50%;width:${pct}%` : `right:50%;width:${pct}%`);
    track.append(el("div", undefined, "mid"), fill);
    row.append(el("span", c), track, el("span", z.toFixed(1)));
    if (isSkipped(c)) row.style.opacity = 0.4;
    box.append(row);
  });
}

function renderPicks(d) {
  const list = $("picks");
  list.textContent = "";
  // A hand-entered league lists every pick, so any of them can be corrected
  (manual ? d.picks : d.picks.slice(-12)).slice().reverse().forEach((p) => {
    const cost = p.cost ? ` ($${p.cost})` : "";
    const li = el("li", `#${p.pick} ${p.player_name}${cost} — ${p.team_name}`, p.is_mine ? "mine" : "");
    if (manual) {
      const edit = el("a", "edit");
      edit.onclick = () => startEdit(p, d);
      const del = el("a", "delete");
      del.onclick = () => {
        if (!confirm(`Delete pick #${p.pick} (${p.player_name})? Later picks keep their teams and prices.`)) return;
        if (editing === p.pick) stopEdit();
        manualAction(() => manualApi(`/picks/${p.pick}`, "DELETE"));
      };
      li.append(" ", edit, " ", del);
    }
    list.append(li);
  });
  if (!d.picks.length) list.append(el("li", d.mock ? "Practice picks aren't listed here." : "No picks yet."));
}

function markMock(name, isMine) {
  if (lastData && lastData.is_auction) {
    const rec = (lastData.recommendations || []).find((r) => r.name === name);
    const card = lastData.nominee_card;
    const guess = (card && card.name === name ? card.market : rec && rec.market) || 1;
    const answer = prompt(`What did ${name} sell for? ($)`, guess);
    if (answer === null) return;
    mockCosts[name] = Math.max(1, parseInt(answer, 10) || 1);
    store.set("mockCosts", mockCosts);
  }
  if (!mockTaken.includes(name)) mockTaken.push(name);
  if (isMine && !mockMine.includes(name)) mockMine.push(name);
  store.set("mockTaken", mockTaken);
  store.set("mockMine", mockMine);
  refresh();
}

function pollInterval() {
  return lastData && lastData.is_auction ? AUCTION_POLL_MS : POLL_MS;
}

// --- hand-entered league ---------------------------------------------------

let loggedTeam = "";
let editing = null; // pick number being corrected, or null when logging a new one

function startEdit(p, d) {
  editing = p.pick;
  $("pk_player").value = p.player_name;
  $("pk_team").value = String(Number(p.team_key.slice(1)) + 1);
  $("pk_cost").value = p.cost ?? "";
  $("pk_msg").textContent = `Editing pick #${p.pick}.`;
  $("pk_submit").textContent = `Save pick #${p.pick}`;
  $("pk_cancel").style.display = "";
  $("pk_player").focus();
}

function stopEdit() {
  editing = null;
  $("pk_player").value = "";
  $("pk_cost").value = "";
  $("pk_msg").textContent = "";
  $("pk_submit").textContent = "Add pick";
  $("pk_cancel").style.display = "none";
}

const manualApi = (path, method, body) => jsonRequest(`${base}${path}`, method, body);

function renderManual(d) {
  const m = d.manual;
  document.querySelectorAll(".manual-only").forEach((n) => { n.style.display = "block"; });
  $("mock").closest(".setting").style.display = "none";

  // Team picker: snake defaults to whoever is on the clock; auction needs an explicit team
  const sel = $("pk_team");
  const keep = sel.value || loggedTeam;
  sel.textContent = "";
  if (!d.is_auction) {
    const clock = m.on_the_clock;
    sel.append(new Option(clock ? `On the clock: ${clock.name}` : "Draft is full", ""));
  }
  m.rosters.forEach((t) => sel.append(new Option(t.name + (t.is_mine ? " (you)" : ""), t.index + 1)));
  sel.value = [...sel.options].some((o) => o.value === keep) ? keep : (d.is_auction ? String(m.settings.my_slot) : "");
  $("pk_cost").style.display = d.is_auction ? "" : "none";
  $("pk_cost").required = d.is_auction;
  $("clock").textContent = m.complete ? "Every roster spot is filled." : `${d.picks.length} of ${m.total_picks} picks logged`;
  $("finished").checked = m.status === "finished";
  $("season_link").href = `/season/manual/${leagueId}`;
  $("season_link").style.display = m.status === "finished" ? "" : "none";

  const notes = $("notes");
  notes.textContent = "";
  [...m.notes].reverse().forEach((n) => {
    const row = el("div", n.text, "note");
    const meta = el("small");
    const when = new Date(n.ts).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
    const phase = n.phase === "before" ? "Before the draft" : n.phase === "after" ? "After the draft" : `After pick ${n.pick_count}`;
    meta.append(`${phase} · ${when}`);
    const del = el("a", "delete");
    del.onclick = async () => { try { await manualApi(`/notes/${n.id}`, "DELETE"); refresh(); } catch (e) { $("pk_msg").textContent = e.message; } };
    meta.append(del);
    row.prepend(meta);
    notes.append(row);
  });
  if (!m.notes.length) notes.append(el("div", "Nothing yet. Notes are saved with the league.", "hint"));

  const teams = $("teams");
  teams.textContent = "";
  m.rosters.forEach((t) => {
    const row = el("div", undefined, "teamrow" + (t.is_mine ? " mine" : ""));
    const left = d.is_auction ? d.teams[t.index].budget_left : null;
    row.append(el("b", `${t.name}${left != null ? ` · $${left} left` : ""}`));
    row.append(el("span", t.players.length ? t.players.map((p) => p.name + (p.cost != null ? ` ($${p.cost})` : "")).join(", ") : "No players yet"));
    teams.append(row);
  });

  ensurePlayerList();
  // Don't overwrite settings the manager is in the middle of editing
  if (!document.querySelector("details[open]")) fillSettings(m.settings);
}

let slotsUi = null;

function fillSettings(s) {
  $("s_name").value = s.name;
  $("s_teams").value = s.num_teams;
  const slots = s.slots || slotsFromRosterSize(s.roster_size);
  if (slotsUi) slotsUi.set(slots); else slotsUi = slotsEditor($("s_slots"), slots);
  $("s_slot").value = s.my_slot;
  $("s_budget").value = s.budget;
  $("s_budget").disabled = !s.is_auction;
  $("s_cats").value = s.categories.join(", ");
  $("s_names").value = s.team_names.join("\n");
}

async function manualAction(fn) {
  $("pk_msg").textContent = "";
  try { await fn(); await refresh(); } catch (e) { $("pk_msg").textContent = e.message; }
}

// After an unknown name: one-tap fixes, or log it as typed (rookies have no stats yet)
function showSuggestions(names, logPick) {
  const row = el("div", undefined, "suggest-row");
  if (names.length) row.append(el("span", "Did you mean:"));
  names.forEach((n) => {
    const b = el("button", n, "btn mini");
    b.type = "button";
    b.onclick = () => { $("pk_player").value = n; logPick(false); };
    row.append(b);
  });
  const anyway = el("button", `Log "${$("pk_player").value.trim()}" anyway`, "btn secondary mini");
  anyway.type = "button";
  anyway.title = "For players with no stats yet, like rookies";
  anyway.onclick = () => logPick(true);
  row.append(anyway);
  $("pk_msg").append(row);
}

function wireManual() {
  const logPick = async (force) => {
    const team = $("pk_team").value;
    const msg = $("pk_msg");
    msg.textContent = "";
    try {
      const body = { player_name: $("pk_player").value, team, cost: $("pk_cost").value, force };
      if (editing) await manualApi(`/picks/${editing}`, "PUT", body);
      else await manualApi("/picks", "POST", body);
    } catch (e) {
      msg.textContent = e.message;
      if (e.data && e.data.unknown_player) showSuggestions(e.data.suggestions || [], logPick);
      return;
    }
    if (editing) stopEdit(); else loggedTeam = team;
    $("pk_player").value = "";
    $("pk_cost").value = "";
    $("pk_player").focus();
    await refresh();
  };
  $("pk_cancel").onclick = stopEdit;
  $("pickform").onsubmit = (e) => { e.preventDefault(); logPick(false); };
  $("pk_undo").onclick = () => manualAction(() => manualApi("/picks/last", "DELETE"));
  $("finished").onchange = (e) => manualAction(() => manualApi("/status", "PUT", { status: e.target.checked ? "finished" : "drafting" }));
  $("note_add").onclick = () => manualAction(async () => {
    await manualApi("/notes", "POST", { text: $("note_text").value });
    $("note_text").value = "";
  });
  $("s_save").onclick = async () => {
    $("s_msg").textContent = "";
    try {
      await manualApi("/settings", "PUT", {
        name: $("s_name").value, num_teams: $("s_teams").value, slots: slotsUi.get(),
        my_slot: $("s_slot").value, budget: $("s_budget").value,
        categories: $("s_cats").value.split(",").map((c) => c.trim()),
        team_names: $("s_names").value.split("\n"),
      });
      document.querySelector("details").open = false;
      await refresh();
    } catch (e) { $("s_msg").textContent = e.message; }
  };
}

function applyMode() {
  $("mock").checked = mock;
  $("reset").style.display = mock ? "" : "none";
  clearInterval(timer);
  activePoll = pollInterval();
  if (!mock && !manual) timer = setInterval(refresh, activePoll);
}

$("mode").value = jevMode;
$("pref").value = preference;
$("mode").onchange = (e) => {
  jevMode = e.target.value;
  store.set("jevMode", jevMode);
  refresh();
};
// Refresh when the preference is committed, not on every keystroke (each change is a Jev call)
$("pref").onchange = (e) => {
  preference = e.target.value.trim();
  store.set("preference", preference);
  refresh();
};

$("slot").value = draftPosition;
$("slot").onchange = (e) => {
  draftPosition = e.target.value;
  store.set("draftPosition", draftPosition);
  refresh();
};

$("autopunt").checked = autoPunts;
$("autopunt").onchange = (e) => {
  autoPunts = e.target.checked;
  store.set("autoPunts", autoPunts);
  refresh();
};

$("mock").onchange = (e) => {
  mock = e.target.checked;
  store.set("mock", mock);
  applyMode();
  refresh();
};
$("reset").onclick = () => {
  mockTaken = []; mockMine = []; mockCosts = {};
  store.set("mockTaken", mockTaken); store.set("mockMine", mockMine); store.set("mockCosts", mockCosts);
  refresh();
};

// Nominee box: Enter looks the player up, Esc or Clear empties it, / jumps to it from anywhere
$("nominee").onkeydown = (e) => {
  if (e.key === "Enter") { setNominee(e.target.value.trim()); e.target.select(); }
  if (e.key === "Escape") { setNominee(""); e.target.blur(); }
};
$("nominee").onchange = (e) => { if (e.target.value.trim() !== nominee) setNominee(e.target.value.trim()); };
$("nominee-clear").onclick = () => { setNominee(""); $("nominee").focus(); };
document.addEventListener("keydown", (e) => {
  const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
  if (e.key === "/" && !typing && lastData && lastData.is_auction) {
    e.preventDefault();
    $("nominee").focus();
    $("nominee").select();
  }
});

if (manual) wireManual();
applyMode();
refresh();
