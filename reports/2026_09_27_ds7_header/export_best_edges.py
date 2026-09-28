"""Export two existing visits selected by the all-19-session cached survey."""

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    base = Path(__file__).parent / "local"
    survey = json.loads((base / "survey/cached-candidates.json").read_text())
    assert len(survey["sessions"]) == 19
    reader = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    for edge in ["upper"] if args.holdout else ["lower", "upper"]:
        ranked = [
            (session, c)
            for session in survey["sessions"]
            for c in session["top"]
            if c["probe"]["edge"] == edge
        ]
        selected, seed = max(ranked, key=lambda sc: sc[1]["candidate"]["fractional_margin"])
        if args.holdout:
            same_session = sorted(
                [sc for sc in ranked if sc[0]["session_id"] == selected["session_id"]],
                key=lambda sc: sc[1]["candidate"]["fractional_margin"],
                reverse=True,
            )
            selected, seed = same_session[1]
        sid = selected["session_id"]
        session = reader.inspect(sid)
        assert session.manifest_sha256 == selected["manifest_sha256"]
        raw = inputs.load(sid)
        assert raw.input_manifest_sha256 == session.manifest_sha256
        index = seed["probe"]["visit_index"]
        visit, values = reader.read_visit_ci16(session, index)
        assert len(values) == 1200000
        out = base / (("holdout-" if args.holdout else "best-") + edge)
        out.mkdir(exist_ok=True)
        exports = []
        for receiver in [0, 1]:
            choices = [
                (p, c)
                for p in raw.probes
                if p.visit_index == index
                and p.receiver_id == receiver
                and p.probe_start_ms == 0
                and p.edge == edge
                for c in p.candidates
                if c.passed_fractional_margin_gate
                and abs(c.integer_epoch_sample - seed["candidate"]["integer_epoch_sample"]) < 5
            ]
            if not choices:
                raise ValueError(f"No matched peer epoch: {sid} {index} RX{receiver}")
            probe, candidate = max(choices, key=lambda pc: pc[1].fractional_margin)
            name = f"visit-{index}-rx-{receiver}"
            excerpt = values[:, receiver, :].copy()
            np.save(out / (name + ".npy"), excerpt)
            exports.append(
                dict(
                    name=name,
                    session_id=sid,
                    visit=visit.model_dump(mode="json"),
                    probe={k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"},
                    candidate=dataclasses.asdict(candidate),
                    sample_rate_hz=10000000,
                    excerpt_start_in_visit=0,
                    excerpt_samples=len(excerpt),
                    excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                )
            )
            print(edge, sid, name, candidate.fractional_margin, flush=True)
        (out / "inventory.json").write_text(
            json.dumps(
                dict(
                    dataset_sha256=survey["dataset_sha256"],
                    reader_release=survey["reader_release"],
                    manifest_sha256=session.manifest_sha256,
                    exports=exports,
                    selection=(
                        "second-ranked visit in best upper session; prospective word validation"
                        if args.holdout
                        else ("highest cached margin per edge across all 19 10 MS/s sessions; "
                              "matched peer RX")
                    ),
                ),
                indent=2,
            )
            + "\n"
        )
    inputs.close()


if __name__ == "__main__":
    main()
