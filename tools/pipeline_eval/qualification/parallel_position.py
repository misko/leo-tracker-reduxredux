"""Fit the compact receiver from stereo packets available at the recorded cutoff."""

import argparse
import gzip
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import dual_rate
from ..variants.negative_rescue import positive
from ..variants.selective_capture import visit_pairs
from . import adaptive_arrival_position as position
from . import arrival_queue, bracketed_position, paced_original, recording_to_v5
from .bracketed_position_results import service_result
from .complete_detector_roster import SCREEN
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = SCREEN / "receiver-deadline/parallel-position"
JOINT = REPORT.parent / "parallel-acquisition"
LEGACY = "4f88161ae1e825f5bf84a31050765282dd03b281c4e043d96a19a24395e2a91b"
CASES = ("DS26-0237", "DS29-0082")
CPUS = (8, 9)
POLICIES = {
    "wide": ("wide", None),
    "original": ("original", None),
    "replace": ("replace", None),
    "fill": ("fill", None),
    "timely": ("replace", 20_000_000),
}


def branch_events(doc, rows, legacy):
    """Match every measured reply to its native pair and recording delivery clock."""
    packets = dict(visit_pairs(doc["source"]["probes"]))
    excluded = {e["visit"] for e in doc["provenance"]["excluded_windows"]}
    clocks = doc["delivery_clocks"]
    first = clocks[0]["monotonic_ns"]
    events = []
    for visit, (clock, row) in enumerate(zip(clocks, rows, strict=True)):
        due = clock["monotonic_ns"] - first
        if (
            row["visit"] != visit
            or row["arrival_ns"] != due
            or row["delivery_clock"] != clock
            or (row["status"] == "invalid_capture") != (visit in excluded)
        ):
            raise ValueError("branch lost physical admission, visit order or delivery clock")
        finish = row.get("emitted_ns" if legacy else "finish_ns")
        pair = packets.get(visit)
        if legacy:
            emitted = row["outcome"] == "emitted"
        else:
            packet = row["packet"]
            emitted = packet is not None
            if emitted and (packet["visit"] != visit or tuple(packet["probes"]) != pair):
                raise ValueError("measured reply differs from its sealed native probes")
        if (pair is not None) != emitted or (emitted and (visit in excluded or finish is None)):
            raise ValueError(
                "an emitted valid visit requires its measured finish and stereo probes"
            )
        if not emitted:
            finish = None
        if finish is not None and finish < due:
            raise ValueError("measured detector completion precedes delivery")
        events.append((due, finish, pair))
    return events


def compose(fast, original, policy, cutoff):
    rule, max_age = POLICIES[policy]
    kept, choices, counts = [], [], Counter()
    for visit, (w, o) in enumerate(zip(fast, original, strict=True)):
        due, wide_end, wide_pair = w
        other_due, orig_end, orig_pair = o
        if due != other_due:
            raise ValueError("the detector traces have different scheduled arrivals")
        for branch, finish in (("wide", wide_end), ("original", orig_end)):
            if finish is not None:
                counts[branch + "_returned"] += 1
                counts[branch + "_after_cutoff"] += finish > cutoff
                counts[branch + "_within_20ms_at_cutoff"] += dual_rate.available(
                    finish, due, cutoff, 20_000_000
                )
        wide = wide_pair if dual_rate.available(wide_end, due, cutoff, max_age) else None
        orig = orig_pair if dual_rate.available(orig_end, due, cutoff, max_age) else None
        selected = dual_rate.select_probes(wide, orig, rule)
        if selected is None:
            continue
        kept.extend(selected)
        sources = []
        for lane, probe in enumerate(selected):
            uses_orig = orig is not None and probe is orig[lane]
            src = "original" if uses_orig else "wide"
            sources.append(src)
            counts[src + "_probes"] += 1
            counts["positive_probes"] += positive(probe)
            finish = orig_end if uses_orig else wide_end
            counts["positive_probes_within_20ms"] += positive(probe) and finish - due <= 20_000_000
            if wide is not None and uses_orig:
                counts["changed_probe_payloads"] += wide[lane] != probe
                counts["positive_gains"] += positive(probe) and not positive(wide[lane])
                counts["positive_losses"] += not positive(probe) and positive(wide[lane])
        choices.append((visit, *sources))
        counts["positive_visits"] += any(map(positive, selected))
    return kept, choices, counts


