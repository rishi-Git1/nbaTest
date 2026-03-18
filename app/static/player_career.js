const careerForm = document.getElementById("career-controls");
const careerStatusEl = document.getElementById("career-status");
const careerPlayerInput = document.getElementById("player_name");
const careerOptionsList = document.getElementById("career-player-options");
const careerSummaryHeader = document.getElementById("career-summary-header");
const careerSummaryBody = document.querySelector("#career-summary-table tbody");
const careerResultsHeader = document.getElementById("career-results-header");
const careerResultsBody = document.querySelector("#career-results tbody");
const careerAdvancedToggleBtn = document.getElementById("career-advanced-toggle");
const careerResultsWrap = document.getElementById("career-results-wrap");
const careerTopScroll = document.getElementById("career-results-top-scroll");
const careerTopScrollInner = document.getElementById("career-results-top-scroll-inner");

const CAREER_BASE_COLUMNS = [
  { key: "season", label: "SEASON" },
  { key: "team", label: "TEAM" },
  { key: "gp", label: "GP" },
  { key: "mpg", label: "MPG" },
  { key: "ppg", label: "PPG" },
  { key: "rpg", label: "RPG" },
  { key: "apg", label: "APG" },
  { key: "spg", label: "SPG" },
  { key: "bpg", label: "BPG" },
  { key: "fg_pct", label: "FG%" },
  { key: "three_pt_pct", label: "3P%" },
  { key: "ft_pct", label: "FT%" },
  { key: "ts_pct", label: "TS%" },
  { key: "pf_pg", label: "FOULS/G" },
];

const CAREER_ADVANCED_COLUMNS = [
  { key: "season", label: "SEASON" },
  { key: "team", label: "TEAM" },
  { key: "gp", label: "GP" },
  { key: "mpg", label: "MPG" },
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

let careerAdvancedMode = false;

function currentCareerColumns() {
  return careerAdvancedMode ? CAREER_ADVANCED_COLUMNS : CAREER_BASE_COLUMNS;
}

function careerFmt(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function renderCareerHeaders() {
  const markup = currentCareerColumns().map((column) => `<th>${column.label}</th>`).join("");
  careerSummaryHeader.innerHTML = markup;
  careerResultsHeader.innerHTML = markup;
}

function renderCareerSummary(row) {
  const columns = currentCareerColumns();
  careerSummaryBody.innerHTML = "";
  const tr = document.createElement("tr");
  tr.innerHTML = columns.map((column) => `<td>${careerFmt(row?.[column.key])}</td>`).join("");
  careerSummaryBody.appendChild(tr);
}

function renderCareerSeasons(rows) {
  const columns = currentCareerColumns();
  careerResultsBody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = columns.map((column) => `<td>${careerFmt(row?.[column.key])}</td>`).join("");
    careerResultsBody.appendChild(tr);
  });
  syncCareerScrollbarWidth();
}

function syncCareerScrollbarWidth() {
  const table = document.getElementById("career-results");
  careerTopScrollInner.style.width = `${table.scrollWidth}px`;
}

function syncCareerScrollbars() {
  let syncingFromTop = false;
  let syncingFromBottom = false;

  careerTopScroll.addEventListener("scroll", () => {
    if (syncingFromBottom) return;
    syncingFromTop = true;
    careerResultsWrap.scrollLeft = careerTopScroll.scrollLeft;
    syncingFromTop = false;
  });

  careerResultsWrap.addEventListener("scroll", () => {
    if (syncingFromTop) return;
    syncingFromBottom = true;
    careerTopScroll.scrollLeft = careerResultsWrap.scrollLeft;
    syncingFromBottom = false;
  });
}

async function loadCareerPlayerOptions() {
  const res = await fetch("/api/player-directory");
  const json = await res.json();
  if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);

  careerOptionsList.innerHTML = "";
  (json.data || []).forEach((row) => {
    const option = document.createElement("option");
    option.value = row.player_name;
    careerOptionsList.appendChild(option);
  });
}

async function loadCareerStats() {
  const params = new URLSearchParams(new FormData(careerForm));
  careerStatusEl.textContent = "Loading career stats...";

  try {
    const res = await fetch(`/api/player-career?${params.toString()}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);

    renderCareerSummary(json.career || {});
    renderCareerSeasons(json.seasons || []);
    careerStatusEl.textContent = `Loaded ${json.meta.player_name} | seasons: ${json.meta.season_count}`;
  } catch (error) {
    careerStatusEl.textContent = `Failed to load career stats: ${error}`;
    careerSummaryBody.innerHTML = "";
    careerResultsBody.innerHTML = "";
  }
}

careerAdvancedToggleBtn.addEventListener("click", () => {
  careerAdvancedMode = !careerAdvancedMode;
  careerAdvancedToggleBtn.textContent = `ADVANCED STATISTICS: ${careerAdvancedMode ? "ON" : "OFF"}`;
  renderCareerHeaders();
  loadCareerStats();
});

careerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadCareerStats();
});

renderCareerHeaders();
syncCareerScrollbars();
window.addEventListener("resize", syncCareerScrollbarWidth);

(async () => {
  try {
    await loadCareerPlayerOptions();
    await loadCareerStats();
  } catch (error) {
    careerStatusEl.textContent = `Failed to initialize page: ${error}`;
  }
})();
