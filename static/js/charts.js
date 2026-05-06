// static/js/charts.js
// Chart.js factory functions: phase intra-day, monthly rolling.
const COLOR_PLAN = "#3880ff";
const COLOR_PRODUCED = "#2dd36f";

function makePhaseChart(canvas, dayTotalGrossH /* 16 or 24 */) {
  return new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        { label: "Plan", data: [], borderColor: COLOR_PLAN, borderWidth: 2,
          pointRadius: 0, fill: false, tension: 0 },
        { label: "Produced", data: [], borderColor: COLOR_PRODUCED, borderWidth: 2.5,
          pointRadius: 3, pointBackgroundColor: COLOR_PRODUCED, fill: false, tension: 0.2 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { type: "linear", min: 0, max: dayTotalGrossH,
             ticks: { color: "#777", font: { size: 9 },
                      callback: (v) => formatXTick(v) } },
        y: { beginAtZero: true,
             ticks: { color: "#777", font: { size: 9 } } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function formatXTick(hoursFrom0730) {
  const totalMinutes = 7 * 60 + 30 + Math.round(hoursFrom0730 * 60);
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function updatePhaseChart(chart, plannedHDay, curvePoints, dayTotalGrossH) {
  chart.data.datasets[0].data = [
    { x: 0, y: 0 },
    { x: dayTotalGrossH, y: plannedHDay },
  ];
  const producedData = (curvePoints || []).map(p => {
    const [h, m] = p.time.split(":").map(Number);
    let elapsed = (h - 7) + (m - 30) / 60;
    if (elapsed < 0) elapsed += 24;
    return { x: elapsed, y: p.h };
  });
  producedData.unshift({ x: 0, y: 0 });
  chart.data.datasets[1].data = producedData;
  chart.update("none");
}

function makeRollingChart(canvas) {
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Plan", data: [], borderColor: COLOR_PLAN, borderWidth: 2,
          pointRadius: 2, fill: false },
        { label: "Produced", data: [], borderColor: COLOR_PRODUCED, borderWidth: 2.5,
          pointRadius: 2, fill: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { ticks: { color: "#777" } },
        y: { beginAtZero: true, ticks: { color: "#777" } },
      },
      plugins: { legend: { display: true, labels: { color: "#ccc" } } },
    },
  });
}

function updateRollingChart(chart, days) {
  chart.data.labels = days.map(d => d.date.slice(5));
  chart.data.datasets[0].data = days.map(d => d.planned_h);
  chart.data.datasets[1].data = days.map(d => d.produced_h);
  chart.update("none");
}
