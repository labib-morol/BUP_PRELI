"""End-to-end HTTP tests using a stubbed language model (no API key required).

Proves the transport contract, the response schema, the error codes and the
hedging behaviour independently of any provider.

    python tools/test_http_stub.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app import pipeline  # noqa: E402
from app.directives import Directive, compute_effects  # noqa: E402
from app.main import app  # noqa: E402
from app.optimizer import to_plan  # noqa: E402
from app.schemas import OptimizeRequest  # noqa: E402

CASES = json.loads(
    (ROOT / "docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json").read_text(encoding="utf-8")
)["cases"]

client = TestClient(app)
failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        failures.append(label)
        print(f"  FAIL {label}")


def truth_readings(case) -> list[list[dict]]:
    readings = []
    for entry in case["expected_output"]["directive_interpretation"]:
        adjustment = entry["structured_adjustment"] or {}
        readings.append([{
            "note_index": entry["note_index"],
            "applies": entry["applies"],
            "directive_type": entry["directive_type"],
            "hours": adjustment.get("hours"),
            "factor": adjustment.get("factor"),
            "minimum_energy_kwh": adjustment.get("minimum_energy_kwh"),
            "max_grid_kwh": adjustment.get("max_grid_kwh"),
        }])
    return readings


async def stub_perfect(notes, capacity_kwh, initial_kwh, minimum_kwh, use_cache=True):
    return stub_perfect.payload


async def stub_disagreeing(notes, capacity_kwh, initial_kwh, minimum_kwh, use_cache=True):
    return stub_disagreeing.payload


def install(stub, case=None, readings=None):
    stub.payload = readings if readings is not None else truth_readings(case)
    pipeline.gather_readings = stub


def test_health():
    response = client.get("/health")
    check(response.status_code == 200, f"/health status {response.status_code}")
    check(response.json() == {"status": "ok"}, "/health body")


def test_contract_errors():
    bad_json = client.post("/optimize-energy", content=b"{not json",
                           headers={"content-type": "application/json"})
    check(bad_json.status_code == 400, f"malformed JSON -> {bad_json.status_code} (want 400)")

    case = CASES[0]["input"]
    short_hours = dict(case, hours=case["hours"][:23])
    response = client.post("/optimize-energy", json=short_hours)
    check(response.status_code == 422, f"23 hours -> {response.status_code} (want 422)")

    no_notes = dict(case, operator_notes=[])
    response = client.post("/optimize-energy", json=no_notes)
    check(response.status_code == 422, f"empty notes -> {response.status_code} (want 422)")

    shuffled = dict(case, hours=list(reversed(case["hours"])))
    response = client.post("/optimize-energy", json=shuffled)
    check(response.status_code == 200, f"shuffled hours -> {response.status_code} (want 200)")


def test_public_cases():
    for case in CASES:
        install(stub_perfect, case)
        response = client.post("/optimize-energy", json=case["input"])
        if response.status_code != 200:
            check(False, f"{case['id']} HTTP {response.status_code}")
            continue
        body = response.json()
        truth = case["expected_output"]["directive_interpretation"]
        check(body["scenario_id"] == case["input"]["scenario_id"], f"{case['id']} scenario_id echo")
        check(len(body["directive_interpretation"]) == len(truth), f"{case['id']} interpretation count")

        for got, want in zip(body["directive_interpretation"], truth):
            check(got["note_index"] == want["note_index"], f"{case['id']} note_index order")
            check(got["applies"] == want["applies"], f"{case['id']} applies")
            check(got["directive_type"] == want["directive_type"],
                  f"{case['id']} type {got['directive_type']} != {want['directive_type']}")
            check(got["structured_adjustment"] == want["structured_adjustment"],
                  f"{case['id']} adjustment {got['structured_adjustment']} != {want['structured_adjustment']}")
            if not want["applies"]:
                check(got["structured_adjustment"] is None, f"{case['id']} no_op adjustment null")

        check(set(body) == {"scenario_id", "directive_interpretation", "hourly_plan",
                            "total_grid_kwh", "total_cost_bdt", "peak_grid_kwh", "plan_summary"},
              f"{case['id']} response fields {sorted(body)}")
        check(len(body["hourly_plan"]) == 24, f"{case['id']} plan length")
        check({row["hour"] for row in body["hourly_plan"]} == set(range(24)), f"{case['id']} plan hours")
        check(all(row["battery_action"] in ("charge", "discharge", "idle")
                  for row in body["hourly_plan"]), f"{case['id']} action enum")

        reference = case["expected_output"]["total_cost_bdt"]
        ratio = min(1.0, reference / body["total_cost_bdt"]) if body["total_cost_bdt"] else 1.0
        check(ratio > 0.9999, f"{case['id']} cost {body['total_cost_bdt']} vs reference {reference}")
    print(f"public cases: {len(CASES)} posted through the HTTP contract")


def test_hedging():
    """One provider misreads the window; the applied plan must still satisfy truth."""
    case = CASES[0]
    truth = truth_readings(case)
    wrong = [dict(entry[0]) for entry in truth]
    if wrong[0]["directive_type"] == "solar_reduction":
        wrong[0] = dict(wrong[0], hours=[11, 12])          # off-by-one misreading
    readings = [[wrong[i], truth[i][0]] for i in range(len(truth))]
    install(stub_disagreeing, readings=readings)

    response = client.post("/optimize-energy", json=case["input"])
    check(response.status_code == 200, f"hedged request HTTP {response.status_code}")
    body = response.json()

    request = OptimizeRequest(**case["input"])
    truth_directives = [
        Directive(
            directive_type=entry["directive_type"],
            hours=tuple((entry["structured_adjustment"] or {}).get("hours") or ()),
            factor=(entry["structured_adjustment"] or {}).get("factor"),
            minimum_energy_kwh=(entry["structured_adjustment"] or {}).get("minimum_energy_kwh"),
            max_grid_kwh=(entry["structured_adjustment"] or {}).get("max_grid_kwh"),
        )
        for entry in case["expected_output"]["directive_interpretation"]
    ]
    effects = compute_effects(request.solar_profile, request.battery.minimum_energy_kwh,
                              truth_directives)
    rows = {row["hour"]: row for row in body["hourly_plan"]}
    for hour in (12, 13):
        check(rows[hour]["solar_used_kwh"] <= effects.effective_solar[hour] + 1e-3,
              f"hedged h{hour} solar {rows[hour]['solar_used_kwh']} > effective "
              f"{effects.effective_solar[hour]}")
    print("hedging: plan satisfies ground truth even though one provider disagreed")


def test_zero_tariff_degeneracy():
    """A free hour must not produce simultaneous charge and discharge."""
    case = json.loads(json.dumps(CASES[0]["input"]))
    case["scenario_id"] = "SYNTH-ZERO-TARIFF"
    for hour in case["hours"]:
        hour["tariff_bdt_per_kwh"] = 0.0
    install(stub_perfect, readings=[[{"note_index": 0, "directive_type": "no_op"}],
                                    [{"note_index": 1, "directive_type": "no_op"}]])
    response = client.post("/optimize-energy", json=case)
    check(response.status_code == 200, f"zero tariff HTTP {response.status_code}")
    if response.status_code == 200:
        actions = [row["battery_action"] for row in response.json()["hourly_plan"]]
        check(all(a in ("charge", "discharge", "idle") for a in actions), "zero tariff actions valid")
        check(response.json()["total_cost_bdt"] == 0.0, "zero tariff cost is zero")
    print("zero tariff: single action per hour preserved")


def test_degraded_no_provider():
    install(stub_perfect, readings=[[] for _ in CASES[0]["input"]["operator_notes"]])
    response = client.post("/optimize-energy", json=CASES[0]["input"])
    check(response.status_code == 200, f"no provider HTTP {response.status_code} (want 200, not 5xx)")
    if response.status_code == 200:
        body = response.json()
        check(all(e["directive_type"] == "no_op" for e in body["directive_interpretation"]),
              "no provider -> no_op interpretation")
        check(len(body["hourly_plan"]) == 24, "no provider -> still a 24-hour plan")
        check("Warning" in body["plan_summary"], "no provider -> summary warns")
    print("no provider: controlled degradation instead of a 5xx")


if __name__ == "__main__":
    test_health()
    test_contract_errors()
    test_public_cases()
    test_hedging()
    test_zero_tariff_degeneracy()
    test_degraded_no_provider()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for item in failures:
            print(" -", item)
        sys.exit(1)
    print("ALL STUB HTTP TESTS PASSED")