def physical_match(a, b):
    for key in ("clock_anchor", "delivery_clocks", "last_sample_counter", "schema_version"):
        if a[key] != b[key]:
            raise ValueError(f"detectors do not share {key}")
    for key in ("window_count", "invalid_capture", "excluded_windows"):
        if a["provenance"][key] != b["provenance"][key]:
            raise ValueError(f"detectors do not share {key}")
    keys = set(a["source"]) | set(b["source"])
    for key in keys - {"probes", "analysis_manifest_sha256"}:
        if a["source"].get(key) != b["source"].get(key):
            raise ValueError(f"detectors do not share physical authority {key}")


def read_sources(ident, legacy):
    if legacy:
        parent = paced_original.REPORT
        seal = sealed(parent, "prediction-lock.json", LEGACY)
        locators = {
            m: (f"raw/{m}/trace.json.gz", f"native/{m}/{ident}.json.gz")
            for m in ("wide", "original")
        }
        digest = LEGACY
    else:
        parent = JOINT
        receipt = parent / "manifest.json"
        manifest = whole_iq.read(receipt)
        branches = manifest["cases"][ident]["branches"]
        locators = {m: (branches[m]["trace"], branches[m]["native"]) for m in ("wide", "original")}
        seal = manifest
        digest = _sha(receipt)
    docs, events, hashes = {}, {}, {}
    for mode, (trace, native) in locators.items():
        for name in (trace, native):
            path = (parent / name).resolve()
            if not path.is_relative_to(parent.resolve()):
                raise ValueError("branch artifact lies outside its sealed evidence")
            whole_iq.checked(path, seal["files"][name])
            hashes[name] = _sha(path)
        doc = docs[mode] = arrival_queue.readgz(parent / native)
        events[mode] = branch_events(doc, arrival_queue.readgz(parent / trace), legacy)
    physical_match(docs["wide"], docs["original"])
    cutoff = events["wide"][-1][0]
    if not legacy and cutoff != manifest["cases"][ident]["last_arrival_ns"]:
        raise ValueError("published clock cutoff differs from the observed recording duration")
    return docs["wide"], events, cutoff, dict(parent=digest, files=hashes)


