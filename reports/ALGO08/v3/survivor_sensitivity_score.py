"""Compare frozen sensitivity diagnostics with authenticated saved terminal outputs."""

from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCORE = HERE / "measurements"
SHM = Path("/dev/shm")
ARMS = ("c0", "fitted_c")
CASES = {
    "0016": ("leo-v3-survivor-stress-dev01", "development"),
    "0316": ("leo-v3-survivor-stress-dev01", "development"),
    "0008": ("leo-v3-survivor-stress-held01", "held"),
    "0402": ("leo-v3-survivor-stress-hard03", "held"),
}
PAIR = {
    "0008": ("leo-cumulative-grid-projection-01/dense-pair/combined", "f378b41ceaf7a874aeb2b7cb02636647fa01b32c0ddc70efb65fd566a724182f",
             "leo-v3-mixed-final-0008-01/candidate", "dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a"),
    "0316": ("leo-v3-saved-0316-pair-01/cumulative", "cc34b01ee1145cbc7f9388eab33da5e120011a86c0911f8876260ca9ad27ab25",
             "leo-v3-final-0316-transfer-result02/candidate", "ebbaed6c90a1d03b229b4199835bcc399984eee2524755b8b2e7d0470c907d1f"),
    "0402": ("leo-v3-isolated-salvage-0402-run01/candidate", "fdc6fd2b3c6c0eac6d1859ce748129bfb844a259040e2324f96bb09a7df5139f",
             "leo-v3-named-survivor-fit-0402-01/fixed", "f8db8fada16d4061de4f5e6c8ecf1394ea9a397b74e5ccbf68108caf16682a22"),
}
DEV = "leo-v3-portable-repaired-0016-containing-01"
WEAK_FULL = "d3a8a2ad37f94c1447092bf6e1e2df33bf8a9c34f43785db5f92805b29cb21b6"
WEAK_SCORE = "98365718e60164134084810baf1890aa81a9dc9c2e1804bd77d2b1b4ca1c2d79"
DENSE_FEATURE = "f12f4df50e23fc2b167b78afa453c3bc004bd49ef6dd59d00fdf330e1ee92229"


def read(path, pin=None):
    raw = path.read_bytes()
    data = decompress(raw) if path.suffix == ".gz" else raw
    if pin is not None and sha256(data).hexdigest() != pin:
        raise ValueError(f"Scientific source changed at {path}")
    return json.loads(data)


def receipt(root, pin):
    return read(SHM / root / "joint-research-receipt.json", pin)


def scores(case):
    if case == "0016":
        current = read(SHM / DEV / "complete-scope.json", WEAK_SCORE)["runs"]["ordinary"]
        named = read(SCORE / "raw-0016-best.json.gz", "348ed9bffa27185f39673bdd0ee20ec2418a9b1e8723f19a950f4e5bd4e399a8")
        named = named["geographic"]["runs"]["stock"]
        return dict(full=current["horizontal_error_km"], named=named["horizontal_error_km"]), named["rf_rms_hz"]
    if case == "0316":
        current = read(SCORE / "named-final-0316.json.gz", "a9b58b411f29e430e4df47829b3b15e95cf2c0d5d9ef80bed521a92b9e83647b")
        geo = current["geographic"]["runs"]
        error = {target: geo[name]["horizontal_error_km"] for target, name in
                 (("full", "candidate"), ("warm", "earlier_cumulative"), ("named", "named"))}
        return error, geo["named"]["rf_rms_hz"]
    if case == "0008":
        current = read(SCORE / "mixed-named-finish-0008.json.gz", "da352d9b4b08a7d79be2fb46735afc7b63f2fee8bb29c1c886e268fae012dd1d")
        named = current["earlier_named_raw"]["arms"]
        error = {target: {arm: row["position_error_km"] for arm, row in source.items()} for target, source in
                 (("full", current["solution"]), ("warm", current["previous_mixed"]["arms"]), ("named", named))}
        return error, {arm: row["rf_rms_hz"] for arm, row in named.items()}
    current = read(SCORE / "named-survivor-fit-0402.json.gz", "01424260596bde4c31c31d03f794f8c5279418122ef1d2bf05cc634dc52d6800")
    geo = current["horizontal_error_km"]
    named = current["fits"]["named"]
    return dict(full=geo["fixed"], warm=geo["warm"], named=geo["named"]), {arm: value["rf_rms_hz"] for arm, value in named.items()}


def archived(case):
    if case == "0016":
        return None, receipt(DEV + "/ordinary/selective", WEAK_FULL)
    warm_path, warm_pin, full_path, full_pin = PAIR[case]
    return receipt(warm_path, warm_pin), receipt(full_path, full_pin)


