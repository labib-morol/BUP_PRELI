"""Independent verification that our reading of the GridWise spec is correct.

Two checks per public sample case:
  1. REPLAY  - does the reference hourly_plan satisfy every rule in the Problem Statement?
  2. OPTIMUM - does our LP reach the same minimum cost as the reference plan?

If both pass for all 10 cases, our optimizer formulation matches the organizer model.
"""
import json
import sys
from pathlib import Path

import pulp

TOL = 1e-6
CASES = Path(__file__).resolve().parents[1] / "docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def effective_solar(hours, directives):
    eff = [h["solar_kwh"] for h in hours]
    for d in directives:
        if d["directive_type"] == "solar_reduction" and d.get("applies"):
            for hr in d["structured_adjustment"]["hours"]:
                eff[hr] = eff[hr] * d["structured_adjustment"]["factor"]
    return eff


def replay(case, plan, directives):
    """Return list of violations when replaying a plan against the spec."""
    inp = case["input"]
    bat = inp["battery"]
    errs = []
    eff = effective_solar(inp["hours"], directives)

    if len(plan) != 24 or sorted(p["hour"] for p in plan) != list(range(24)):
        return ["hourly_plan is not exactly hours 0..23"]

    plan = sorted(plan, key=lambda p: p["hour"])
    by_hour = {p["hour"]: p for p in plan}

    # directive lookup
    reserve_extra = {}
    no_charge, no_discharge, grid_cap = set(), set(), {}
    for d in directives:
        if not d.get("applies"):
            continue
        adj = d["structured_adjustment"]
        if d["directive_type"] == "minimum_battery_reserve":
            for hr in adj["hours"]:
                reserve_extra[hr] = max(reserve_extra.get(hr, 0), adj["minimum_energy_kwh"])
        elif d["directive_type"] == "no_charge_window":
            no_charge.update(adj["hours"])
        elif d["directive_type"] == "no_discharge_window":
            no_discharge.update(adj["hours"])
        elif d["directive_type"] == "max_grid_window":
            for hr in adj["hours"]:
                grid_cap[hr] = min(grid_cap.get(hr, float("inf")), adj["max_grid_kwh"])

    E = bat["initial_energy_kwh"]
    for p in plan:
        h = p["hour"]
        g, s, act, kwh = p["grid_kwh"], p["solar_used_kwh"], p["battery_action"], p["battery_kwh"]
        for name, v in (("grid_kwh", g), ("solar_used_kwh", s), ("battery_kwh", kwh)):
            if v < -TOL:
                errs.append(f"h{h}: {name} negative ({v})")
        if act not in ("charge", "discharge", "idle"):
            errs.append(f"h{h}: bad battery_action {act}")
        if act == "idle" and abs(kwh) > TOL:
            errs.append(f"h{h}: idle with battery_kwh={kwh}")
        charge = kwh if act == "charge" else 0.0
        discharge = kwh if act == "discharge" else 0.0
        if charge > bat["max_charge_kwh_per_hour"] + TOL:
            errs.append(f"h{h}: charge {charge} > max_charge")
        if discharge > bat["max_discharge_kwh_per_hour"] + TOL:
            errs.append(f"h{h}: discharge {discharge} > max_discharge")
        if h in no_charge and charge > TOL:
            errs.append(f"h{h}: charge inside no_charge_window")
        if h in no_discharge and discharge > TOL:
            errs.append(f"h{h}: discharge inside no_discharge_window")
        # balance
        lhs = g + s + discharge
        rhs = inp["hours"][h]["demand_kwh"] + charge
        if abs(lhs - rhs) > 1e-4:
            errs.append(f"h{h}: energy balance {lhs} != {rhs}")
        if s > eff[h] + 1e-4:
            errs.append(f"h{h}: solar_used {s} > effective solar {eff[h]}")
        if h in grid_cap and g > grid_cap[h] + 1e-4:
            errs.append(f"h{h}: grid {g} > cap {grid_cap[h]}")
        E = E + charge - discharge
        if E < bat["minimum_energy_kwh"] - 1e-4:
            errs.append(f"h{h}: E {E} < base minimum")
        if h in reserve_extra and E < reserve_extra[h] - 1e-4:
            errs.append(f"h{h}: E {E} < directive reserve {reserve_extra[h]}")
        if E > bat["capacity_kwh"] + 1e-4:
            errs.append(f"h{h}: E {E} > capacity")
        if abs(p["battery_energy_after_kwh"] - E) > 1e-4:
            errs.append(f"h{h}: reported E_after {p['battery_energy_after_kwh']} != replayed {E}")
    if abs(E - bat["initial_energy_kwh"]) > 1e-4:
        errs.append(f"end-of-day E {E} != initial {bat['initial_energy_kwh']}")

    # totals
    exp = case["expected_output"]
    tg = sum(p["grid_kwh"] for p in plan)
    tc = sum(p["grid_kwh"] * inp["hours"][p["hour"]]["tariff_bdt_per_kwh"] for p in plan)
    pk = max(p["grid_kwh"] for p in plan)
    if abs(tg - exp["total_grid_kwh"]) > 0.02:
        errs.append(f"total_grid_kwh recompute {tg} != {exp['total_grid_kwh']}")
    if abs(tc - exp["total_cost_bdt"]) > 0.02:
        errs.append(f"total_cost recompute {tc} != {exp['total_cost_bdt']}")
    if abs(pk - exp["peak_grid_kwh"]) > 0.02:
        errs.append(f"peak recompute {pk} != {exp['peak_grid_kwh']}")
    return errs


