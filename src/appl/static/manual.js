const CATS = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"];
const slots = slotsEditor(document.getElementById("slots_box"), DEFAULT_SLOTS);

CATS.forEach((c) => {
  const label = el("label", undefined, "chip");
  const box = document.createElement("input");
  box.type = "checkbox"; box.value = c; box.checked = true;
  label.append(box, c);
  $("cats").append(label);
});
$("is_auction").onchange = (e) => { $("budget_box").style.display = e.target.value === "1" ? "" : "none"; };

const api = fetchJson;

async function loadLeagues() {
  const box = $("leagues");
  try {
    const { leagues } = await api("/manual/api/leagues");
    box.textContent = "";
    if (!leagues.length) { box.append(el("span", "None yet. Create one below.", "help")); return; }
    leagues.forEach((l) => {
      const row = el("div", undefined, "row");
      const info = el("div");
      const link = el("a", l.name, "name");
      link.href = `/manual/${l.id}`;
      info.append(link, el("small", `${l.is_auction ? "Auction" : "Snake"} · ${l.num_teams} teams · ${l.picks}/${l.total_picks} picks · ${l.status === "finished" ? "draft finished" : "drafting"}`));
      const ask = el("a", "💬 Ask", "btn mini");
      ask.href = `/ai-chat/manual/${l.id}`;
      const season = el("a", "Season analysis", "btn secondary mini");
      season.href = `/season/manual/${l.id}`;
      const del = el("button", "Delete", "btn secondary mini");
      del.onclick = async () => {
        if (!confirm(`Delete "${l.name}" and all its picks and notes?`)) return;
        try { await api(`/manual/${l.id}`, { method: "DELETE" }); loadLeagues(); } catch (e) { showError(e.message); }
      };
      const actions = el("div");
      actions.style.cssText = "display:flex; gap:8px; flex-shrink:0";
      actions.append(ask, season, del);
      row.append(info, actions);
      box.append(row);
    });
  } catch (e) { box.textContent = ""; showError("Could not load leagues: " + e.message); }
}

$("form").onsubmit = async (e) => {
  e.preventDefault();
  showError("");
  const body = {
    name: $("name").value, num_teams: $("num_teams").value, slots: slots.get(),
    team_names: $("team_names").value.split("\n").map((n) => n.trim()).filter(Boolean),
    my_slot: $("my_slot").value, is_auction: $("is_auction").value === "1", budget: $("budget").value,
    categories: [...document.querySelectorAll("#cats input:checked")].map((b) => b.value),
  };
  try {
    const { id } = await api("/manual/api/leagues", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    location.href = `/manual/${id}`;
  } catch (err) { showError(err.message); }
};

async function loadTokens() {
  const box = $("tokens");
  try {
    const { tokens } = await api("/manual/api/tokens");
    box.textContent = "";
    tokens.forEach((t) => {
      const row = el("div", undefined, "row");
      const info = el("div");
      info.append(el("b", t.label), el("small", `ends in …${t.hint} · made ${t.created.slice(0, 10)}`));
      const revoke = el("button", "Revoke", "btn secondary mini");
      revoke.type = "button";
      revoke.onclick = async () => {
        if (!confirm(`Revoke "${t.label}" (…${t.hint})? Anything using it stops working.`)) return;
        try { await api(`/manual/api/tokens/${t.id}`, { method: "DELETE" }); loadTokens(); } catch (e) { showError(e.message); }
      };
      row.append(info, revoke);
      box.append(row);
    });
  } catch (e) { showError("Could not load access tokens: " + e.message); }
}

$("make_token").onclick = async () => {
  showError("");
  try {
    const { token } = await api("/manual/api/tokens", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: "Claude Code" }) });
    $("token_value").textContent = token;
    $("token_snippet").textContent = JSON.stringify({ env: { FBH_URL: location.origin, FBH_TOKEN: token } }, null, 2);
    $("new_token").style.display = "";
    loadTokens();
  } catch (e) { showError(e.message); }
};
$("copy_snippet").onclick = async () => {
  try { await navigator.clipboard.writeText($("token_snippet").textContent); $("copy_snippet").textContent = "Copied"; }
  catch { showError("Couldn't copy; select the text and copy it by hand."); }
};

loadLeagues();
loadTokens();
