"""Verify sparse 8 ms typed measurements and native-cost transfer on detached visits."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from attested_visit_detector import CASES, CURRENT, duration, pin, pinned, replay


HERE = Path(__file__).resolve().parent
ARCHIVED = Path("/tmp/leo-ds30-partial-window-detector01")
SPARSE = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/use.so")
DONORS = HERE / "measurements/receiver-mix-budget.json"
DONORS_SHA = "856694a1b8a26f74f172b58a9e3e5b1f1e1c5c1e10a8bc5b185c84456f1c2ffd"
MODELS = ("DS30-0016/positive_first", "DS30-0016/withholding_first", "South/containing", "South/near-omitted")
SLOTS = ("full", "short_primary")
ORDER = {
    "DS30-0163": ("generic", "sparse"),
    "DS30-0419": ("sparse", "generic"),
}
CONTROLS = {
    "DS30-0163": (29, "266a6df0b7cc36a324fd7cf0fa325f3c9059d5ca0faf4811d8dde031238f6b88"),
    "DS30-0419": (15, "c1ee85e09d71cb5e42a0508e90eaf06c43e9ba3f99c0097369e5ef30b5b2e8a7"),
}


def read_donors(path):
    body = path.read_bytes()
    if sha256(body).hexdigest() != DONORS_SHA:
        raise ValueError("Measured native donor receipt differs from the declared model")
    models = {row["name"]: row["cpu_s_per_call"] for row in json.loads(body)["measured"]}
    if set(models) != set(MODELS):
        raise ValueError("Expected all four frozen measured donor scenarios")
    return models


def factors_only(visit):
    """Retain literal science, omitting only per-callback/native durations."""
    same = {key: value for key, value in visit.items() if key not in {"callback_timing", "lanes"}}
    lanes = []
    for lane in visit["lanes"]:
        copy = dict(lane)
        for mode in ("named", "mixed"):
            key = f"{mode}_native"
            copy[key] = {k: v for k, v in lane[key].items() if k not in {"cpu_ns", "elapsed_ns"}}
        lanes.append(copy)
    return same | {"lanes": lanes}


def verify_science(rows, detector, reference):
    from leo.contracts.digests import canonical_json_bytes

    exact = canonical_json_bytes([factors_only(row) for row in rows])
    expected = canonical_json_bytes([factors_only(row) for row in reference["visits"]])
    if exact != expected or not detector["named_archive_exact"]:
        raise ValueError("Typed factors, empties or original visit identity differ from the signed ledger")
    old, new = reference["detector"]["mixed"]["native"], detector["mixed"]["native"]
    for key in ("rule", "installed_sha256", "visits", "native_calls", "factors", "streams"):
        if old[key] != new[key]:
            raise ValueError(f"The actual original stream/schedule differs in {key}")
    return pin(exact)


def exclusive(rows, detector):
    result = {}
    for mode in ("named", "mixed"):
        field = f"{mode}_native"
        calls = Counter()
        totals = {"full": Counter(), "short_primary": Counter()}
        callback = Counter()
        for row in rows:
            if row["admitted"]:
                callback.update(row["callback_timing"][mode])
            for lane in row["lanes"]:
                call = lane[field]
                role = call["aperture"]
                calls[role] += 1
                totals[role].update({key: call[key] for key in ("cpu_ns", "elapsed_ns")})
        if set(calls) != ({"full"} if mode == "named" else set(SLOTS)):
            raise ValueError("Expected the actual native full and short paths")
        if mode == "mixed":
            mixer = detector["mixed"]["native"]
            clocks = (("native_cpu_ns", "cpu_ns"), ("native_wall_ns", "elapsed_ns"))
            if calls != mixer["native_calls"] or any(mixer[stamp] != {r: totals[r][key] for r in SLOTS}
                                                    for stamp, key in clocks):
                raise ValueError("The per-lane native clocks differ from the live receiver accounting")
        remainder = {key: elapsed - sum(clock[key] for clock in totals.values()) for key, elapsed in callback.items()}
        if not remainder or min(remainder.values()) < 0:
            raise ValueError("Component native time exceeds the full instrumented callback")
        result[mode] = dict(callback_total_ns=dict(callback), callback_outside_native_ns=remainder,
                            native={role: dict(**totals[role], calls=n, cpu_ms_per_call=totals[role]["cpu_ns"] / n / 1e6)
                                    for role, n in calls.items()})
    return result


def predicted_slices(models, mixed):
    timings = mixed["native"]
    observed = {slot: timings[slot]["cpu_ns"] / 1e9 for slot in SLOTS}
    estimates = {}
    for name, source in models.items():
        if set(source) != set(SLOTS) or any(not isfinite(rate) or rate <= 0 for rate in source.values()):
            raise ValueError("Donor must expose the measured native rates for both roles")
        predicted = {role: source[role] * timings[role]["calls"] for role in SLOTS}
        predicted["native_sum"] = sum(predicted.values())
        actual = observed | {"native_sum": sum(observed.values())}
        estimates[name] = dict(predicted_cpu_s=predicted, actual_cpu_s=actual,
                               relative_error={role: predicted[role] / actual[role] - 1 for role in actual})
    return estimates


def run(output):
    from empty_bootstrap import load_runtime

    (_, spec, installed_sources, _, _), runtime = duration(load_runtime)

    from dense_geographic_trial import host
    from full_short_run import EIGHT_MS_RECIPES, EIGHT_MS_SHA, SPARSE_EIGHT_MS_SHA
    from attested_visit_detector import admit
    from leo.contracts.digests import canonical_digest, canonical_json_bytes

    machine = host()
    # Runtime setup is paid once even though each scoped receiver context
    # is freshly constructed. Do not charge it once per measured callback.
    sources = {name: pin(body) for name, body in installed_sources.items()}
    models = read_donors(DONORS)
    binaries = {"generic": (CURRENT, EIGHT_MS_SHA), "sparse": (SPARSE, SPARSE_EIGHT_MS_SHA)}
    bundles = {}
    for case, order in ORDER.items():
        count, old_pin = CONTROLS[case]
        reference = json.loads(pinned(ARCHIVED / f"{case}.json", old_pin, Path("/tmp")))
        attestation = CASES[case]["attestation"]
        (document, packet, entry, member, visits, _), admission = duration(admit, case, attestation, spec["detector_sha256"])
        if (len(visits) != count or len(reference["visits"]) != count
                or reference["original"]["first_segment"] != entry
                or reference["original"]["first_member"] != member.model_dump(mode="json")
                or reference["scope"]["verified_file"] != document["verified_file"]
                or reference["scope"]["attestation_sha256"] != "sha256:" + attestation):
            raise ValueError("Previously qualified real detached-prefix evidence changed")
        runs = {}
        for mode in order:
            binary, binary_pin = binaries[mode]
            setup = {}

            def pair():
                return replay(visits, packet, spec, sources, short_binary=binary, short_pin=binary_pin, setup_timing=setup)

            (rows, detectors), scope = duration(pair)
            exact = verify_science(rows, detectors, reference)
            recipe = detectors["mixed"]["pre_selector_recipe"]
            if (canonical_digest(recipe) != "sha256:" + EIGHT_MS_RECIPES[binary_pin]
                    or detectors["mixed"]["detector_sha256"] != "sha256:" + binary_pin):
                raise ValueError("Expected the installed full anchor and distinct registered short binary recipe")
            costs = exclusive(rows, detectors)
            runs[mode] = dict(costs=costs, detector=detectors, context_setup_ns=setup,
                              replay_scope_ns=scope, normalized_science_sha256=exact, visits=rows,
                              donor_predictions=predicted_slices(models, costs["mixed"]) if mode == "sparse" else None)
        if (runs["generic"]["normalized_science_sha256"] != runs["sparse"]["normalized_science_sha256"]
                or runs["generic"]["detector"]["mixed"]["pre_selector_recipe_sha256"] ==
                   runs["sparse"]["detector"]["mixed"]["pre_selector_recipe_sha256"]):
            raise ValueError("Need exact parity across separately identified recipes")
        bundles[case] = dict(order=order, attestation_sha256=attestation, original=reference["original"],
                             prior_ledger_sha256=old_pin, prior_costs=exclusive(reference["visits"], reference["detector"]),
                             verified_file=document["verified_file"], detached_admission_ns=admission, runs=runs)
    evidence = dict(schema="leo.research.attested-sparse-native-budget.v1", case_order=list(ORDER),
                    donors_sha256=DONORS_SHA, bundles=bundles, machine=machine, outer_runtime_setup_ns=runtime,
                    driver_and_harness_sha256={p.name: pin(p.read_bytes()) for p in (Path(__file__), HERE / "attested_visit_detector.py")},
                    original_backing_waveform_bytes=0, held_selector_runs=0, position_solver_runs=0)
    with output.open("xb") as stream:
        stream.write(canonical_json_bytes(evidence))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
