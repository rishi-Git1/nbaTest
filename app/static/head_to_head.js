const form = document.getElementById("h2h-controls");
const statusEl = document.getElementById("h2h-status");
const summaryEl = document.getElementById("team-summary");
const grid = document.getElementById("comparison-grid");

const METRICS = [
  { key: "ppg", label: "PPG", lowerIsBetter: false },
  { key: "rpg", label: "RPG", lowerIsBetter: false },
  { key: "apg", label: "APG", lowerIsBetter: false },
  { key: "spg", label: "SPG", lowerIsBetter: false },
  { key: "bpg", label: "BPG", lowerIsBetter: false },
  { key: "plus_minus", label: "+/-", lowerIsBetter: false },
  { key: "fg_pct", label: "FG%", lowerIsBetter: false },
  { key: "ts_pct", label: "TS%", lowerIsBetter: false },
  { key: "ft_pct", label: "FT%", lowerIsBetter: false },
  { key: "pf_pg", label: "FOULS/G", lowerIsBetter: true },
  { key: "tov_pg", label: "TOV/G", lowerIsBetter: true },
  { key: "off_rating", label: "OFF RATING", lowerIsBetter: false },
  { key: "def_rating", label: "DEF RATING", lowerIsBetter: true },
];

function fmt(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function winnerForMetric(team1Value, team2Value, lowerIsBetter) {
  if (team1Value === null || team1Value === undefined || team2Value === null || team2Value === undefined) {
    return "none";
  }
  if (team1Value === team2Value) return "tie";

  if (lowerIsBetter) {
    return team1Value < team2Value ? "team1" : "team2";
  }
  return team1Value > team2Value ? "team1" : "team2";
}

function indicator(winner, side) {
  if (winner === "tie" || winner === "none") return "•";
  if (winner === side) return "↑";
  return "↓";
}

function renderTeamSummary(team1, team2) {
  const rows = METRICS.map((metric) => {
    const v1 = team1[metric.key];
    const v2 = team2[metric.key];
    const winner = winnerForMetric(v1, v2, metric.lowerIsBetter);

    return `
      <tr>
        <td class="metric-col">${metric.label}${metric.lowerIsBetter ? " (LOWER IS BETTER)" : ""}</td>
        <td class="team-col ${winner === "team1" ? "winner" : ""}">
          <span class="arrow">${indicator(winner, "team1")}</span>${fmt(v1)}
        </td>
        <td class="team-col ${winner === "team2" ? "winner" : ""}">
          <span class="arrow">${indicator(winner, "team2")}</span>${fmt(v2)}
        </td>
      </tr>
    `;
  }).join("");

  summaryEl.innerHTML = `
    <table class="summary-table">
      <thead>
        <tr>
          <th>TEAM METRIC</th>
          <th>${team1.team_name.toUpperCase()} (${team1.season})</th>
          <th>${team2.team_name.toUpperCase()} (${team2.season})</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function teamPlayersCard(teamData) {
  const team = teamData.summary;
  const players = (teamData.players || []).slice(0, 12);

  return `
    <article class="card">
      <h2>${team.team_name} (${team.abbreviation}) - ${team.season}</h2>
      <h3>ACTIVE PLAYERS (SORTED BY PPG)</h3>
      <div class="table-wrap">
        <table class="players-table">
          <thead>
            <tr>
              <th>PLAYER</th>
              <th>PPG</th>
              <th>RPG</th>
              <th>APG</th>
              <th>SPG</th>
              <th>BPG</th>
            </tr>
          </thead>
          <tbody>
            ${
              players.length
                ? players
                    .map(
                      (player) => `
                  <tr>
                    <td>${player.player_name}</td>
                    <td>${fmt(player.ppg)}</td>
                    <td>${fmt(player.rpg)}</td>
                    <td>${fmt(player.apg)}</td>
                    <td>${fmt(player.spg)}</td>
                    <td>${fmt(player.bpg)}</td>
                  </tr>
                `,
                    )
                    .join("")
                : `<tr><td colspan="6">No active player data available.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </article>
  `;
}

async function loadComparison() {
  const params = new URLSearchParams(new FormData(form));
  const season1 = params.get("season_1");
  const team1 = params.get("team1_id");
  const season2 = params.get("season_2");
  const team2 = params.get("team2_id");

  if (team1 === team2 && season1 === season2) {
    statusEl.textContent = "Pick at least one different value (team or season) to compare.";
    summaryEl.innerHTML = "";
    grid.innerHTML = "";
    return;
  }

  statusEl.textContent = "Loading team comparison...";
  try {
    const res = await fetch(`/api/head-to-head?${params.toString()}`);
    if (!res.ok) {
      const errPayload = await res.json().catch(() => null);
      const message = errPayload?.detail || `${res.status} ${res.statusText}`;
      throw new Error(message);
    }

    const payload = await res.json();
    renderTeamSummary(payload.team_1.summary, payload.team_2.summary);
    grid.innerHTML = `${teamPlayersCard(payload.team_1)}${teamPlayersCard(payload.team_2)}`;
    statusEl.textContent = `Loaded ${payload.team_1.summary.team_name} (${payload.meta.season_1}) vs ${payload.team_2.summary.team_name} (${payload.meta.season_2}).`;
  } catch (error) {
    statusEl.textContent = `Failed to load comparison: ${error}`;
    summaryEl.innerHTML = "";
    grid.innerHTML = "";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadComparison();
});

loadComparison();
