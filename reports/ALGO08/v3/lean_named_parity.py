"""Join the sealed lean and exact named evidence on five same-packet cases."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path


TMPFS = Path("/dev/shm").resolve()
ARMS = ("c0", "fitted_c")
CASES = {
    "North": (
        ("leo-v3-exact-named-raw-north03/candidate/exact-named-raw-witness.json", "04e965422cb13f12ee69ad7311c2524e06c94d8695a8562aebf29af2197eca22"),
        ("leo-v3-eight-ms-native-north02/containing/joint-research-receipt.json", "f0990c1e5a60bc2f6fb05973529e4aeb6bc570a673186a52235aebb66f37e909"),
    ),
    "DS30-0016": (
        ("leo-v3-named-weak-all8-result01/exact/named-saved-witness.json", "347460edcfaba075a07984921328c6210ce8b9f79503def02df2c7665a7c9c28"),
        ("leo-v3-weak-all8-combined-result02/candidate/joint-research-receipt.json", "eff8970033292d1b635d7d8467cf801f1805d60638c97868ed1131d13494643b"),
    ),
    "DS30-0160": (
        ("leo-v3-exact-named-0160-result01/candidate/joint-research-receipt.json", "f8f97702d8d230b3068605f9efd235e4fbd7e8dae0f1fa8ceddc6e1ac2c29c1e"),
        ("leo-held-adaptive-0160-result01/candidate/joint-research-receipt.json", "d1553f95edeeab86a9b1e127fb4e91449c776f3a7772e8f9bb2f4e6fa049aef7"),
    ),
    "DS30-0316": (
        ("leo-v3-exact-named-0316-result02/candidate/joint-research-receipt.json", "75445d0649e18a6343394f5871115643bf7a3769ab9b7b554a540cd96d765558"),
        ("leo-v3-final-0316-transfer-result02/candidate/joint-research-receipt.json", "ebbaed6c90a1d03b229b4199835bcc399984eee2524755b8b2e7d0470c907d1f"),
    ),
    "DS30-0374": (
        ("leo-v3-exact-named-0374-result01/candidate/joint-research-receipt.json", "bf56b382d5ccfa0217bbd2bbd9b27a63cae29a9a1a7e00a72b8779380eb90b84"),
        ("leo-v3-0374-final-fit-result02/combined/joint-research-receipt.json", "46080930eec33cf3586d8dc226c86d56324b734ef18349445b502bd31556d4e9"),
    ),
}
NORTH_EXACT = ("leo-v3-exact-named-raw-north03/verified-result.json", "3713a489669cbb6e185f83b7570714b0e8e6319d5e8ad01c310f06a75479c3cc")
NORTH_LEAN = ("leo-v3-eight-ms-native-north02/science-seal.json", "74f85ba14d14e085ea0832933acd3ad1fed001d6b0d698d2c05b52a39a77a849")
NORTH_REQUEST = ("leo-v3-exact-named-raw-north03/binding.json", "1f3913510a397328f427362bd264481330f94024ee2143d1de0b002a6460b51f")
WEAK_EXACT = ("leo-v3-named-weak-all8-result01/result.json", "f7a55412fe0bf00a105236e636e8b654af7d3f90f166ec9b16bc59104f397ec6")
WEAK_LEAN = ("leo-v3-weak-all8-combined-result02/seal.json", "b29c1e288400792af10176f5936fce7206ba7d5f5c817cf214ce08ad800e7cfc")
MEDIUM_REQUESTS = {
    "DS30-0160": (("leo-v3-saved-0160-pair-01/request.json", "c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e"),),
    "DS30-0316": (
        ("leo-v3-saved-0316-pair-01/request.json", "e1e3d9cd482bc4b8837f782c329702472b60e34eba8616616b5ec20ef759b739"),
        ("leo-v3-final-0316-transfer-result02/request.json", "c9be0ae39a59a69621f9b9a6f4062ea7e33d1ba1de05c394771001f1b26ce4b3"),
    ),
    "DS30-0374": (("leo-v3-0374-final-fit-result02/request.json", "72ced1ad90e5d9b6783efd20d6de6cf19edcb054bf445633d00b2b0f99cc454f"),),
}


def tagged(payload):
    return "sha256:" + sha256(payload).hexdigest()


def canonical(value):
    return tagged(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


def read(path, pin=None):
    path = path.resolve(strict=True)
    if not path.is_relative_to(TMPFS):
        raise ValueError(f"Expected an existing tmpfs artifact: {path}")
    body = path.read_bytes()
    digest = tagged(body)
    if pin and digest != "sha256:"+pin:
        raise ValueError(f"Unexpected source bytes: {path}")
    return json.loads(body), digest


def compare_owners(named, lean):
    def by_id(rows):
        owners = {oid: (norad, role) for oid, norad, role in rows}
        if len(owners) != len(rows):
            raise ValueError("Duplicate selected observation ID")
        return owners

    left, right = by_id(named), by_id(lean)
    shared = left.keys() & right.keys()
    return dict(ordered_equal=named == lean, left=len(left), right=len(right), shared=len(shared),
                lost=len(left)-len(shared), added=len(right)-len(shared),
                changed_norad=sum(left[o][0] != right[o][0] for o in shared),
                changed_role=sum(left[o][1] != right[o][1] for o in shared),
                left_roles=dict(Counter(role for _, role in left.values())),
                right_roles=dict(Counter(role for _, role in right.values())),
                rows_sha256=[canonical(named), canonical(lean)])


def residual_roles(conditional, overall, roles):
    """Recover a raw predictive RMS only for the original two disjoint fit roles."""
    if set(roles) != {"conditional", "predictive"} or min(roles.values()) <= 0:
        raise ValueError("Expected exactly the complete conditional and predictive row census")
    remaining = (sum(roles.values()) * overall**2 - roles["conditional"] * conditional**2) / roles["predictive"]
    if not math.isfinite(remaining) or remaining < 0:
        raise ValueError("Conditional and published residual summaries are inconsistent")
    return math.sqrt(remaining)


def grid_comparison(left, right):
    def key(row):
        return row["east_km"], row["north_km"], tuple(row["latlon"])

    points = [dict((key(row), row) for row in grid["points"]) for grid in (left, right)]
    if any(len(mapping) != len(grid["points"]) for mapping, grid in zip(points, (left, right), strict=True)):
        raise ValueError("Duplicate grid coordinate")
    common = points[0].keys() & points[1].keys()
    result = dict(left=len(points[0]), right=len(points[1]), shared=len(common), same_order=list(points[0]) == list(points[1]))
    result["arms"] = {}
    for arm in ARMS:
        values = [(points[0][p]["scores"].get(arm), points[1][p]["scores"].get(arm)) for p in common]
        differences = [abs(a-b) for a, b in values if a is not None and b is not None]
        result["arms"][arm] = dict(scored_in_both=len(differences), different=sum(d > 0 for d in differences),
                                    unmatched_failures=sum((a is None) != (b is None) for a, b in values),
                                    maximum_absolute_delta=max(differences, default=None))
    return result


def publication(source, pin):
    witness_file = TMPFS/source
    root = witness_file.parent
    witness, witness_digest = read(witness_file, pin)
    ordered = witness["selected_rows"] if "selected_rows" in witness else witness["evidence"]["owner_rows"]
    terminal_file, = root.glob("fast-scan-automatic-work/*/terminal.json")
    terminal, terminal_file_sha256 = read(terminal_file)
    detector, = root.glob("fast-scan-automatic-work/*/detections.json")
    native, _ = read(detector)
    if canonical(native) != terminal["native_sha256"]:
        raise ValueError("Native packet and terminal binding disagree")
    run_id = terminal_file.parent.name
    artifact_root = root/"fast-scan-standard-v2"/run_id/"final-error-v7"
    adaptive = not artifact_root.exists()
    if adaptive:
        artifact_root = root/"research-adaptive-position-v1"/run_id
    names = (("research-manifest.json", "recorded-position-path.json", "adaptive-position-sample.json") if adaptive
             else ("manifest.json", "position-path.json", "position-grid.json"))
    (meta, meta_pin), (path, path_pin), (grid, grid_pin) = (read(artifact_root/name) for name in names)
    detail = meta["publication"] if adaptive else meta
    if adaptive:
        if (meta["publication_sha256"] != canonical(detail) or meta["sidecars_sha256"] !=
                {"path": canonical(path), "sample": canonical(grid)} or
                meta["phase_state_sha256"] != grid["phase_state_sha256"]):
            raise ValueError("Adaptive evidence changed after publication")
    else:
        if any(doc["sha256"] != canonical(doc["document"]) for doc in (path, grid)):
            raise ValueError("Standard evidence changed after publication")
        path, grid = path["document"], grid["document"]
    if (detail["terminal_sha256"] != canonical(terminal) or detail["input_sha256"] != terminal["native_sha256"]
            or detail["raw_authority"] != native["source"]["raw_recording_authority_digest"]):
        raise ValueError("Terminal, region, and scientific detail lack their common input binding")
    for arm in ARMS:
        rows = ordered[arm]
        if (len(rows) != detail["arms"][arm]["associated_points"] or
                canonical({oid: norad for oid, norad, _ in rows}) != detail["arms"][arm]["owner_sha256"]):
            raise ValueError("Saved rows do not represent published ownership")
    artifacts = {row["name"]: row["sha256"] for row in detail["artifacts"]}
    if (len(artifacts) != 8 or any(doc["binding"]["position_png_sha256"] != artifacts["position"]
                                  or doc["binding"]["input_sha256"] != terminal["native_sha256"]
                                  for doc in (path, grid))):
        raise ValueError("The archived scientific sidecars lack their own published position binding")
    return dict(terminal=terminal, detail=detail, artifacts=artifacts, owners=ordered, grid=grid, path=path,
                orbit_recipe=witness.get("solver_recipe"), route=witness.get("route_details"),
                pins=dict(witness=witness_digest, terminal_file=terminal_file_sha256, detail=meta_pin,
                          grid=grid_pin, path=path_pin), archive_phase_digest=meta.get("phase_state_sha256"))


def compare(left, right, decompose):
    a, b = (x["terminal"] for x in (left, right))
    if (any(a[key] != b[key] for key in ("native_sha256", "session_id", "region"))
            or left["detail"]["raw_authority"] != right["detail"]["raw_authority"]):
        raise ValueError("A pair must use identical signed detections and region")
    owner = {arm: compare_owners(left["owners"][arm], right["owners"][arm]) for arm in ARMS}
    metrics = {}
    for arm in ARMS:
        metrics[arm] = [dict(endpoint=x["terminal"]["arms"][arm]["latlon"],
                             conditional_rms_hz=x["terminal"]["arms"][arm]["rf_rms_hz"],
                             owned_rms_hz=x["detail"]["arms"][arm]["residual_rms_hz"],
                             owner_rows=len(x["owners"][arm])) for x in (left, right)]
        if decompose:
            for metric, key in zip(metrics[arm], ("left_roles", "right_roles"), strict=True):
                metric["predictive_rms_hz_from_role_sums"] = residual_roles(
                    metric["conditional_rms_hz"], metric["owned_rms_hz"], owner[arm][key])
    paths = [x["path"]["stages"] for x in (left, right)]
    return dict(native=a["native_sha256"], region=a["region"], same_terminal=a == b, owner=owner, metrics=metrics,
                paths_equal=paths[0] == paths[1], terminal_policies=[a["orbit_policy"], b["orbit_policy"]],
                phase_changes_s=[{arm: [step["phase_change_s"] for stage in outer
                                        for step in stage["arms"][arm]["rounds"]] for arm in ARMS} for outer in paths],
                phase_state_digests=[x["archive_phase_digest"] for x in (left, right)],
                grid=grid_comparison(left["grid"], right["grid"]),
                like_png_digests=sum(digest == right["artifacts"].get(name) for name, digest in left["artifacts"].items()),
                installed_and_lean_pins=[left["pins"], right["pins"]],
                lean_branch={key: right["route"][key] for key in
                             ("pair_passes", "named_survivor_fit", "cold_clocks", "candidate_pre_evidence_clocks",
                              "standard_evidence_clocks", "exterior_clocks") if key in right["route"]})


def comparable_inputs(named, lean, keys):
    identity = {key: named[key] for key in keys}
    if identity != {key: lean[key] for key in keys}:
        raise ValueError("The same packet did not use the same offered input")
    return identity


def timed_positive_cases():
    def source(pin):
        return read(TMPFS/pin[0], pin[1])[0]

    a, b, north_request = map(source, (NORTH_EXACT, NORTH_LEAN, NORTH_REQUEST))
    n = a["runs"]["candidate"]
    north = dict(identity=comparable_inputs(north_request["request"], b["request"], (
        "session", "cutoff_utc_ns", "archive", "authority", "inventory", "inside_offer_sha256")),
        receipt_sha256=[NORTH_EXACT[1], NORTH_LEAN[1]], request_sha256=NORTH_REQUEST[1],
        raw_observation_clocks=[a["clocks"]["candidate"], b["clock"]],
        exact_solve=n["timings"]["solve"][0], lean_solve={k: b["solve"][k] for k in ("cpu_s", "elapsed_s")},
        exact_acquisition=n["raw_stages"]["receiver"], lean_acquisition=b["raw"]["phases"]["authenticated_raw_acquisition"],
        exact_render=n["timings"]["render"][0])
    a, b = map(source, (WEAK_EXACT, WEAK_LEAN))
    weak = dict(identity=comparable_inputs(a["source_bindings"]["request"], b["execution"]["identity"], (
        "session", "cutoff_utc_ns", "archive", "authority", "inventory", "offer_sha256")),
        receipt_sha256=[WEAK_EXACT[1], WEAK_LEAN[1]],
        saved_observation_clocks=[a["clocks"]["exact"], b["clock"]], exact_times=a["evidence"]["exact"]["timing"],
        lean_times=b["disjoint_saved_costs"])
    return {"North": north, "DS30-0016": weak}


def medium_identity(case, native):
    docs = []
    for source, pin in MEDIUM_REQUESTS[case]:
        doc, _ = read(TMPFS/source, pin)
        docs.append(dict(native="sha256:"+doc["native_sha256"], cutoff=doc["causal_cutoff_utc_ns"],
                         archive=(doc.get("original_archive") or doc["local_archive"])["snapshots_sha256"],
                         offer_sha256=doc["offer_sha256"], session=doc["session"], raw_authority=doc["raw_authority"]))
    if docs[0]["native"] != native or any(item != docs[0] for item in docs[1:]):
        raise ValueError("The documented medium packet, causal archive or offer differs")
    return docs[0] | {"request_sources": MEDIUM_REQUESTS[case]}


def audit():
    results = {}
    for case, inputs in CASES.items():
        inputs = [publication(*item) for item in inputs]
        results[case] = compare(*inputs, decompose=case in ("North", "DS30-0016"))
        if case in MEDIUM_REQUESTS:
            results[case]["authenticated_request"] = medium_identity(case, results[case]["native"])
    return dict(cases=results, timing_inputs=timed_positive_cases())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
