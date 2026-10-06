"""Bounded IQ offset controls on published seeds; no reacquisition or writes."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from rate64_phase_convention import bias, physical_frame

from leo.analysis.starlink import pilot_methods
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.storage.adaptive_hop import AdaptiveHopIqStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    metrics = json.loads((args.input / "metrics.json").read_text())
    audit = {r["session_id"]: r for r in json.loads(args.audit.read_text())}
    selected = []
    for rate in (2500000, 10000000):
        for edge in ("lower", "upper"):
            recent = sorted(
                [r for r in metrics if r["rate"] == rate and r["edge"] == edge],
                key=lambda r: r["captured_at"],
                reverse=True,
            )[:8]
            ranked = sorted(recent, key=lambda r: r["glrt"]["pass_fraction"])
            selected.append(ranked[len(ranked) // 2])
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    results = []
    for scan in selected:
        sid = scan["session_id"]
        fs = scan["rate"]
        edge = scan["edge"]
        with store.reader(sid) as reader:
            retained_indexes = {
                visit.event.visit_index: index
                for index, visit in enumerate(reader.session.manifest.receipt.visits)
            }
            for key, e in sorted(audit[sid]["examples"].items()):
                if e["channel"] not in (1, 4):
                    continue
                visit, ci16 = reader.read_visit_ci16(retained_indexes[e["visit_index"]])
                assert visit.event.visit_index == e["visit_index"]
                rx = e["receiver_id"]
                start = e["probe_start_ms"] * fs // 1000
                vals = ci16[start : start + fs // 50, rx, :]
                iq = vals[:, 0].astype(float) + 1j * vals[:, 1].astype(float)
                w = e["candidate"]
                epoch = w["integer_epoch_sample"]
                cfo = w["acquired_cfo_hz"]
                fraction = w["fractional_epoch_offset_samples"]
                assert (
                    int(w["integer_device_sample_counter"])
                    == visit.event.valid_start_counter + start + epoch
                )
                b = conditioned_glrt64_score(
                    iq,
                    fs,
                    epoch_sample=epoch,
                    acquired_cfo_hz=cfo,
                    fractional_epoch_offset_samples=fraction,
                    edge=edge,
                )
                assert abs(b.margin - w["fractional_margin"]) < 1e-7, (
                    sid,
                    key,
                    b.margin,
                    w["fractional_margin"],
                )
                baseline = dict(exact=b.exact_score, control=b.control_score, margin=b.margin)

                # Controls use the same original epoch and frame inventory.
                def exact_control(
                    delta=0.0,
                    shift=0,
                    wrong=False,
                    conjugate=False,
                    iq=iq,
                    fs=fs,
                    epoch=epoch,
                    cfo=cfo,
                    fraction=fraction,
                    edge=edge,
                ):
                    sc = conditioned_glrt64_score(
                        np.conj(iq) if conjugate else iq,
                        fs,
                        epoch_sample=max(0, epoch + shift),
                        acquired_cfo_hz=(-cfo if conjugate else cfo) + delta,
                        fractional_epoch_offset_samples=fraction,
                        edge=("upper" if edge == "lower" else "lower") if wrong else edge,
                    )
                    return dict(exact=sc.exact_score, control=sc.control_score, margin=sc.margin)

                offsets = {
                    str(delta): exact_control(delta=delta)
                    for delta in (-312500.0, -234375.0, -117187.5, 117187.5, 234375.0, 312500.0)
                }
                # Report-only physical-coordinate check, identical IQ and seeds.
                # No production template, artifact, or persisted CFO is changed.
                with patch.object(pilot_methods, "qin_edge_pilot_frame", physical_frame):
                    physical = exact_control(delta=-bias(edge))
                result = dict(
                    session_id=sid,
                    rate=fs,
                    edge=edge,
                    lane=key,
                    visit_index=e["visit_index"],
                    candidate_rank=w["candidate_rank"],
                    baseline=baseline,
                    offsets=offsets,
                    physical_template=physical,
                    cfo_convention_bias_hz=bias(edge),
                    minus_symbol=exact_control(shift=-round(fs * 4.4e-6)),
                    plus_symbol=exact_control(shift=round(fs * 4.4e-6)),
                    wrong_edge=exact_control(wrong=True),
                    conjugated=exact_control(conjugate=True),
                    input_manifest_sha256=reader.session.manifest_sha256,
                )
                results.append(result)
                args.output.write_text(json.dumps(results, indent=2))
                print(sid, key, round(baseline["margin"], 4), flush=True)
    store.close()


if __name__ == "__main__":
    main()