def matches_owners(port, archive):
    factors = [(oid, row["norad"], role)
               for role, fragments in (("conditional", port["curved"]), ("predictive", port["predictive"]))
               for row in fragments.values() for oid in row["ids"]]
    if len({row[0] for row in factors}) != len(factors):
        raise ValueError("Duplicated stable observation identity in tested fit")
    return all(sorted(map(tuple, archive["selected_rows"][arm])) == sorted(factors) for arm in ARMS)


def score(case):
    from tools.pipeline_eval.scoring import distance_km

    folder, split = CASES[case]
    root = SHM / folder
    pin = DENSE_FEATURE if case == "0008" else read(root / "feature-seal.json")[case]
    port = read(root / case / "probe.json", pin)
    clocks = read(root / f"{case}-clock.json")
    provenance = read(root / "binding.json")
    warm, full = archived(case)
    errors, named_rf = scores(case)
    if (port["handoff"][0] != 1 or port["waveform_calls"] or port["case"] != case or clocks["exit_code"]
            or not matches_owners(port, full)):
        raise ValueError("A stage does not match the sealed availability or original full roster")
    actual = port["fits"]
    signed = full["route_details"]
    fit_arms = signed["signed"]["finish"]
    if signed["named_survivor_fit"]["status"] != "accepted" or full["receipt"]["decision"] != "complete":
        raise ValueError("Expected an accepted current named finish for the comparison")
    full_fit_cpu = signed["signed_refit_clocks"]["cpu_s"]
    added_cpu = port["warm_clocks"]["cpu_s"] + port["stress_clocks"]["cpu_s"]
    same_warm = False
    exact_roster = None
    displacement = None
    if warm is not None:
        exact_roster = (full["selected_rows"] == warm["selected_rows"] and
                        full["receipt"]["region"] == warm["receipt"]["region"] and warm["receipt"]["decision"] == "complete")
        earlier = warm["route_details"]["warm_signed_fit"]
        same_warm = earlier["accepted"] and set(actual) == set(ARMS) and all(
            all(actual[arm][x] == earlier["finished_arms"][arm][y] for x, y in (
                ("latlon", "latlon"), ("rf_rms_hz", "rf_rms_hz"), ("position", "east_north_km"), ("objective", "objective")))
            for arm in ARMS)
        if same_warm and exact_roster:
            displacement = {arm: distance_km(actual[arm]["latlon"], fit_arms[arm]["latlon"]) for arm in ARMS}
    matched = bool(same_warm and exact_roster)
    false_skip = port["accepted"] and (not matched or any(
        displacement[arm] > .010 or errors["warm"][arm] - errors["full"][arm] > .010
        or errors["warm"][arm] - errors["named"][arm] > .010 for arm in ARMS))
    rf = dict(named=named_rf, full={arm: fit_arms[arm]["rf_rms_hz"] for arm in ARMS},
              warm={arm: actual[arm]["rf_rms_hz"] for arm in actual})
    return dict(split=split, feature_sha256=pin, provenance=provenance, clocks=clocks,
                staged_request_sha256=port["staged_request_sha256"], owners_per_arm={arm: len(full["selected_rows"][arm])
                for arm in ARMS}, same_archived_warm_solution=matched, exact_warm_full_roster=exact_roster,
                warm_passed=port["warm_passed"], warm_reasons=port["warm_reasons"], accepted=port["accepted"],
                stress=port["stress"], horizontal_error_km=errors, rf_rms_hz=rf,
                displacement_from_full_km=displacement, false_skip=bool(false_skip),
                warm_cpu_s=port["warm_clocks"]["cpu_s"], stress_cpu_s=port["stress_clocks"]["cpu_s"],
                archived_full_finish_cpu_s=full_fit_cpu, fallback_finish_cpu_s=full_fit_cpu + added_cpu,
                if_accepted_headroom_cpu_s=full_fit_cpu - added_cpu)


def report():
    cases = {case: score(case) for case in CASES}
    eligible = all(not row["false_skip"] for row in cases.values()) and any(
        row["split"] == "held" and row["accepted"] and row["same_archived_warm_solution"]
        and row["if_accepted_headroom_cpu_s"] >= .500 for row in cases.values())
    failures = {name: read(SHM / name / "0402-clock.json") for name in (
        "leo-v3-survivor-stress-held01", "leo-v3-survivor-stress-hard02")}
    return dict(cases=cases, eligible_for_full_held_publication=eligible, measured_probe_processes=4,
                failed_0402_setups=failures, complete_new_publications=0, waveform_reads=0)


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
