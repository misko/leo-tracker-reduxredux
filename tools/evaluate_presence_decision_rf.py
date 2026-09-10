"""Evaluate the frozen decision hypothesis on a metadata-selected saved cohort.

RX1 only, read-only archive adapter. Dense references are comparison evidence,
not independent Starlink truth; unmatched RF must remain unresolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.arm_presence import fresh_glrt
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from tools.evaluate_native_presence_budgets import associated
from tools.presence_decision_challenge import passing, prepare
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest, write_json


def visits(protocol):
    sweeps = protocol["rf_sweeps"]
    sessions = protocol["rf_sessions"]
    if (
        len(sweeps) != 2
        or sweeps != sorted(set(sweeps))
        or any(type(s) is not int or not 0 <= s < 290 for s in sweeps)
        or len(sessions) != 4
        or len({s["session_id"] for s in sessions}) != 4
        or sorted(s["rate_hz"] for s in sessions) != [2500000, 2500000, 5000000, 5000000]
    ):
        raise ValueError("bounded, distinct and balanced RF cohort required")
    return [sweep * 8 + edge for sweep in sweeps for edge in range(8)]


def summarize(rows, protocol):
    result = {}
    for name in protocol["policies"]:
        result[name] = {}
        for rate in protocol["rates_hz"]:
            subset = [r for r in rows if r["rate_hz"] == rate]
            if not subset:
                continue
            positive = [r for r in subset if any(r["reference_positive"])]
            unresolved = [r for r in subset if not any(r["reference_positive"])]
            result[name][str(rate)] = {
                "dwells": len(subset),
                "reference_positive_dwells": len(positive),
                "flags_in_reference_positive": sum(
                    r["decisions"][name]["flagged"] for r in positive
                ),
                "associated_reference_positive": sum(
                    r["decisions"][name]["associated"] for r in positive
                ),
                "unresolved_rf_dwells": len(unresolved),
                "flags_in_unresolved_rf": sum(r["decisions"][name]["flagged"] for r in unresolved),
            }
    return result


def load_references(directory, manifests, indices):
    """Reuse only the exact recorded comparison, not a silently changed cohort."""
    freeze = json.loads((directory / "source-freeze.json").read_text())
    if freeze["sessions"] != manifests:
        raise ValueError("reference source manifests differ")
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    mapped = {(r["session"], r["visit"]): r for r in rows}
    expected = {(session, index) for session in manifests for index in indices}
    if len(rows) != len(expected) or set(mapped) != expected:
        raise ValueError("reference source inventory differs")
    return mapped


def validate_reference(row, *, input_sha, rate, edge, counter):
    if (
        row["iq_sha256"] != input_sha
        or row["rate_hz"] != rate
        or row["edge"] != edge
        or row["rx"] != 1
        or row["source_counter"] != str(counter)
    ):
        raise ValueError("reference IQ identity differs")


def diagnose(row, result, protocol):
    """Offline six-confirmation comparator; never a proposed realtime budget.

    Preserve same-window agreement and separately count within-dwell agreement.
    Each 20 ms slice is exactly 15 frame periods at these two sample rates, so
    its start offset cancels in the circular epoch comparison. This assumes
    sufficiently stable timing/CFO over 120 ms; it is not independent truth.
    """
    if result["confirmation_count"] != 6 or result["confirmation_window_mask"] != 63:
        raise ValueError("all six diagnostic confirmations required")
    order = result["rank"]["order"]
    if sorted(order) != list(range(6)) or order[0] != row["selected_window"]:
        raise ValueError("diagnostic rank changed")
    confirmations = result["confirmations"]
    first = confirmations[0]
    if first["candidates"][: first["candidate_count"]] != row["candidates"]:
        raise ValueError("diagnostic first confirmation changed")
    references = [[c for c in cs if c["margin"] >= 0.025] for cs in row["reference_candidates"]]
    all_references = [c for cs in references for c in cs]
    comparisons = {}
    for name, policy in protocol["policies"].items():
        windows = []
        for index, confirmation in zip(order, confirmations, strict=True):
            candidates = confirmation["candidates"][: confirmation["candidate_count"]]
            accepted = passing(candidates, policy)
            windows.append(
                {
                    "window": index,
                    "flagged": bool(accepted),
                    "reference_positive": bool(references[index]),
                    "same_window_associated": any(
                        associated(c, ref, row["rate_hz"], protocol["association"])
                        for c in accepted
                        for ref in references[index]
                    ),
                    "within_dwell_associated": any(
                        associated(c, ref, row["rate_hz"], protocol["association"])
                        for c in accepted
                        for ref in all_references
                    ),
                }
            )
        comparisons[name] = windows
    return {
        "scope": "offline all-window comparator, not the one-confirmation worker",
        "result": result,
        "comparisons": comparisons,
    }


def summarize_diagnostics(rows, protocol):
    result = {}
    for name in protocol["policies"]:
        result[name] = {}
        for rate in protocol["rates_hz"]:
            subset = [r for r in rows if r["rate_hz"] == rate]
            result[name][str(rate)] = {}
            for budget in (1, 2, 3, 6):
                positive = [r for r in subset if any(r["reference_positive"])]
                unresolved = [r for r in subset if not any(r["reference_positive"])]

                def count(records, field, policy=name, limit=budget):
                    return sum(
                        any(w[field] for w in r["diagnostics"]["comparisons"][policy][:limit])
                        for r in records
                    )

                result[name][str(rate)][str(budget)] = {
                    "reference_positive_dwells": len(positive),
                    "flags_in_reference_positive": count(positive, "flagged"),
                    "same_window_associated": count(positive, "same_window_associated"),
                    "within_dwell_associated": count(positive, "within_dwell_associated"),
                    "unresolved_rf_dwells": len(unresolved),
                    "flags_in_unresolved_rf": count(unresolved, "flagged"),
                }
    return result


def run(archive, output, prefix, *, amplitude=False, reference_run=None, all_windows=False):
    protocol, library = prepare(output, prefix, amplitude=amplitude)
    indices = visits(protocol)
    inputs = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(archive))
    sources = [inputs.source(s["session_id"]) for s in protocol["rf_sessions"]]
    for spec, source in zip(protocol["rf_sessions"], sources, strict=True):
        if (
            source.sample_rate_hz != spec["rate_hz"]
            or not source.receipt.qualified
            or source.plan.valid_visit_ms != 120
            or 1 not in source.receiver_ids
            or len(source.visits) <= indices[-1]
        ):
            raise ValueError("source differs from frozen metadata selection")
    reference_rows = {}
    if reference_run is not None:
        reference_rows = load_references(
            reference_run, {s.session_id: s.input_manifest_sha256 for s in sources}, indices
        )
    write_json(
        output / "source-freeze.json",
        {
            "state": "source_manifests_frozen_before_IQ_or_scores",
            "sessions": {s.session_id: s.input_manifest_sha256 for s in sources},
            "visit_indices": indices,
            "rx": 1,
            "tool_sha256": digest(Path(__file__)),
            "reference": "fresh eight-candidate fractional GLRT in each of six 20 ms slices",
            "reference_reused_sha256": digest(reference_run / "results.jsonl")
            if reference_run is not None
            else None,
            "interpretation": "development replay of opened cohort"
            if reference_run
            else "initial frozen RF comparison; not independent Starlink truth",
            "all_window_diagnostic": all_windows,
        },
    )
    rows = []
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        engines = {}
        for source in sources:
            for index in indices:
                visit = source.read_visit(index)
                rate, edge = source.sample_rate_hz, visit.span.target.edge
                iq = np.ascontiguousarray(visit.samples_ci16[:, source.receiver_ids.index(1), :])
                key = rate, edge
                if key not in engines:
                    engines[key] = stack.enter_context(NativeDwell(library, rate, edge, 512))
                result = unpack(engines[key].run(iq, maximum=1, seeded=False))
                selected = result["rank"]["order"][0]
                confirm = result["confirmations"][0]
                candidates = confirm["candidates"][: confirm["candidate_count"]]
                # Reference output never supplies a timing/CFO seed to the worker.
                values = iq[:, 0].astype(np.float64) + 1j * iq[:, 1]
                input_sha = hashlib.sha256(iq.tobytes()).hexdigest()
                prior = reference_rows.get((source.session_id, index))
                if prior is not None:
                    validate_reference(
                        prior,
                        input_sha=input_sha,
                        rate=rate,
                        edge=edge,
                        counter=visit.span.valid_device_sample_counter,
                    )
                    references = prior["reference_candidates"]
                else:
                    references = [
                        [
                            asdict(c)
                            for c in fresh_glrt(
                                values[w * rate // 50 : (w + 1) * rate // 50],
                                rate,
                                edge=edge,
                                candidate_count=protocol["rf_reference_candidates"],
                            )
                        ]
                        for w in range(6)
                    ]
                positive = [[c for c in cs if c["margin"] >= 0.025] for cs in references]
                decisions = {}
                for name, policy in protocol["policies"].items():
                    accepted = passing(candidates, policy)
                    decisions[name] = {
                        "flagged": bool(accepted),
                        "associated": any(
                            associated(c, ref, rate, protocol["association"])
                            for c in accepted
                            for ref in positive[selected]
                        ),
                    }
                row = {
                    "session": source.session_id,
                    "visit": index,
                    "rx": 1,
                    "rate_hz": rate,
                    "edge": edge,
                    "channel": visit.span.target.channel,
                    "source_counter": str(visit.span.valid_device_sample_counter),
                    "source_manifest_sha256": source.input_manifest_sha256,
                    "iq_sha256": input_sha,
                    "selected_window": selected,
                    "candidates": candidates,
                    "reference_candidates": references,
                    "reference_positive": [bool(cs) for cs in positive],
                    "decisions": decisions,
                }
                if all_windows:
                    full = unpack(engines[key].run(iq, maximum=6, seeded=False))
                    row["diagnostics"] = diagnose(row, full, protocol)
                    row["diagnostics"]["screens"] = unpack(engines[key].screens())
                rows.append(row)
                stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                print(f"{source.session_id} visit {index}: {len(rows)}/64 scored", flush=True)
    result = {
        "scope": "RF reference agreement, not independent specificity or absence",
        "dwells": len(rows),
        "binary_sha256": digest(library),
        "results": summarize(rows, protocol),
    }
    if all_windows:
        result["offline_comparators"] = summarize_diagnostics(rows, protocol)
    write_json(output / "summary.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw-prefix", required=True, type=Path)
    parser.add_argument("--rank-amplitude", action="store_true")
    parser.add_argument(
        "--reference-run",
        type=Path,
        help="Reuse hash-checked references; this is now development data",
    )
    parser.add_argument(
        "--all-windows",
        action="store_true",
        help="Offline all-six comparator; does not change the one-window policy",
    )
    args = parser.parse_args()
    run(
        args.archive,
        args.output,
        args.fftw_prefix,
        amplitude=args.rank_amplitude,
        reference_run=args.reference_run,
        all_windows=args.all_windows,
    )
