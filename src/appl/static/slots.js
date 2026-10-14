/* Roster spots by position (PG, SG, G, SF, PF, F, C, Util, Bench, Injured list).
   One number per position, used by the "new league" form and the league settings. */
(function () {
  const ROWS = [
    ["PG", "PG"], ["SG", "SG"], ["G", "G"], ["SF", "SF"], ["PF", "PF"], ["F", "F"],
    ["C", "C"], ["Util", "Util"], ["BN", "Bench"], ["IL", "Injured list"],
  ];
  const DEFAULTS = { PG: 1, SG: 1, G: 1, SF: 1, PF: 1, F: 1, C: 1, Util: 3, BN: 3, IL: 1 };
  const MAX = 15;

  const STYLE = `
    .slots-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; margin-top: 8px; }
    .slots-grid label { margin: 0; }
    .slots-grid span { display: block; font-weight: 700; font-size: .85rem; margin-bottom: 3px; }
    .slots-total { margin-top: 10px; color: var(--muted); font-size: .9rem; }
  `;

  // Leagues made before positions existed only know a roster size: use the usual
  // starting spots first and put everyone else on the bench.
  function fromRosterSize(size) {
    const slots = Object.fromEntries(ROWS.map(([key]) => [key, 0]));
    slots.IL = 1;
    let left = Number(size) || 0;
    for (const key of ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "Util"]) {
      if (left <= 0) break;
      slots[key] += 1;
      left -= 1;
    }
    slots.BN = Math.max(left, 0);
    return slots;
  }

  function slotsEditor(container, initial) {
    if (!document.getElementById("slots-style")) {
      const style = document.createElement("style");
      style.id = "slots-style";
      style.textContent = STYLE;
      document.head.append(style);
    }
    container.textContent = "";
    const grid = document.createElement("div");
    grid.className = "slots-grid";
    const total = document.createElement("div");
    total.className = "slots-total";
    const inputs = {};

    ROWS.forEach(([key, label]) => {
      const wrap = document.createElement("label");
      const name = document.createElement("span");
      name.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.className = "field";
      input.min = "0";
      input.max = String(MAX);
      input.addEventListener("input", update);
      inputs[key] = input;
      wrap.append(name, input);
      grid.append(wrap);
    });
    container.append(grid, total);

    function count(key) {
      const n = parseInt(inputs[key].value, 10);
      return Number.isNaN(n) ? 0 : Math.max(0, Math.min(MAX, n));
    }

    function get() {
      return Object.fromEntries(ROWS.map(([key]) => [key, count(key)]));
    }

    function update() {
      const slots = get();
      const size = Object.entries(slots).filter(([k]) => k !== "IL").reduce((sum, [, n]) => sum + n, 0);
      total.textContent = `${size} players per team (${size - slots.BN} starting, ${slots.BN} on the bench). The injured list is not counted.`;
    }

    function set(slots) {
      ROWS.forEach(([key]) => { inputs[key].value = (slots && slots[key]) || 0; });
      update();
    }

    set(initial || DEFAULTS);
    return { get, set };
  }

  window.slotsEditor = slotsEditor;
  window.slotsFromRosterSize = fromRosterSize;
  window.DEFAULT_SLOTS = DEFAULTS;
})();
