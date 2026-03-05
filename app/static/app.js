const form = document.getElementById("controls");
const tbody = document.querySelector("#results tbody");
const statusEl = document.getElementById("status");
const sortSelect = document.getElementById("sort_by");
const headerRow = document.getElementById("results-header-row");
const advancedToggleBtn = document.getElementById("advanced-toggle");

const BASE_COLUMNS = [
  { key: "player_name", label: "PLAYER" },
  { key: "team", label: "TEAM" },
  { key: "gp", label: "GP" },
  { key: "ppg", label: "PPG" },
  { key: "rpg", label: "RPG" },
  { key: "apg", label: "APG" },
  { key: "spg", label: "SPG" },
  { key: "bpg", label: "BPG" },
  { key: "plus_minus", label: "+/-" },
  { key: "fg_pct", label: "FG%" },
  { key: "ts_pct", label: "TS%" },
  { key: "ft_pct", label: "FT%" },
  { key: "three_pt_pct", label: "3P%" },
  { key: "pf_pg", label: "FOULS/G" },
];

const ADVANCED_COLUMNS = [
  { key: "player_name", label: "PLAYER" },
  { key: "team", label: "TEAM" },
  { key: "gp", label: "G" },
  { key: "mpg", label: "MP" },
  { key: "ts_pct", label: "TS%" },
  { key: "three_par", label: "3PAr" },
  { key: "ftr", label: "FTr" },
  { key: "oreb_pct", label: "ORB%" },
  { key: "dreb_pct", label: "DRB%" },
  { key: "reb_pct", label: "TRB%" },
  { key: "ast_pct", label: "AST%" },
  { key: "stl_pct", label: "STL%" },
  { key: "blk_pct", label: "BLK%" },
  { key: "tov_pct", label: "TOV%" },
  { key: "usg_pct", label: "USG%" },
  { key: "off_rating", label: "OFF RTG" },
  { key: "def_rating", label: "DEF RTG" },
  { key: "net_rating", label: "NET RTG" },
  { key: "efg_pct", label: "eFG%" },
  { key: "pie", label: "PIE" },
];

let advancedMode = false;

function currentColumns() {
  return advancedMode ? ADVANCED_COLUMNS : BASE_COLUMNS;
}

function fmt(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function renderHeader() {
  headerRow.innerHTML = currentColumns().map((c) => `<th>${c.label}</th>`).join("");
}

function renderSortOptions() {
  const preferred = advancedMode ? "ts_pct" : "ppg";
  sortSelect.innerHTML = currentColumns()
    .map((c) => `<option value="${c.key}">${c.label}</option>`)
    .join("");
  sortSelect.value = preferred;
}

function renderRows(rows) {
  const columns = currentColumns();
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = columns.map((c) => `<td>${fmt(row[c.key])}</td>`).join("");
    tbody.appendChild(tr);
  }
}

async function loadData() {
  const params = new URLSearchParams(new FormData(form));
  params.set("limit", "250");
  statusEl.textContent = "Loading...";
  try {
    const res = await fetch(`/api/players?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
    const payload = await res.json();
    renderRows(payload.data);
    statusEl.textContent = `Loaded ${payload.data.length} players (total ${payload.meta.total}) for ${payload.meta.season}`;
  } catch (error) {
    statusEl.textContent = `Failed to load data: ${error}`;
  }
}

advancedToggleBtn.addEventListener("click", () => {
  advancedMode = !advancedMode;
  advancedToggleBtn.textContent = `ADVANCED STATISTICS: ${advancedMode ? "ON" : "OFF"}`;
  renderHeader();
  renderSortOptions();
  loadData();
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  loadData();
});

renderHeader();
renderSortOptions();
loadData();
