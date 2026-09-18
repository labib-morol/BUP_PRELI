"""Interactive demo page for humans (and for the submission video).

The judged endpoints are unchanged; this only adds a browser-friendly surface for
demonstrating the pipeline without a terminal. Worth having because the address bar
can only issue GETs, so `POST /optimize-energy` returns 405 to a plain URL - which
makes a "just show the URL" demo impossible without a page like this.

No external assets: the page is one self-contained document, so it renders identically
inside the Docker image with no network access beyond the service itself.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

CASES = Path(__file__).resolve().parents[1] / "docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GridWise - Smart Campus Energy Optimization</title>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --ink:#e2e8f0; --dim:#94a3b8;
          --ok:#34d399; --warn:#fbbf24; --accent:#38bdf8; }
  * { box-sizing:border-box; }
  body { margin:0; padding:32px; background:var(--bg); color:var(--ink);
         font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .wrap { max-width:1080px; margin:0 auto; }
  h1 { font-size:21px; margin:0 0 4px; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.09em; color:var(--dim);
       margin:26px 0 10px; font-weight:600; }
  .sub { color:var(--dim); margin:0 0 22px; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  select, button { font:inherit; padding:9px 13px; border-radius:8px;
                   border:1px solid var(--line); background:var(--card); color:var(--ink); }
  button { cursor:pointer; background:var(--accent); color:#06263a; border-color:var(--accent);
           font-weight:650; }
  button:disabled { opacity:.55; cursor:default; }
  .note { background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
          border-radius:8px; padding:11px 14px; margin:7px 0; }
  .tag { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px;
         color:var(--accent); }
  .muted { color:var(--dim); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; }
  .stat .k { font-size:11.5px; text-transform:uppercase; letter-spacing:.07em; color:var(--dim); }
  .stat .v { font-size:20px; font-weight:650; margin-top:3px; }
  .verdict { margin-top:12px; padding:10px 14px; border-radius:8px; font-weight:600; }
  .good { background:rgba(52,211,153,.13); color:var(--ok); border:1px solid rgba(52,211,153,.35); }
  .bar { display:flex; align-items:flex-end; gap:2px; height:120px; margin-top:6px;
         padding:8px; background:var(--card); border:1px solid var(--line); border-radius:8px; }
  .bar > div { flex:1; border-radius:2px 2px 0 0; position:relative; }
  .legend { display:flex; gap:16px; font-size:12.5px; color:var(--dim); margin-top:7px; }
  .sw { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; }
  table { width:100%; border-collapse:collapse; font-family:ui-monospace,Menlo,monospace;
          font-size:12.5px; margin-top:6px; }
  th,td { padding:4px 8px; text-align:right; border-bottom:1px solid var(--line); }
  th:first-child, td:first-child { text-align:left; }
  th { color:var(--dim); font-weight:600; }
  .hide { display:none; }
  .err { background:rgba(248,113,113,.13); border:1px solid rgba(248,113,113,.4);
         color:#fca5a5; padding:11px 14px; border-radius:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>GridWise - Smart Campus Energy Optimization</h1>
  <p class="sub">Natural-language operator notes &rarr; LLM interpretation &rarr; deterministic
     guardrails &rarr; linear-programming schedule. Pick a public sample case and run it.</p>

  <div class="row">
    <select id="case"></select>
    <button id="run">Run optimization</button>
    <span id="status" class="muted"></span>
  </div>

  <div id="error" class="err hide"></div>

  <div id="out" class="hide">
    <h2>Operator notes &amp; interpretation</h2>
    <div id="notes"></div>

    <h2>Result</h2>
    <div class="grid" id="stats"></div>
    <div id="verdict" class="verdict"></div>

    <h2>Grid draw per hour (bar height = grid kWh, colour = tariff)</h2>
    <div class="bar" id="chart"></div>
    <div class="legend">
      <span><span class="sw" style="background:#38bdf8"></span>low tariff</span>
      <span><span class="sw" style="background:#818cf8"></span>mid tariff</span>
      <span><span class="sw" style="background:#fbbf24"></span>high tariff</span>
    </div>

    <h2>24-hour plan</h2>
    <table id="plan"></table>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let CASES = [];

async function boot() {
  const res = await fetch("/demo/cases");
  CASES = await res.json();
  $("case").innerHTML = CASES.map(c =>
    `<option value="${c.index}">${c.id} - ${c.label}</option>`).join("");
}

function money(x) { return x.toLocaleString(undefined, {maximumFractionDigits: 2}); }

function render(data, input, reference) {
  $("notes").innerHTML = data.directive_interpretation.map(e => {
    const adj = e.structured_adjustment ? JSON.stringify(e.structured_adjustment) : "null";
    return `<div class="note"><b>note ${e.note_index}</b>
      <span class="tag">${e.directive_type}</span>
      ${e.applies ? `<span class="tag">${adj}</span>` : ""}
      <div class="muted">${e.explanation}</div></div>`;
  }).join("");

  const cost = data.total_cost_bdt;
  $("stats").innerHTML = [
    ["total cost (BDT)", money(cost)],
    ["total grid (kWh)", money(data.total_grid_kwh)],
    ["peak grid (kWh)", money(data.peak_grid_kwh)],
    ["reference cost", reference == null ? "-" : money(reference)]
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

  const optimal = reference == null ? null : Math.abs(cost - reference) <= 0.01;
  if (optimal === null) {
    $("verdict").className = "verdict good";
    $("verdict").textContent = "Plan is valid for the interpreted directives.";
  } else if (optimal) {
    $("verdict").className = "verdict good";
    $("verdict").textContent =
      "OPTIMAL - recalculated cost equals the organizer's reference optimum exactly.";
  } else {
    const ratio = (Math.min(1, reference / cost)).toFixed(4);
    $("verdict").className = "verdict";
    $("verdict").textContent = `Valid plan, cost ratio ${ratio} against the reference.`;
  }

  const plan = data.hourly_plan;
  const peak = Math.max(...plan.map(r => r.grid_kwh), 1);
  const tariffs = input.hours.map(h => h.tariff_bdt_per_kwh);
  const lo = Math.min(...tariffs), hi = Math.max(...tariffs);
  const colour = t => {
    const f = hi > lo ? (t - lo) / (hi - lo) : 0;
    return f > 0.66 ? "#fbbf24" : f > 0.33 ? "#818cf8" : "#38bdf8";
  };
  $("chart").innerHTML = plan.map(r => {
    const tariff = input.hours.find(h => h.hour === r.hour).tariff_bdt_per_kwh;
    return `<div title="hour ${r.hour}: ${r.grid_kwh} kWh at ${tariff} BDT/kWh"
      style="height:${Math.max(2, (r.grid_kwh / peak) * 100)}%;
             background:${colour(tariff)}"></div>`;
  }).join("");

  $("plan").innerHTML = "<tr><th>hour</th><th>grid</th><th>solar</th><th>action</th>" +
    "<th>battery</th><th>E after</th></tr>" + plan.map(r =>
      `<tr><td>${r.hour}</td><td>${r.grid_kwh}</td><td>${r.solar_used_kwh}</td>` +
      `<td>${r.battery_action}</td><td>${r.battery_kwh}</td>` +
      `<td>${r.battery_energy_after_kwh}</td></tr>`).join("");
}

async function run() {
  const index = $("case").value;
  $("error").classList.add("hide");
  $("run").disabled = true;
  $("status").textContent = "running (LLM interpretation + LP solve)...";
  const started = performance.now();
  try {
    const input = await (await fetch(`/demo/cases/${index}`)).json();
    const res = await fetch("/optimize-energy", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(input)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const seconds = ((performance.now() - started) / 1000).toFixed(2);
    $("status").textContent = `completed in ${seconds}s`;
    render(data, input, CASES.find(c => c.index == index).reference);
    $("out").classList.remove("hide");
  } catch (e) {
    $("error").textContent = "Request failed: " + e.message;
    $("error").classList.remove("hide");
    $("status").textContent = "";
  } finally {
    $("run").disabled = false;
  }
}

$("run").addEventListener("click", run);
boot();
</script>
</body>
</html>
"""


def _load_cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def demo_page() -> HTMLResponse:
    return HTMLResponse(PAGE)


def case_index() -> list[dict]:
    return [
        {"index": i, "id": case["id"], "label": case["label"],
         "reference": case["expected_output"]["total_cost_bdt"]}
        for i, case in enumerate(_load_cases())
    ]


def case_input(index: int) -> dict:
    cases = _load_cases()
    if not 0 <= index < len(cases):
        raise HTTPException(status_code=404, detail="no such sample case")
    return cases[index]["input"]