def solve(case, directives):
    """LP: minimize grid cost subject to base rules + given directives."""
    inp = case["input"]
    bat = inp["battery"]
    hours = inp["hours"]
    eff = effective_solar(hours, directives)
    cap, init, base_min = bat["capacity_kwh"], bat["initial_energy_kwh"], bat["minimum_energy_kwh"]
    mc, md = bat["max_charge_kwh_per_hour"], bat["max_discharge_kwh_per_hour"]

    reserve, nchg, ndis, gcap = {}, set(), set(), {}
    for d in directives:
        if not d.get("applies"):
            continue
        adj = d["structured_adjustment"]
        if d["directive_type"] == "minimum_battery_reserve":
            for hr in adj["hours"]:
                reserve[hr] = max(base_min, adj["minimum_energy_kwh"])
        elif d["directive_type"] == "no_charge_window":
            nchg.update(adj["hours"])
        elif d["directive_type"] == "no_discharge_window":
            ndis.update(adj["hours"])
        elif d["directive_type"] == "max_grid_window":
            for hr in adj["hours"]:
                gcap[hr] = min(gcap.get(hr, float("inf")), adj["max_grid_kwh"])

    p = pulp.LpProblem("gridwise", pulp.LpMinimize)
    g = [pulp.LpVariable(f"g{h}", lowBound=0) for h in range(24)]
    s = [pulp.LpVariable(f"s{h}", 0, eff[h]) for h in range(24)]
    c = [pulp.LpVariable(f"c{h}", 0, None if h in nchg else mc) for h in range(24)]
    d_ = [pulp.LpVariable(f"d{h}", 0, None if h in ndis else md) for h in range(24)]
    E = [pulp.LpVariable(f"E{h}", 0, cap) for h in range(24)]

    p += pulp.lpSum(g[h] * hours[h]["tariff_bdt_per_kwh"] for h in range(24))
    for h in range(24):
        p += g[h] + s[h] + d_[h] == hours[h]["demand_kwh"] + c[h]
        prev = init if h == 0 else E[h - 1]
        p += E[h] == prev + c[h] - d_[h]
        lo = max(base_min, reserve.get(h, 0))
        p += E[h] >= lo
        if h in gcap:
            p += g[h] <= gcap[h]
        if h in nchg:
            p += c[h] == 0
        if h in ndis:
            p += d_[h] == 0
    p += E[23] == init

    status = p.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        return None, pulp.LpStatus[status]
    return pulp.value(p.objective), pulp.LpStatus[status]


def main():
    data = json.loads(CASES.read_text(encoding="utf-8"))
    ok = True
    for case in data["cases"]:
        exp = case["expected_output"]
        dirs = exp["directive_interpretation"]
        errs = replay(case, exp["hourly_plan"], dirs)
        opt, status = solve(case, dirs)
        ref = exp["total_cost_bdt"]
        gap = None if opt is None else opt - ref
        verdict = "OK"
        if errs or opt is None or abs(gap) > 0.01:
            verdict = "FAIL"
            ok = False
        print(f"{case['id']:10s} {verdict:4s}  replay_errs={len(errs)}  "
              f"lp={None if opt is None else round(opt,4)} ref={ref} gap={None if gap is None else round(gap,6)} status={status}")
        for e in errs:
            print("      -", e)
    print("\nMODEL VERIFIED" if ok else "\nMODEL MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
