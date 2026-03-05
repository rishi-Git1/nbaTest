const form = document.getElementById("controls");
const tbody = document.querySelector("#results tbody");
const statusEl = document.getElementById("status");

function fmt(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function renderRows(rows) {
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.player_name}</td>
      <td>${fmt(row.team)}</td>
      <td>${fmt(row.gp)}</td>
      <td>${fmt(row.ppg)}</td>
      <td>${fmt(row.rpg)}</td>
      <td>${fmt(row.apg)}</td>
      <td>${fmt(row.spg)}</td>
      <td>${fmt(row.bpg)}</td>
      <td>${fmt(row.plus_minus)}</td>
      <td>${fmt(row.fg_pct)}</td>
      <td>${fmt(row.ts_pct)}</td>
      <td>${fmt(row.ft_pct)}</td>
      <td>${fmt(row.three_pt_pct)}</td>
      <td>${fmt(row.pf_pg)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function loadData() {
  const params = new URLSearchParams(new FormData(form));
  params.set("limit", "200");
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

form.addEventListener("submit", (e) => {
  e.preventDefault();
  loadData();
});

loadData();
