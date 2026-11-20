"""Fit the four position inputs obtained from a fixed RF assignment and measured arrivals."""

import argparse
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.negative_rescue import positive
from ..variants.rf_routing import choose_rf
from ..variants.selective_capture import visit_pairs
from . import adaptive_arrival_position as position
from . import arrival_queue, one_lane_roster, parallel_position, recording_to_v5, two_rate_holdout
from . import parallel_acquisition_source as staging
from .complete_detector_roster import BINDINGS, SCREEN
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = SCREEN / "pilot-search-and-region/rf-lane-position"
JOINT = REPORT.parent / "rf-lane-waveform"
CASES = ("DS26-0237", "DS29-0082")
POLICIES = ("complete", "recorded", "timely", "other_lanes")
PARENT = "360af28d5e65513fa6d8cd01efc794a85968a73d286fa6179bd635eec81c8f15"


def complete_assignment(wide, original, seed):
    """Build the complete exclusive assignment; a valid physical visit occurs exactly once."""
    centers = [pair[0]["actual_rf_hz"] for pair in wide.values()]
    donor = choose_rf(seed, centers)
    choices = {}
    if wide.keys() != original.keys():
        raise ValueError("complete detector controls have different valid visit sets")
    for visit, pair in wide.items():
        other = original[visit]
        rf = pair[0]["actual_rf_hz"]
        if any(p["actual_rf_hz"] != rf or p["visit_index"] != visit for p in (*pair, *other)):
            raise ValueError("complete controls disagree on the physical visit or RF")
        role = "original" if rf == donor else "wide"
        choices[visit] = (role, other if role == "original" else pair)
    return donor, choices


def verify_emissions(rows, events, choices, role, cutoff):
    for row, (arrival, finish, pair) in zip(rows, events, strict=True):
        choice = choices.get(row["visit"])
        if choice and ((row["admission"] in ("queued", "dropped_busy")) != (choice[0] == role)):
            raise ValueError("valid visit was offered to the wrong detector")
        if pair is not None and (not choice or role != choice[0] or pair != choice[1]):
            raise ValueError("measured packet differs from its assigned full waveform")
        if row["observed_by_cutoff"] != (pair is not None and arrival <= finish <= cutoff):
            raise ValueError("packet availability disagrees with the measured clock")


def load_case(ident, manifest, archive):
    wide = one_lane_roster.stock_document(archive)
    original, release = staging.original_reference(ident)
    parallel_position.physical_match(wide, original)
    seed = wide["source"]["input_manifest_sha256"]
    donor, choices = complete_assignment(
        dict(visit_pairs(wide["source"]["probes"])),
        dict(visit_pairs(original["source"]["probes"])),
        seed,
    )
    case = manifest["cases"][ident]
    cutoff = case["last_arrival_ns"]
    if (
        cutoff
        != wide["delivery_clocks"][-1]["monotonic_ns"] - wide["delivery_clocks"][0]["monotonic_ns"]
    ):
        raise ValueError("raw run closed at a different recorded arrival")

    def member(name):
        path = (JOINT / name).resolve()
        if not path.is_relative_to(JOINT.resolve()):
            raise ValueError("raw artifact escapes its measurement folder")
        return arrival_queue.readgz(whole_iq.checked(path, manifest["files"][name]))

    events = {}
    for role, entry in case["branches"].items():
        doc, rows = member(entry["native"]), member(entry["trace"])
        parallel_position.physical_match(wide, doc)
        events[role] = parallel_position.branch_events(doc, rows, False)
        verify_emissions(rows, events[role], choices, role, cutoff)
    if set(events) != {"wide", "original"}:
        raise ValueError("the physical replay requires both assigned workers")
    return wide, release, donor, choices, events, cutoff


def inputs(choices, events, cutoff):
    selected = [(v, role, role) for v, (role, _) in sorted(choices.items())]
    full = [p for v, _, _ in selected for p in choices[v][1]]
    yield "complete", full, selected
    for policy, rule in (("recorded", "replace"), ("timely", "timely"), ("other_lanes", "wide")):
        probes, rows, _ = parallel_position.compose(
            events["wide"], events["original"], rule, cutoff
        )
        yield policy, probes, rows


