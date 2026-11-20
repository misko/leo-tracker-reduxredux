"""Compare causal retry intervals with count-matched schedules on authentic peer measurements."""

import argparse
from collections import defaultdict
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.negative_rescue import positive
from ..variants.retry_cadence import RetryCadence
from ..variants.selective_capture import visit_pairs
from . import adaptive_arrival_position as position
from . import arrival_queue, parallel_position
from .complete_detector_roster import BINDINGS, SCREEN
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .recording_to_v5 import digest
from .whole_pressure_trial import rows_from

REPORT = SCREEN / "retry-and-transfer/retry-cadence"
LOWER = "DS26-0237"
UPPER = "DS29-0082"
PARENTS = {
    LOWER: (
        "receiver-deadline/selector-waveform",
        "ef587578d8706b6b35bf2a80bf12e53e1da3fa878860b9ccf7e8b814069a2e01",
        "pilot-search-and-region/single-pass/position",
        "f167d48dec3f47be1b301c8829c4734eb639f868d92f873f2db2c8f1a27e0450",
    ),
    UPPER: (
        "pilot-search-and-region/field-exact-waveform",
        "1120835b1f43533690fb99c69ac5da4c576c0d06c20121b16335fc0fcc867a25",
        "retry-and-transfer/upper-primary",
        "2b72ca663a7061d141f8bfee9e58bea65d82b11865b083192aee73c95ef85c31",
    ),
}


def sources(ident):
    full_dir, full_sha, primary_dir, primary_sha = PARENTS[ident]
    full, primary = SCREEN / full_dir, SCREEN / primary_dir
    parent = sealed(full, "prediction-lock.json", full_sha)
    full_doc = arrival_queue.readgz(full / "native.json.gz")
    if ident == UPPER:
        early = whole_iq.read(whole_iq.checked(primary / "primary-lock.json", primary_sha))
        primary_path = whole_iq.checked(primary / "native.json.gz", early["primary_gzip_sha256"])
    else:
        selected = sealed(primary, "prediction-lock.json", primary_sha)
        primary_path = whole_iq.checked(
            primary / "native.json.gz", selected["files"]["native.json.gz"]
        )
    doc = arrival_queue.readgz(primary_path)
    parallel_position.physical_match(full_doc, doc)
    release = whole_iq.read(
        whole_iq.checked(full / "source-lock.json", parent["files"]["source-lock.json"])
    )
    if whole_iq.receiver_identity(Path(release["receiver"])) != release["receiver_files"]:
        raise ValueError("capture and position worker refer to different receiver versions")
    rows = rows_from(full / "positions.jsonl.gz")
    (reference,) = [r for r in rows if r["method"] == "capture_archived_factors_compact"]
    return full_doc, doc, release, reference


def opportunities(full, primary, clocks):
    if full.keys() != primary.keys():
        raise ValueError("physical visit coverage differs")
    choices = []
    for visit, pair in sorted(primary.items()):
        other = full[visit]
        for a, b in zip(pair, other, strict=True):
            if {k: v for k, v in a.items() if k != "candidates"} != {
                k: v for k, v in b.items() if k != "candidates"
            }:
                raise ValueError("primary and conditional inputs disagree on physical antenna")
        flags = tuple(map(positive, pair))
        if flags[0] == flags[1]:
            if pair != other:
                raise ValueError("a visit without a retry changed its measurements")
            continue
        lane = flags.index(False)
        if other[1 - lane] != pair[1 - lane]:
            raise ValueError("the initially successful antenna changed on retry")
        probe = pair[lane]
        key = (probe["receiver_id"], probe["actual_rf_hz"])
        choices.append((visit, key, clocks[visit]["monotonic_ns"], positive(other[lane])))
    return choices


def schedules(events, seed):
    by_key = defaultdict(list)
    for visit, key, _, _ in events:
        by_key[key].append(visit)
    for after in ("miss", "hit"):
        timer, selected = RetryCadence(after), set()
        for visit, key, now, hit in events:
            if timer.allows(key, now):
                selected.add(visit)
                timer.observed(key, now, hit)
        yield after, selected
        matched = set()
        for key, visits in by_key.items():
            count = len(selected.intersection(visits))
            ranked = sorted(visits, key=lambda v: (digest(["retry-cadence-v1", seed, key, v]), v))
            matched.update(ranked[:count])
        yield after + "_control", matched
    yield "oracle", {visit for visit, _, _, hit in events if hit}


