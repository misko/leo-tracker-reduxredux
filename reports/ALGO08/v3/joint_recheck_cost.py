"""Price the specific 0049 and 0086 saved receiver edits against their measured field budgets."""

import gzip
from hashlib import sha256
import json
from pathlib import Path


DATA = Path(__file__).with_name("measurements")
PINS = {
    "first30-empty-call-roof": "b24250705e44e24f440ed0163a5ee8ccf98f92ee37c5bc5f0f41b75b91c58514",
    "ds30-0049-joint-recovery": "bb6be0710cb1c22ce1399bb870226beffec87394796c897b9c8dd5f576a58ba0",
    "ds30-0086-joint-recovery": "af5df623993d0d9ce8eb95d49fee3a52f8842ce7790d412e8f2718c1ff491250",
}


def read(name):
    body = gzip.decompress((DATA / (name + ".json.gz")).read_bytes())
    if sha256(body).hexdigest() != PINS[name]:
        raise ValueError("The archived measurement changed")
    return json.loads(body)


def additional_work(inserted, replaced, donor):
    def seconds(mode, output):
        return donor[mode][output]["wall_ns"]["mean"] / 1e9

    full = (inserted + replaced) * seconds("full", "positive")
    skipped = inserted * seconds("short_primary", "empty") + replaced * seconds("short_primary", "positive")
    return dict(after_short_s=full, scheduled_instead_s=full - skipped)


def price(publication, field, donors):
    plan = publication["plan"]
    change = plan["change"]
    if (plan["case"] != field["case"] or plan["original_native_sha256"] != field["native_sha256"]
            or not change["same_signed_clocks"]):
        raise ValueError("Joint solve and paired field clock have different inputs")
    inserted, replaced = change["inserted"], change["replaced"]
    ledger = change["edits"]
    if (len({r["observation_id"] for r in ledger}) != len(ledger) or len(ledger) != inserted + replaced
            or sum(r["edit"] == "inserted" and r["original"] is None and r["installed"] is not None
                   for r in ledger) != inserted
            or sum(r["edit"] == "replaced" and r["original"] is not None and r["installed"] is not None
                   for r in ledger) != replaced):
        raise ValueError("Expected disjoint edits to short lanes with genuinely positive full outputs")
    lanes = sum(v["opportunities"] for k, v in change["coverage"].items() if k.endswith("/short"))
    if field["modes"]["short_primary"]["lanes"] != lanes:
        raise ValueError("Opportunity counts differ between the field and saved runs")
    installed, candidate = field["paid_installed_s"], field["paid_candidate_s"]
    deficit = candidate - installed / 2
    original_native_s = sum(v["elapsed_ns"] for v in field["modes"].values()) / 1e9
    outside_s = candidate - original_native_s
    if not 0. <= outside_s < candidate:
        raise ValueError("Native callback scope cannot exceed the field wall clock")
    modeled = {case: additional_work(inserted, replaced, times) for case, times in donors.items()}
    return dict(case=field["case"], short_lanes=lanes, inserted=inserted, replaced=replaced,
                measured_installed_s=installed, measured_candidate_s=candidate, half_installed_s=installed / 2,
                measured_s_over_half=deficit, donors=modeled,
                measured_outside_native_s=outside_s, available_for_all_native_s=installed / 2 - outside_s,
                other_saving_if_only_retries_cost_time_s=[
                    max(0., outside_s + fn(t["after_short_s"] for t in modeled.values()) - installed / 2)
                    for fn in (min, max)],
                additional_reduction_needed_s={
                    mode: [deficit + fn(t[mode] for t in modeled.values()) for fn in (min, max)]
                    for mode in ("after_short_s", "scheduled_instead_s")})


def main():
    field = read("first30-empty-call-roof")
    cases = {c["case"]: c for c in field["cases"]}
    records = []
    for name in ("ds30-0049-joint-recovery", "ds30-0086-joint-recovery"):
        publication = read(name)
        records.append(price(publication, cases[publication["plan"]["case"]], field["late_pilot_donor_clocks"]))
    print(json.dumps(dict(inputs=PINS, records=records), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