def run(work, out, cpus):
    if work.exists() or (out / "position-input-lock.json").exists():
        raise FileExistsError("use fresh scratch and output directories for numerical replay")
    work.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    manifest = sealed(JOINT, "manifest.json")
    archive = two_rate_holdout.REPORT
    baseline = sealed(archive, "prediction-lock.json", PARENT)
    controls = rows_from(
        whole_iq.checked(archive / "positions.jsonl.gz", baseline["files"]["positions.jsonl.gz"])
    )
    inventory = whole_iq.read(
        whole_iq.checked(
            archive / "membership-lock.json", baseline["files"]["membership-lock.json"]
        )
    )
    jobs, references, support = [], [], []
    files = []
    raw_sha = _sha(JOINT / "manifest.json")
    for n, ident in enumerate(CASES):
        binding, req = whole_iq.binding(ident)
        base, release, donor, choices, events, cutoff = load_case(
            ident, manifest, inventory["stock_archives"][ident]
        )
        keys = dict(
            paired_capture_sha256=binding["native"]["sha256"],
            original_request_sha256=binding["request"]["sha256"],
            catalog_sha256=binding["catalog"]["sha256"],
            tile=binding["regions"][0],
        )
        if base["source"]["session_id"] != binding["session_id"] or (
            whole_iq.receiver_identity(Path(release["receiver"])) != release["receiver_files"]
        ):
            raise ValueError(
                "factor stream or compact receiver does not match its original request"
            )
        for mode in ("wide", "original"):
            (row,) = [r for r in controls if r["condition"] == mode and r["id"] == ident]
            if any(row[k] != keys[k] for k in BINDINGS):
                raise ValueError("complete compact reference belongs to a different request")
            references.append(
                dict(
                    row,
                    mode="matched-tile",
                    cohort="complete reference",
                    policy=mode,
                    method="rf_lane_reference_" + mode,
                )
            )
        for k, (policy, probes, selected) in enumerate(inputs(choices, events, cutoff)):
            count = Counter(role for _, role, _ in selected)
            filename = f"selected/{ident}-{policy}.json.gz"
            arrival_queue.writegz(out / filename, selected)
            files.append(filename)
            fingerprint = recording_to_v5.digest(probes)
            lineage = recording_to_v5.digest([ident, policy, raw_sha, fingerprint])
            provenance = dict(
                base["provenance"],
                processed_windows=len(selected),
                run_id="replay-" + lineage[7:39],
                scope="Fixed frequency assignment on independently verified recording packets",
            )
            provenance.pop("detector_sha256", None)
            doc = dict(
                base,
                provenance=provenance,
                source=dict(base["source"], probes=probes, analysis_manifest_sha256=lineage),
            )
            folder = work / ident / policy
            folder.mkdir(parents=True)
            cpu = cpus[(n + k) % len(cpus)]
            native, request = position.position_input(folder, binding, req, release, doc, cpu)
            counts = dict(
                valid_visits=len(choices),
                selected_visits=len(selected),
                configured_rf_hz=donor,
                original_visits=count["original"],
                wide_visits=count["wide"],
                positive_probes=sum(map(positive, probes)),
                probe_sha256=fingerprint,
            )
            support.append(dict(id=ident, policy=policy, **counts))
            jobs.append(
                dict(
                    id=ident,
                    mode="matched-tile",
                    method="rf_lane_" + policy,
                    policy=policy,
                    cohort="recorded RF assignment",
                    cpu=cpu,
                    native_sha256=native,
                    position_request_sha256=request,
                    **counts,
                    **keys,
                )
            )
    csv_file(out / "support.csv", support)
    files.append("support.csv")
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=CASES,
            jobs=jobs,
            cpus=cpus,
            raw_manifest_sha256=raw_sha,
            controls_sha256=PARENT,
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            program_sha256=_sha(Path(__file__)),
            dispatch_sha256=_sha(Path(choose_rf.__code__.co_filename)),
            fitter_sha256=_sha(Path(parallel_position.__file__)),
            files={n: _sha(out / n) for n in files},
        ),
    )
    results = parallel_position.fit_jobs(work, out, jobs, cpus)
    files.extend(r["service_log"] for r in results if r["service_log"])
    pack(
        out / "positions.jsonl.gz",
        sorted(results + references, key=lambda r: (r["id"], r["method"])),
    )
    files.extend(("position-input-lock.json", "positions.jsonl.gz"))
    save_json(
        out / "prediction-lock.json", dict(cases=CASES, files={n: _sha(out / n) for n in files})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs="+", default=[22, 23])
    args = parser.parse_args()
    if not args.cpus or len(set(args.cpus)) != len(args.cpus):
        parser.error("choose distinct available worker CPUs")
    run(args.work, args.out, tuple(args.cpus))
