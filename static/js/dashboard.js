// static/js/dashboard.js
// Builds page DOM, polls APIs, updates DOM + charts.

const DASH = document.getElementById("dash");
const POLLING_MS = parseInt(DASH.dataset.pollingSeconds, 10) * 1000;
const PHASES = window.MONITORED_PHASES || [];

const pageCharts = {};
let totalChart = null;
let rollingChart = null;

function hms(d) {
  const pad = n => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function updateClock() {
  const now = new Date();
  document.getElementById("hdr-time").textContent = hms(now);
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const pad = n => String(n).padStart(2, "0");
  document.getElementById("hdr-date").textContent =
    `${days[now.getDay()]} ${pad(now.getDate())}/${pad(now.getMonth() + 1)}/${now.getFullYear()}`;
}
setInterval(updateClock, 1000);
updateClock();

function buildPages() {
  const pagesContainer = document.getElementById("pages");
  pagesContainer.innerHTML = "";
  const pages = [];
  for (let i = 0; i < PHASES.length; i += 2) {
    pages.push(PHASES.slice(i, i + 2));
  }

  pages.forEach((phaseGroup, idx) => {
    const pg = document.createElement("div");
    pg.className = "page" + (idx === 0 ? " active" : "");
    pg.dataset.kind = "phases";
    pg.innerHTML = `<div class="panels">${phaseGroup.map(name => `
      <div class="panel" data-phase="${name}">
        <div class="panel-head">
          <div class="panel-name">${name}</div>
          <div class="badge red" data-role="badge">--</div>
        </div>
        <div class="panel-body">
          <div class="chart-mini"><canvas data-role="chart"></canvas></div>
          <div class="kpi-grid">
            <div class="kpi-cell planned"><div class="lbl">Shift plan</div><div class="v" data-role="shift-plan">--</div><div class="s" data-role="shift-plan-by-now">by now --</div></div>
            <div class="kpi-cell produced"><div class="lbl">Shift produced</div><div class="v" data-role="shift-prod">--</div><div class="s">shift in progress</div></div>
            <div class="kpi-cell planned"><div class="lbl">Day plan</div><div class="v" data-role="day-plan">--</div><div class="s" data-role="day-plan-by-now">by now --</div></div>
            <div class="kpi-cell produced"><div class="lbl">Day produced</div><div class="v" data-role="day-prod">--</div><div class="s">cumul.</div></div>
            <div class="kpi-delta neg" data-role="delta"><div class="lbl">Δ vs expected (day)</div><div class="v">--</div></div>
          </div>
        </div>
      </div>
    `).join("")}</div>`;
    pagesContainer.appendChild(pg);
    pageCharts[idx] = {};
    pg.querySelectorAll("[data-phase]").forEach(panel => {
      const phaseName = panel.dataset.phase;
      const canvas = panel.querySelector("[data-role=chart]");
      pageCharts[idx][phaseName] = makePhaseChart(canvas, 16);
    });
  });

  // Total Summary page
  const totalPg = document.createElement("div");
  totalPg.className = "page";
  totalPg.dataset.kind = "total";
  totalPg.innerHTML = `
    <div class="panel" style="margin-top:12px">
      <div class="panel-head"><div class="panel-name">Total Summary — Today</div></div>
      <div class="panel-body">
        <div class="chart-mini"><canvas id="total-chart"></canvas></div>
        <div class="kpi-grid">
          <div class="kpi-cell planned"><div class="lbl">Day plan</div><div class="v" id="tot-plan">--</div></div>
          <div class="kpi-cell planned"><div class="lbl">By now</div><div class="v" id="tot-plan-by-now">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Produced</div><div class="v" id="tot-prod">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Coverage</div><div class="v" id="tot-cov">--</div></div>
          <div class="kpi-delta" id="tot-delta"><div class="lbl">Δ vs expected (day)</div><div class="v">--</div></div>
        </div>
      </div>
    </div>`;
  pagesContainer.appendChild(totalPg);
  totalChart = makePhaseChart(document.getElementById("total-chart"), 16);

  // Monthly Rolling + YTD page
  const rollingPg = document.createElement("div");
  rollingPg.className = "page";
  rollingPg.dataset.kind = "rolling";
  rollingPg.innerHTML = `
    <div class="panel" style="margin-top:12px">
      <div class="panel-head"><div class="panel-name">Monthly Rolling + YTD</div></div>
      <div class="panel-body" style="grid-template-columns:1.7fr 1fr">
        <div class="chart-mini" style="min-height:260px"><canvas id="rolling-chart"></canvas></div>
        <div class="kpi-grid" style="grid-template-columns:1fr">
          <div class="kpi-cell planned"><div class="lbl">Month plan</div><div class="v" id="m-plan">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Month produced</div><div class="v" id="m-prod">--</div></div>
          <div class="kpi-cell"><div class="lbl">Month coverage</div><div class="v" id="m-cov">--</div></div>
          <div class="kpi-cell planned"><div class="lbl">YTD plan</div><div class="v" id="y-plan">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">YTD produced</div><div class="v" id="y-prod">--</div></div>
          <div class="kpi-cell"><div class="lbl">YTD coverage</div><div class="v" id="y-cov">--</div></div>
        </div>
      </div>
    </div>`;
  pagesContainer.appendChild(rollingPg);
  rollingChart = makeRollingChart(document.getElementById("rolling-chart"));

  return pages.length + 2;
}

const TOTAL_PAGES = buildPages();

async function fetchAndUpdate() {
  try {
    const [phasesResp, totalsResp, rollingResp, healthResp] = await Promise.all([
      fetch("/api/phases").then(r => r.json()),
      fetch("/api/totals").then(r => r.json()),
      fetch("/api/rolling-month").then(r => r.json()),
      fetch("/api/health").then(r => r.json()),
    ]);

    const dayTotalGross = 16;  // MVP: assume 2 shifts. Phase 2 will derive from API.

    document.getElementById("hdr-day-plan").textContent = (totalsResp.planned_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("hdr-day-plan-by-now").textContent = "by now: " + (totalsResp.planned_h_so_far_day ?? 0).toFixed(2) + " h";
    document.getElementById("hdr-produced").textContent = (totalsResp.produced_h_day ?? 0).toFixed(2) + " h";
    const dlt = totalsResp.delta_vs_expected_day ?? 0;
    document.getElementById("hdr-delta").textContent = (dlt >= 0 ? "+" : "") + dlt.toFixed(2) + " h";
    document.getElementById("hdr-delta-status").textContent = dlt >= 0 ? "ahead" : "behind";
    document.getElementById("hdr-coverage").textContent = (totalsResp.coverage_pct_day ?? 0).toFixed(1) + " %";

    Object.entries(phasesResp.phases || {}).forEach(([phaseName, k]) => {
      const panel = document.querySelector(`[data-phase="${phaseName}"]`);
      if (!panel) return;
      const set = (role, v) => { const el = panel.querySelector(`[data-role="${role}"]`); if (el) el.textContent = v; };
      const badge = panel.querySelector("[data-role=badge]");
      badge.className = `badge ${k.status_color}`;
      const dlts = k.delta_vs_expected_shift;
      badge.textContent = `${k.shift_code} · ${dlts >= 0 ? "+" : ""}${dlts.toFixed(2)} h`;
      set("shift-plan", k.planned_h_shift.toFixed(2) + " h");
      set("shift-plan-by-now", "by now " + k.planned_h_so_far_shift.toFixed(2) + " h");
      set("shift-prod", k.produced_h_shift.toFixed(2) + " h");
      set("day-plan", k.planned_h_day.toFixed(2) + " h");
      set("day-plan-by-now", "by now " + k.planned_h_so_far_day.toFixed(2) + " h");
      set("day-prod", k.produced_h_day.toFixed(2) + " h");
      const dEl = panel.querySelector("[data-role=delta]");
      const d = k.delta_vs_expected_day;
      dEl.className = "kpi-delta " + (d >= 0 ? "pos" : "neg");
      dEl.querySelector(".v").textContent = (d >= 0 ? "+" : "") + d.toFixed(2) + " h";

      Object.values(pageCharts).forEach(group => {
        if (group[phaseName]) {
          updatePhaseChart(group[phaseName], k.planned_h_day, k.curve_points, dayTotalGross);
        }
      });
    });

    document.getElementById("tot-plan").textContent = (totalsResp.planned_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-plan-by-now").textContent = (totalsResp.planned_h_so_far_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-prod").textContent = (totalsResp.produced_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-cov").textContent = (totalsResp.coverage_pct_day ?? 0).toFixed(1) + " %";
    const totDelta = document.getElementById("tot-delta");
    totDelta.className = "kpi-delta " + ((totalsResp.delta_vs_expected_day ?? 0) >= 0 ? "pos" : "neg");
    totDelta.querySelector(".v").textContent = ((totalsResp.delta_vs_expected_day ?? 0) >= 0 ? "+" : "") + (totalsResp.delta_vs_expected_day ?? 0).toFixed(2) + " h";

    const totalCurve = aggregateCurves(phasesResp.phases);
    updatePhaseChart(totalChart, totalsResp.planned_h_day ?? 0, totalCurve, dayTotalGross);

    document.getElementById("m-plan").textContent = (rollingResp.month_planned_h ?? 0).toFixed(2) + " h";
    document.getElementById("m-prod").textContent = (rollingResp.month_produced_h ?? 0).toFixed(2) + " h";
    document.getElementById("m-cov").textContent = (rollingResp.month_coverage_pct ?? 0).toFixed(1) + " %";
    document.getElementById("y-plan").textContent = (rollingResp.ytd_planned_h ?? 0).toFixed(2) + " h";
    document.getElementById("y-prod").textContent = (rollingResp.ytd_produced_h ?? 0).toFixed(2) + " h";
    document.getElementById("y-cov").textContent = (rollingResp.ytd_coverage_pct ?? 0).toFixed(1) + " %";
    updateRollingChart(rollingChart, rollingResp.days || []);

    const healthEl = document.getElementById("hdr-health");
    const anyStale = Object.values(healthResp.stale || {}).some(Boolean);
    healthEl.className = "health " + (anyStale ? "stale" : "ok");
    healthEl.textContent = anyStale ? "● data stale" : "● data ok";
  } catch (e) {
    console.error("update failed", e);
    document.getElementById("hdr-health").className = "health error";
    document.getElementById("hdr-health").textContent = "● error";
  }
}

function aggregateCurves(phaseDict) {
  const timeMap = new Map();
  Object.values(phaseDict || {}).forEach(p => {
    (p.curve_points || []).forEach(cp => {
      timeMap.set(cp.time, (timeMap.get(cp.time) || 0) + cp.h);
    });
  });
  return Array.from(timeMap.entries()).sort().map(([t, h]) => ({ time: t, h }));
}

setInterval(fetchAndUpdate, POLLING_MS);
fetchAndUpdate();
