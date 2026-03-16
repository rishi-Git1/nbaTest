const form = document.getElementById("lineups-controls");
const statusEl = document.getElementById("lineups-status");
const tbody = document.querySelector("#lineups-results tbody");

function fmt(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function renderRows(rows) {
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmt(row.rank)}</td>
      <td>${fmt(row.lineup)}</td>
      <td>${fmt(row.min)}</td>
      <td>${fmt(row.gp)}</td>
      <td>${fmt(row.off_rating)}</td>
      <td>${fmt(row.def_rating)}</td>
      <td>${fmt(row.net_rating)}</td>
      <td>${fmt(row.ast_pct)}</td>
      <td>${fmt(row.reb_pct)}</td>
      <td>${fmt(row.efg_pct)}</td>
      <td>${fmt(row.ts_pct)}</td>
      <td>${fmt(row.pie)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadLineups() {
  const params = new URLSearchParams(new FormData(form));
  statusEl.textContent = "Loading lineups...";
  try {
    const res = await fetch(`/api/lineups?${params.toString()}`);
    const json = await res.json();
    if (!res.ok) {
      throw new Error(json?.detail || `${res.status} ${res.statusText}`);
    }
    renderRows(json.data || []);
    statusEl.textContent = `Loaded ${json.data.length} lineups for ${json.meta.team_name} (${json.meta.season}).`;
  } catch (error) {
    statusEl.textContent = `Failed to load lineups: ${error}`;
    tbody.innerHTML = "";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadLineups();
});

loadLineups();
