const dateForm = document.getElementById("ge-date-controls");
const matchupForm = document.getElementById("ge-matchup-controls");
const statusEl = document.getElementById("ge-status");
const gamesBody = document.querySelector("#ge-games-table tbody");
const analysisSection = document.getElementById("ge-analysis");
const analysisTitle = document.getElementById("ge-analysis-title");
const analysisSubtitle = document.getElementById("ge-analysis-subtitle");
const keyFactorsEl = document.getElementById("ge-key-factors");
const teamComparisonBody = document.querySelector("#ge-team-comparison tbody");
const team1Header = document.getElementById("ge-team-1-header");
const team2Header = document.getElementById("ge-team-2-header");
const topPerformersBody = document.querySelector("#ge-top-performers tbody");
const playerStatsBody = document.querySelector("#ge-player-stats tbody");

function fmt(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(digits);
  return `${value}`;
}

function renderGames(rows) {
  gamesBody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmt(row.game_date)}</td>
      <td>${fmt(row.matchup)}</td>
      <td>${fmt(row.score)}</td>
      <td><button type="button" class="nav-button ge-load-analysis" data-game-id="${row.game_id}">ANALYZE</button></td>
    `;
    gamesBody.appendChild(tr);
  });

  document.querySelectorAll(".ge-load-analysis").forEach((button) => {
    button.addEventListener("click", () => loadAnalysis(button.dataset.gameId));
  });
}

function renderKeyFactors(factors) {
  keyFactorsEl.innerHTML = "";
  (factors || []).forEach((factor) => {
    const li = document.createElement("li");
    li.textContent = factor;
    keyFactorsEl.appendChild(li);
  });
}

function renderTeamComparison(payload) {
  const teams = payload.teams || [];
  const comparisonRows = payload.team_comparison || [];
  if (teams.length < 2) {
    teamComparisonBody.innerHTML = "";
    return;
  }

  team1Header.textContent = `${teams[0].team_name} (${teams[0].team_abbreviation})`;
  team2Header.textContent = `${teams[1].team_name} (${teams[1].team_abbreviation})`;
  teamComparisonBody.innerHTML = comparisonRows.map((row) => `
    <tr>
      <td class="metric-col">${fmt(row.label)}</td>
      <td class="team-col ${row.winner === "team_1" ? "winner" : row.winner === "team_2" ? "loser" : ""}">${fmt(row.team_1_value)}</td>
      <td class="team-col ${row.winner === "team_2" ? "winner" : row.winner === "team_1" ? "loser" : ""}">${fmt(row.team_2_value)}</td>
    </tr>
  `).join("");
}

function renderPlayerTable(tbody, rows) {
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmt(row.player_name)}</td>
      <td>${fmt(row.team_abbreviation)}</td>
      <td>${fmt(row.minutes_display ?? row.minutes)}</td>
      <td>${fmt(row.pts)}</td>
      <td>${fmt(row.reb)}</td>
      <td>${fmt(row.ast)}</td>
      <td>${fmt(row.fgm)}</td>
      <td>${fmt(row.fga)}</td>
      <td>${fmt(row.fg3m)}</td>
      <td>${fmt(row.plus_minus)}</td>
      <td>${fmt(row.usg_pct)}</td>
      <td>${fmt(row.ts_pct)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function runGamesSearch(form, label) {
  const params = new URLSearchParams(new FormData(form));
  statusEl.textContent = `Loading ${label}...`;
  analysisSection.classList.add("hidden");

  try {
    const res = await fetch(`/api/game-explainer/games?${params.toString()}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);
    renderGames(json.data || []);
    statusEl.textContent = `${label}: loaded ${json.meta?.total ?? 0} games.`;
  } catch (error) {
    statusEl.textContent = `Failed ${label}: ${error}`;
    gamesBody.innerHTML = "";
  }
}

async function loadAnalysis(gameId) {
  statusEl.textContent = `Loading analysis for ${gameId}...`;

  try {
    const res = await fetch(`/api/game-explainer/analysis?game_id=${encodeURIComponent(gameId)}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);

    analysisSection.classList.remove("hidden");
    analysisTitle.textContent = `${json.meta.matchup} — ${json.meta.score}`;
    analysisSubtitle.textContent = `Winner: ${json.meta.winner_team_name} | Date: ${fmt(json.meta.game_date)}`;
    renderKeyFactors(json.key_factors || []);
    renderTeamComparison(json);
    renderPlayerTable(topPerformersBody, json.top_performers || []);
    renderPlayerTable(playerStatsBody, json.players || []);
    statusEl.textContent = `Loaded game analysis for ${json.meta.matchup}.`;
  } catch (error) {
    statusEl.textContent = `Failed analysis: ${error}`;
    analysisSection.classList.add("hidden");
  }
}

dateForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runGamesSearch(dateForm, "date search");
});

matchupForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const team1 = new FormData(matchupForm).get("team1_id");
  const team2 = new FormData(matchupForm).get("team2_id");
  if (team1 === team2) {
    statusEl.textContent = "Pick two different teams for matchup search.";
    return;
  }
  runGamesSearch(matchupForm, "matchup search");
});
