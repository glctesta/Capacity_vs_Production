// static/js/rotation.js
// Auto-rotates pages, supports manual prev/next/dropdown/dot click + pause.
const ROT_MS = parseInt(DASH.dataset.rotationSeconds, 10) * 1000;
const PAUSE_MS = parseInt(DASH.dataset.manualPauseSeconds, 10) * 1000;

const pages = Array.from(document.querySelectorAll(".page"));
let currentIdx = 0;
let paused = false;
let manualPauseUntil = 0;
let elapsedInPage = 0;

function pageTitle(idx) {
  const pg = pages[idx];
  const kind = pg.dataset.kind;
  if (kind === "total") return `${idx + 1} — Total Summary`;
  if (kind === "rolling") return `${idx + 1} — Monthly Rolling + YTD`;
  const phaseNames = Array.from(pg.querySelectorAll("[data-phase]")).map(p => p.dataset.phase);
  return `${idx + 1} — ${phaseNames.join(" + ")}`;
}

function buildSelectAndDots() {
  const sel = document.getElementById("page-select");
  sel.innerHTML = pages.map((_, i) => `<option value="${i}">${pageTitle(i)}</option>`).join("");
  sel.value = currentIdx;
  sel.addEventListener("change", e => goTo(parseInt(e.target.value, 10), true));

  const dotsEl = document.getElementById("nav-dots");
  dotsEl.innerHTML = pages.map((_, i) => `<span class="dot" data-i="${i}"></span>`).join("");
  dotsEl.querySelectorAll(".dot").forEach(el => {
    el.addEventListener("click", () => goTo(parseInt(el.dataset.i, 10), true));
  });

  document.getElementById("btn-prev").addEventListener("click", () => goTo((currentIdx - 1 + pages.length) % pages.length, true));
  document.getElementById("btn-next").addEventListener("click", () => goTo((currentIdx + 1) % pages.length, true));
  document.getElementById("btn-pause").addEventListener("click", togglePause);
}

function goTo(idx, manual) {
  pages[currentIdx].classList.remove("active");
  pages[idx].classList.add("active");
  currentIdx = idx;
  document.getElementById("page-select").value = idx;
  document.querySelectorAll("#nav-dots .dot").forEach((d, i) => d.classList.toggle("act", i === idx));
  elapsedInPage = 0;
  if (manual) {
    manualPauseUntil = Date.now() + PAUSE_MS;
    document.querySelector(".timer-bar").classList.add("paused");
  }
}

function togglePause() {
  paused = !paused;
  document.getElementById("btn-pause").textContent = paused ? "▶" : "⏸";
  document.getElementById("btn-pause").title = paused ? "Resume rotation" : "Pause rotation";
  document.querySelector(".timer-bar").classList.toggle("paused", paused);
}

function tick() {
  const now = Date.now();
  const inManualPause = now < manualPauseUntil;
  if (inManualPause) {
    document.querySelector(".timer-bar").classList.add("paused");
  } else {
    document.querySelector(".timer-bar").classList.toggle("paused", paused);
  }
  if (!paused && !inManualPause) {
    elapsedInPage += 1000;
    if (elapsedInPage >= ROT_MS) {
      goTo((currentIdx + 1) % pages.length, false);
    }
  }
  const remainingSec = Math.max(0, Math.ceil((ROT_MS - elapsedInPage) / 1000));
  document.getElementById("timer-fill").style.width = `${(elapsedInPage / ROT_MS) * 100}%`;
  document.getElementById("nav-status-text").textContent =
    `page ${currentIdx + 1} / ${pages.length} · ${paused ? "paused" : (inManualPause ? "manual pause" : "auto in " + remainingSec + "s")}`;
}

buildSelectAndDots();
goTo(0, false);
setInterval(tick, 1000);
