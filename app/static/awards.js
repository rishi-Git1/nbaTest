const form = document.getElementById("awards-controls");
const statusEl = document.getElementById("awards-status");
const tbody = document.querySelector("#awards-results tbody");
const awardSelect = document.getElementById("award");
const teamWeightInput = document.getElementById("team_rating_weight");
const minGpInput = document.getElementById("min_gp");
const topNInput = document.getElementById("top_n");
const resetBtn = document.getElementById("reset-weights");
const metricInputs = [...document.querySelectorAll("input[data-metric-key]")];

function getWeightPayload() {
  const weights = {};
  metricInputs.forEach((input) => {
    const value = Number(input.value || 0);
    if (value > 0) {
      weights[input.dataset.metricKey] = Math.min(100, value);
    }
  });
  return weights;
}

function applyPreset(name) {
  const preset = window.AWARDS_PRESETS?.[name] || { weights: {}, team_rating_weight: 0, min_gp: 0 };

  metricInputs.forEach((input) => {
    input.value = String(preset.weights?.[input.dataset.metricKey] ?? 0);
  });
  teamWeightInput.value = String(preset.team_rating_weight ?? 0);
  minGpInput.value = String(preset.min_gp ?? 0);
}

function renderRows(rows) {
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.rank}</td>
      <td>${row.player_name}</td>
      <td>${row.team ?? "-"}</td>
      <td>${row.gp ?? "-"}</td>
      <td>${Number(row.award_score).toFixed(3)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function runFormula() {
  statusEl.textContent = "Calculating...";

  const payload = {
    season: form.season.value,
    award: awardSelect.value,
    weights: getWeightPayload(),
    team_rating_weight: Number(teamWeightInput.value || 0),
    min_gp: Number(minGpInput.value || 0),
    top_n: Number(topNInput.value || 25),
  };

  try {
    const res = await fetch("/api/awards-formula", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const json = await res.json();
    if (!res.ok) {
      throw new Error(json?.detail || `${res.status} ${res.statusText}`);
    }

    renderRows(json.data || []);
    statusEl.textContent = `Computed ${json.meta.award} rankings for ${json.meta.season}. Eligible players: ${json.meta.eligible_players}.`;
  } catch (error) {
    statusEl.textContent = `Failed to compute formula: ${error}`;
    tbody.innerHTML = "";
  }
}

awardSelect.addEventListener("change", () => {
  applyPreset(awardSelect.value);
});

resetBtn.addEventListener("click", () => {
  metricInputs.forEach((input) => {
    input.value = "0";
  });
  teamWeightInput.value = "0";
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runFormula();
});

applyPreset(awardSelect.value);
runFormula();
