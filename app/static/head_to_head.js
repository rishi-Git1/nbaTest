const form = document.getElementById("h2h-controls");
const statusEl = document.getElementById("h2h-status");
const grid = document.getElementById("comparison-grid");

function fmt(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(3);
  return `${value}`;
}

function teamCard(teamData) {
  const team = teamData.summary;
  const players = teamData.players || [];
  const topPlayers = players.slice(0, 12);

  return `
    <article class="card">
      <h2>${team.team_name} (${team.abbreviation})</h2>

      <table class="mini-table">
        <tbody>
          <tr><th>GP</th><td>${fmt(team.gp)}</td></tr>
          <tr><th>PPG</th><td>${fmt(team.ppg)}</td></tr>
          <tr><th>RPG</th><td>${fmt(team.rpg)}</td></tr>
          <tr><th>APG</th><td>${fmt(team.apg)}</td></tr>
          <tr><th>SPG</th><td>${fmt(team.spg)}</td></tr>
          <tr><th>BPG</th><td>${fmt(team.bpg)}</td></tr>
          <tr><th>+/-</th><td>${fmt(team.plus_minus)}</td></tr>
          <tr><th>FG%</th><td>${fmt(team.fg_pct)}</td></tr>
          <tr><th>TS%</th><td>${fmt(team.ts_pct)}</td></tr>
          <tr><th>FT%</th><td>${fmt(team.ft_pct)}</td></tr>
          <tr><th>FOULS/G</th><td>${fmt(team.pf_pg)}</td></tr>
        </tbody>
      </table>

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
              topPlayers.length
                ? topPlayers
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
  const team1 = params.get("team1_id");
  const team2 = params.get("team2_id");

  if (team1 === team2) {
    statusEl.textContent = "Please choose two different teams.";
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
    grid.innerHTML = `${teamCard(payload.team_1)}${teamCard(payload.team_2)}`;
    statusEl.textContent = `Loaded ${payload.team_1.summary.team_name} vs ${payload.team_2.summary.team_name} for ${payload.meta.season}.`;
  } catch (error) {
    statusEl.textContent = `Failed to load comparison: ${error}`;
    grid.innerHTML = "";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadComparison();
});

loadComparison();