def run(work, out, cpus):
    if work.exists() or (out / "schedule-lock.json").exists():
        raise FileExistsError("choose a new replay directory")
    work.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    jobs, references, support, files = [], [], [], []
    for i, ident in enumerate(PARENTS):
        original, prior, release, ref = sources(ident)
        binding, req = whole_iq.binding(ident)
        keys = dict(
            paired_capture_sha256=binding["native"]["sha256"],
            original_request_sha256=binding["request"]["sha256"],
            catalog_sha256=binding["catalog"]["sha256"],
            tile=binding["regions"][0],
        )
        if (
            any(ref[k] != keys[k] for k in BINDINGS)
            or prior["source"]["session_id"] != binding["session_id"]
        ):
            raise ValueError("original reference belongs to another request")
        references.append(
            dict(ref, policy="full", method="cadence_full", cohort="full conditional")
        )
        full = dict(visit_pairs(original["source"]["probes"]))
        primary = dict(visit_pairs(prior["source"]["probes"]))
        events = opportunities(full, primary, original["delivery_clocks"])
        seed = prior["source"]["input_manifest_sha256"]
        hits = {v for v, _, _, passed in events if passed}
        for n, (policy, selected) in enumerate(schedules(events, seed)):
            probes = [
                p
                for v, pair in sorted(primary.items())
                for p in (full[v] if v in selected else pair)
            ]
            observed = sum(map(positive, probes))
            if observed != sum(positive(p) for pair in primary.values() for p in pair) + len(
                selected & hits
            ):
                raise ValueError("positive probe count does not match physical retry decisions")
            decisions = [(v, key, t, v in selected, h) for v, key, t, h in events]
            witness = f"schedules/{ident}-{policy}.json.gz"
            arrival_queue.writegz(out / witness, decisions)
            files.append(witness)
            fingerprint = digest(probes)
            lineage = digest([ident, policy, fingerprint, _sha(out / witness)])
            provenance = dict(prior["provenance"], run_id="retry-" + lineage[7:39])
            provenance.pop("detector_sha256", None)
            doc = dict(
                prior,
                provenance=provenance,
                source=dict(prior["source"], probes=probes, analysis_manifest_sha256=lineage),
            )
            folder = work / ident / policy
            folder.mkdir(parents=True)
            cpu = cpus[(i + n) % len(cpus)]
            native, request = position.position_input(folder, binding, req, release, doc, cpu)
            counts = dict(
                opportunities=len(events),
                executed=len(selected),
                original_rescues=len(hits),
                retained_rescues=len(hits & selected),
                positive_probes=observed,
                valid_visits=len(primary),
            )
            support.append(dict(id=ident, policy=policy, **counts, probe_sha256=fingerprint))
            jobs.append(
                dict(
                    id=ident,
                    mode="matched-tile",
                    cohort="selected peer retry",
                    policy=policy,
                    method="cadence_" + policy,
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
        out / "schedule-lock.json",
        dict(
            cases=list(PARENTS),
            jobs=jobs,
            parents=PARENTS,
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            selector_sha256=_sha(Path(RetryCadence.observed.__code__.co_filename)),
            program_sha256=_sha(Path(__file__)),
            files={k: _sha(out / k) for k in files},
        ),
    )
    results = parallel_position.fit_jobs(work, out, jobs, cpus)
    files.extend(r["service_log"] for r in results if r["service_log"])
    pack(
        out / "positions.jsonl.gz",
        sorted(results + references, key=lambda r: (r["id"], r["policy"])),
    )
    files.extend(("schedule-lock.json", "positions.jsonl.gz"))
    save_json(
        out / "prediction-lock.json",
        dict(cases=list(PARENTS), files={k: _sha(out / k) for k in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs="+", default=[22, 23])
    args = parser.parse_args()
    if not args.cpus or len(set(args.cpus)) != len(args.cpus):
        parser.error("the worker list must be nonempty and contain distinct CPU IDs")
    run(args.work, args.out, tuple(args.cpus))
