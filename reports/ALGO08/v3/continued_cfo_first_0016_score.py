"""Check signed native prefix fidelity and the actual versus full held evidence."""

from collections import Counter
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from continued_cfo_first_0016 import ORDER, SOURCE, WINDOWS, read, write
from empty_bootstrap import bind_native, checked
from held_cycle_refined import CFO


CONTINUED = Path("/dev/shm/leo-v3-continued-refine-results-03")
REFINED = Path("/dev/shm/leo-v3-raw-cfo-0016-result03/candidate")
FULL = {
    "named": (SOURCE/"stock", "4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"),
    "original": (SOURCE/"candidate", "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "refined": (REFINED, "6329ba6eb4893ae12a05259fef9ce14ff8678a320a133ff1dc5ee839527af2ea"),
    "continued": (CONTINUED/"selective", "92680ec88b287a6f69f0fea5ebd0120d854b0e5e09076903f28c49926765a927"),
}
PRICE = "25c515e90936e4e03fe858dd0070356bafb3fea84ef492d9bcc8bc629f13b232"
REFINED_RECEIPT = "059b428e1b2fb38ff2bd098c4a647712b8813455597a64330a4bcfc739def4d5"
ROUNDOFF = {CFO: 1e-6, "fractional_exact_score": 1e-10, "fractional_control_score": 1e-10, "fractional_margin": 1e-10}


def probes(packet):
    return packet["source"]["probes"]


def key(row):
    return row["visit_index"], row["receiver_id"]


def metadata(row):
    return dict(row, candidates=[])


def align(live, full):
    expected = [row for row in probes(full) if row["visit_index"] < WINDOWS]
    exclusions = [x for x in full["provenance"]["excluded_windows"] if x["visit"] < WINDOWS]
    identity = ("radio_id", "stream_generation", "sample_rate_hz", "rf_mapping_authorities")
    if (live["clock_anchor"] != full["clock_anchor"] or live["delivery_clocks"] != full["delivery_clocks"][:WINDOWS]
            or live["provenance"]["excluded_windows"] != exclusions
            or any(live["source"].get(k) != full["source"].get(k) for k in identity[:-1])
            or live["provenance"][identity[-1]] != full["provenance"][identity[-1]]
            or [metadata(row) for row in probes(live)] != [metadata(row) for row in expected]):
        raise ValueError("Original issued clock, counter, RF or signed opportunity order changed")
    return expected


def audit_rows(actual, expected):
    counts, maximum = Counter(), dict.fromkeys(ROUNDOFF, 0.0)
    changes = []
    for a, b in zip(actual, expected, strict=True):
        if metadata(a) != metadata(b):
            raise ValueError("Signed visit/counter/RF mismatch")
        left, right = a["candidates"], b["candidates"]
        counts.update(rows=1, exact=int(left == right), active_a=len(left), active_b=len(right))
        reasons = set()
        if len(left) != len(right):
            reasons.add("support")
        else:
            for x, y in zip(left, right, strict=True):
                if {k:v for k,v in x.items() if k not in ROUNDOFF} != {k:v for k,v in y.items() if k not in ROUNDOFF}:
                    reasons.add("nonroundoff")
                for field, tolerance in ROUNDOFF.items():
                    delta = abs(x[field]-y[field])
                    maximum[field] = max(maximum[field], delta)
                    if delta > tolerance:
                        reasons.add(field)
        if reasons:
            changes.append(dict(lane=key(a), fields=sorted(reasons)))
    return dict(counts=counts, max_abs_delta=maximum, material=changes)


def detector_overlap(named, optimized):
    counts = Counter()
    for a, b in zip(named, optimized, strict=True):
        if metadata(a) != metadata(b):
            raise ValueError("The two receivers visited different RF lanes")
        left, right = a["candidates"], b["candidates"]
        counts.update(named_lanes=bool(left), guarded_lanes=bool(right), shared_lanes=bool(left and right),
                      named_only=bool(left and not right), guarded_only=bool(right and not left))
        if left and right:
            x, y = left[0], right[0]
            def epoch(row):
                return row["integer_epoch_sample"]+row["fractional_epoch_offset_samples"]
            counts["matched_signed_primary"] += (x["candidate_rank"] == y["candidate_rank"] == 0
                and abs(x[CFO]-y[CFO]) <= 250 and abs(remainder(epoch(x)-epoch(y), 13_333)) <= 2)
    return dict(counts)


def held_audit(packet):
    from anchor_cycle_route import select_route

    audit = select_route(packet, audit=True)
    return json.loads(json.dumps({k:v for k,v in audit.items() if k != "cycles"}))


def score(root, output):
    from anchor_exposure import bind, enroll
    from continued_cfo import ContinuedChanges
    from leo.contracts.digests import canonical_digest

    run_binding = read(root/"binding.json")
    for name, pin in run_binding["sources"].items():
        checked(HERE/name, pin)
    runs = {}
    for i, modes in enumerate(ORDER, 1):
        for mode in modes:
            tag = f"{i}-{mode}"
            scope, clock = read(root/tag/"scope-receipt.json"), read(root/(tag+"-clock.json"))
            native = json.loads(checked(root/tag/"detections.json", scope["native_sha256"][7:]))
            if scope["position_runs"] or any(clock["clock"][k] for k in ("exit_code", "major_faults", "input_blocks")):
                raise ValueError("The named and guarded receiver clocks must each be resident through exit")
            runs[tag] = dict(scope=scope, clock=clock, native=native)
    named, guarded = (runs[f"1-{mode}"] for mode in ORDER[0])
    same_run = ("prefix_inventory", "native_sha256", "iq", "opened", "recipe", "held_choice", "paid")
    if (any(runs[f"1-{mode}"]["scope"][field] != runs[f"2-{mode}"]["scope"][field] for mode in ORDER[0] for field in same_run)
            or any(named["scope"][key] != guarded["scope"][key] for key in ("prefix_inventory", "iq", "opened"))
            or named["native"]["source"]["raw_recording_authority_digest"] != guarded["native"]["source"]["raw_recording_authority_digest"]):
        raise ValueError("Clock order or receiver changed the received signed input or selected result")
    if named["native"]["provenance"]["detector_sha256"] == guarded["native"]["provenance"]["detector_sha256"]:
        raise ValueError("The distinct receivers must retain distinct analysis identities")
    documents = {}
    for name, (folder, expected) in FULL.items():
        candidate, = folder.glob("fast-scan-automatic-work/*/detections.json")
        data = json.loads(checked(candidate, expected))
        bind_native(data, data["source"]["session_id"], data["source"]["input_manifest_sha256"],
                    data["provenance"]["detector_sha256"][7:], expected="sha256:"+expected)
        documents[name] = data
    for name in ("refined", "continued"):
        bind(documents["original"], documents[name])
    refined_receipt = json.loads(checked(REFINED/"unified-short-bootstrap.json", REFINED_RECEIPT))
    full_continued = json.loads(checked(CONTINUED/"price-seal.json", PRICE))["weak"]
    if (refined_receipt["native_sha256"] != "sha256:"+FULL["refined"][1]
            or full_continued["native_sha256"] != "sha256:"+FULL["continued"][1]
            or canonical_digest(probes(documents["continued"])) != full_continued["selected_probes_sha256"]):
        raise ValueError("The comparison detached a complete archived receiver from its acquisition receipt")

    fresh, scope = guarded["native"], guarded["scope"]
    expected = {name: align(named["native"] if name == "named" else fresh, data) for name, data in documents.items()}
    if probes(named["native"]) != expected["named"]:
        raise ValueError("The freshly staged named prefix differs from its authentic original release")
    original = dict(fresh, source=dict(fresh["source"], probes=scope["original_probes"]))
    existing = dict(original, source=dict(original["source"], probes=expected["original"]))
    gate = ContinuedChanges()
    paid_reference = [list(key(row)) for row, event in zip(probes(existing), enroll(existing), strict=True)
                      if gate.consider(row, event[4] == "short")]
    if paid_reference != scope["paid"]:
        raise ValueError("The live original continuation and archived prefix paid different physical lanes")
    prefix, full = held_audit(original), held_audit(documents["original"])
    for archive, choice in ((prefix, scope["held_choice"]["choice"]), (full, full_continued["choice"])):
        if any(archive[k] != value for k, value in choice.items()):
            raise ValueError("Held decisions differ from separately rebuilt original-input cycles")
    paid = {tuple(k) for k in paid_reference}
    selected_expected = [b if key(a) in paid else a for a,b in zip(expected["original"], expected["refined"], strict=True)]
    checks = dict(original_vs_archived=audit_rows(probes(original), expected["original"]),
                  acquired_vs_archived_exact_paid_mask=audit_rows(scope["acquired_probes"], selected_expected),
                  acquired_vs_archived_all_paid=audit_rows(scope["acquired_probes"], expected["refined"]),
                  final_vs_complete_continued_prefix=audit_rows(probes(fresh), expected["continued"]))
    if scope["held_choice"]["pre_refinement_probes_sha256"] != canonical_digest(probes(original)):
        raise ValueError("The live held proof was scored over different original measurements")
    write(output, dict(binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest(), runs=runs, checks=checks,
          archived={label: pin for label, (_, pin) in FULL.items()}, full_selector=full, prefix_selector=prefix,
          full_route_receipt=full_continued["choice"], named_matches_its_complete_prefix=True,
          released_vs_selective=detector_overlap(probes(named["native"]), probes(fresh)),
          hybrid_warranted=bool(checks["final_vs_complete_continued_prefix"]["material"])))


if __name__ == "__main__":
    score(Path(sys.argv[1]), Path(sys.argv[2]))