def run_cohort(work, legacy, out=None):
    cases = ("DS29-0082",) if legacy else CASES
    cohort = "separate" if legacy else "concurrent"
    if out is None:
        out = REPORT / "separate-clocks" if legacy else REPORT
    if work.exists() or (out / "position-input-lock.json").exists():
        raise FileExistsError("the position run needs an unused scratch and unfrozen input scope")
    work.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    anchor = SCREEN / "original-support/prepared-waveform"
    parent = sealed(anchor, "prediction-lock.json")
    release = whole_iq.read(
        whole_iq.checked(anchor / "source-lock.json", parent["files"]["source-lock.json"])
    )
    if whole_iq.receiver_identity(Path(release["receiver"])) != release["receiver_files"]:
        raise ValueError("position receiver differs from the complete original control")
    schedule, resources, source_files = [], [], {}
    for case_index, ident in enumerate(cases):
        case, req = whole_iq.binding(ident)
        base, events, cutoff, sources = read_sources(ident, legacy)
        if base["source"]["session_id"] != case["session_id"]:
            raise ValueError("detector streams and position request belong to different sessions")
        source_files[ident] = sources
        for idx, policy in enumerate(POLICIES):
            probes, choices, counts = compose(events["wide"], events["original"], policy, cutoff)
            chosen = f"selection/{ident}-{policy}.json.gz"
            arrival_queue.writegz(out / chosen, choices)
            lineage = recording_to_v5.digest([ident, cohort, policy, sources, _sha(out / chosen)])
            provenance = dict(base["provenance"])
            provenance.pop("detector_sha256", None)
            provenance.update(
                processed_windows=len(choices),
                run_id="replay-" + lineage[7:39],
                scope="Actual measured branch packets available by the specified clock cutoff",
            )
            material = dict(
                base,
                provenance=provenance,
                source=dict(base["source"], probes=probes, analysis_manifest_sha256=lineage),
            )
            folder = work / ident / policy
            folder.mkdir(parents=True)
            cpu = CPUS[(case_index + idx) % len(CPUS)]
            row = dict(
                id=ident,
                cohort=cohort,
                mode="matched-tile",
                policy=policy,
                method=f"parallel_{cohort}_{policy}",
                cpu=cpu,
                paired_capture_sha256=case["native"]["sha256"],
                original_request_sha256=case["request"]["sha256"],
                tile=case["regions"][0],
                catalog_sha256=case["catalog"]["sha256"],
                choice_file=chosen,
                selection_sha256=_sha(out / chosen),
                processed_visits=len(choices),
                cutoff_ns=cutoff,
                **counts,
            )
            row["native_sha256"], row["position_request_sha256"] = position.position_input(
                folder, case, req, release, material, cpu
            )
            schedule.append(row)
            resources.append(
                dict(
                    id=ident,
                    policy=policy,
                    selected_visits=len(choices),
                    scheduled=len(events["wide"]),
                    cutoff_ns=cutoff,
                    **{
                        k: counts[k]
                        for k in (
                            "wide_probes",
                            "original_probes",
                            "changed_probe_payloads",
                            "positive_gains",
                            "positive_losses",
                            "positive_probes",
                            "positive_visits",
                            "positive_probes_within_20ms",
                            "wide_returned",
                            "wide_after_cutoff",
                            "wide_within_20ms_at_cutoff",
                            "original_returned",
                            "original_after_cutoff",
                            "original_within_20ms_at_cutoff",
                        )
                    },
                )
            )
    csv_file(out / "support.csv", resources)
    write(out / "materializer.py.gz", gzip.compress(Path(__file__).read_bytes(), mtime=0))
    names = ["support.csv", "materializer.py.gz", *(r["choice_file"] for r in schedule)]
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=cases,
            sources=source_files,
            jobs=schedule,
            files={n: _sha(out / n) for n in names},
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            program_sha256=_sha(Path(__file__)),
            policy_sha256=_sha(Path(dual_rate.__file__)),
        ),
    )

    results = fit_jobs(work, out, schedule, CPUS)
    names.extend(r["service_log"] for r in results if r["service_log"])
    pack(out / "positions.jsonl.gz", sorted(results, key=lambda r: (r["id"], r["policy"])))
    names += ["positions.jsonl.gz", "position-input-lock.json"]
    save_json(
        out / "prediction-lock.json",
        dict(cases=cases, files={n: _sha(out / n) for n in sorted(names)}),
    )


def fit_jobs(work, out, schedule, cpus):
    """Run each frozen native input on its assigned CPU; return all terminal decisions."""
    if not cpus or len(set(cpus)) != len(cpus) or any(r["cpu"] not in cpus for r in schedule):
        raise ValueError("each fit must be assigned to exactly one available worker")

    def solve_cpu(cpu):
        results = []
        for r in (r for r in schedule if r["cpu"] == cpu):
            folder = work / r["id"] / r["policy"]
            whole_iq.checked(folder / "native.json", r["native_sha256"])
            whole_iq.checked(folder / "request.json", r["position_request_sha256"])
            receipt = log = None
            if r.get("positive_probes", 0):
                bracketed_position.launch_case(folder, cpu)
                result, receipt = service_result(folder, cpu)
                log = f"services/{r['id']}-{r['policy']}.log"
                write(out / log, (folder / "service.log").read_bytes())
            else:
                result = position.empty_result("withheld", "no_passing_probe_by_cutoff")
            results.append(dict(r, result=result, position_resources=receipt, service_log=log))
        return results

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        return [r for completed in pool.map(solve_cpu, cpus) for r in completed]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--separate-clocks", action="store_true")
    parser.add_argument("--out", type=local_output, help="directory for this run's frozen evidence")
    args = parser.parse_args()
    run_cohort(args.work, args.separate_clocks, args.out)
