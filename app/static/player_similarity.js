const form = document.getElementById("similarity-controls");
const statusEl = document.getElementById("similarity-status");
const tbody = document.querySelector("#similarity-results tbody");
const optionsList = document.getElementById("player-options");

function fmt(value, digits = 3) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(digits);
  return `${value}`;
}

async function loadPlayerOptions() {
  const season = document.getElementById("season").value;
  const res = await fetch(`/api/players?season=${encodeURIComponent(season)}&sort_by=player_name&order=asc&limit=1000`);
  const json = await res.json();
  if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);

  optionsList.innerHTML = "";
  (json.data || []).forEach((row) => {
    const opt = document.createElement("option");
    opt.value = row.player_name;
    optionsList.appendChild(opt);
  });
}

function renderRows(rows) {
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmt(row.rank)}</td>
      <td>${fmt(row.player_name)}</td>
      <td>${fmt(row.team)}</td>
      <td>${fmt(row.similarity, 4)}</td>
      <td>${fmt(row.archetype)}</td>
      <td>${fmt(row.ppg)}</td>
      <td>${fmt(row.apg)}</td>
      <td>${fmt(row.rpg)}</td>
      <td>${fmt(row.ts_pct)}</td>
      <td>${fmt(row.usg_pct)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function runSimilarity() {
  const fd = new FormData(form);
  const params = new URLSearchParams();
  params.set("season", fd.get("season") || "");
  params.set("player_name", fd.get("player_name") || "");
  params.set("top_n", fd.get("top_n") || "5");
  params.set("min_minutes", fd.get("min_minutes") || "800");
  params.set("include_shot_diet", document.getElementById("include_shot_diet").checked ? "true" : "false");
  params.set("archetype_only", document.getElementById("archetype_only").checked ? "true" : "false");
  statusEl.textContent = "Calculating similarity...";

  try {
    const res = await fetch(`/api/player-similarity?${params.toString()}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);

    renderRows(json.data || []);
    const requested = json.meta?.shot_diet_requested;
    const included = json.meta?.shot_diet_included;
    const shotDietLabel = requested
      ? (included ? "shot diet ON" : "shot diet requested (unavailable)")
      : "shot diet OFF";
    statusEl.textContent = `Target: ${json.meta.target_player_name} | ${shotDietLabel} | candidates: ${json.meta.candidate_count}`;
  } catch (error) {
    statusEl.textContent = `Failed: ${error}`;
    tbody.innerHTML = "";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSimilarity();
});

document.getElementById("season").addEventListener("change", async () => {
  try {
    await loadPlayerOptions();
  } catch (error) {
    statusEl.textContent = `Failed to load players for season: ${error}`;
  }
});

(async () => {
  try {
    await loadPlayerOptions();
  } catch (error) {
    statusEl.textContent = `Failed to load players: ${error}`;
  }
})();
