const searchForm = document.getElementById('gf-search-controls');
const onDayForm = document.getElementById('gf-on-day-controls');
const breakoutForm = document.getElementById('gf-breakout-controls');
const statusEl = document.getElementById('gf-status');
const tbody = document.querySelector('#gf-results tbody');

function fmt(v) {
  if (v === null || v === undefined || v === '') return '-';
  return typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(3) : `${v}`;
}

function render(rows) {
  tbody.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmt(r.player_name)}</td>
      <td>${fmt(r.game_date)}</td>
      <td>${fmt(r.matchup)}</td>
      <td>${fmt(r.pts)}</td>
      <td>${fmt(r.reb)}</td>
      <td>${fmt(r.ast)}</td>
      <td>${fmt(r.fgm)}</td>
      <td>${fmt(r.fga)}</td>
      <td>${fmt(r.fg3m)}</td>
      <td>${fmt(r.game_score)}</td>
      <td>${fmt(r.breakout_score)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function run(endpoint, form, label) {
  const fd = new FormData(form);
  const params = new URLSearchParams();
  for (const [k, v] of fd.entries()) {
    if (`${v}`.trim() !== '') params.set(k, v);
  }
  statusEl.textContent = `Loading ${label}...`;
  try {
    const res = await fetch(`${endpoint}?${params.toString()}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `${res.status} ${res.statusText}`);
    render(json.data || []);
    statusEl.textContent = `${label}: loaded ${json.meta?.total ?? (json.data || []).length} rows.`;
  } catch (err) {
    statusEl.textContent = `Failed ${label}: ${err}`;
    tbody.innerHTML = '';
  }
}

searchForm.addEventListener('submit', (e) => {
  e.preventDefault();
  run('/api/game-finder/search', searchForm, 'Search');
});

onDayForm.addEventListener('submit', (e) => {
  e.preventDefault();
  run('/api/game-finder/on-this-day', onDayForm, 'On This Day');
});

breakoutForm.addEventListener('submit', (e) => {
  e.preventDefault();
  run('/api/game-finder/breakouts', breakoutForm, 'Breakouts');
});
