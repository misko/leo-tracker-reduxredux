"""Export one pilot-selected DS9 visit through read-only production contracts."""

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def strongest_pair(choices):
    groups = {}
    for p, c in choices:
        groups.setdefault((p.visit_index, p.edge), {0: [], 1: []})[p.receiver_id].append((p, c))
    pairs = [
        (a, b)
        for receivers in groups.values()
        for a in receivers[0]
        for b in receivers[1]
        if abs(a[1].integer_epoch_sample - b[1].integer_epoch_sample) < 5
    ]
    return max(pairs, key=lambda pair: min(c.fractional_margin for _, c in pair))


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--session-index", type=int, default=0)
    parser.add_argument("--tag", default="first")
    parser.add_argument("--paired", action="store_true")
    args = parser.parse_args()
    manifest_path = (BASE.parents[3] / "reports") / "2026_09_28_ds9_post_ds8/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    cap = [c for c in manifest["captures"] if c["sample_rate_hz"] == 10000000][args.session_index]
    folder = BASE / f"local/ds9-{args.tag}-10m"
    folder.mkdir(exist_ok=True)
    if (folder / "inventory.json").exists():
        raise FileExistsError("Existing export retained")
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    reader = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        raw = source.load(cap["session_id"])
        assert raw.input_manifest_sha256 == cap["manifest_sha256"]
        choices = [
            (p, c)
            for p in raw.probes
            if p.probe_start_ms == 0
            for c in p.candidates
            if c.passed_fractional_margin_gate
        ]
        probe, candidate = max(choices, key=lambda pc: pc[1].fractional_margin)
        paired = []
        for rx in () if args.paired else (0, 1):
            matches = [
                (p, c)
                for p, c in choices
                if p.visit_index == probe.visit_index
                and p.receiver_id == rx
                and p.edge == probe.edge
                and abs(c.integer_epoch_sample - candidate.integer_epoch_sample) < 5
            ]
            paired.append(max(matches, key=lambda pc: pc[1].fractional_margin))
        if args.paired:
            paired = strongest_pair(choices)
            probe, candidate = paired[0]
        session = reader.inspect(cap["session_id"])
        assert session.manifest_sha256 == cap["manifest_sha256"]
        visit, values = reader.read_visit_ci16(session, probe.visit_index)
        if len(values) > 3600000:
            raise ValueError("Visit exceeds 360 ms analysis bound")
        exports = []
        for p, c in paired:
            excerpt = values[:, p.receiver_id, :].copy()
            name = f"visit-{p.visit_index}-rx-{p.receiver_id}"
            np.save(folder / (name + ".npy"), excerpt)
            exports.append(
                dict(
                    name=name,
                    session_id=cap["session_id"],
                    visit=visit.model_dump(mode="json"),
                    probe={k: v for k, v in dataclasses.asdict(p).items() if k != "candidates"},
                    candidate=dataclasses.asdict(c),
                    sample_rate_hz=10000000,
                    excerpt_start_in_visit=0,
                    excerpt_samples=len(excerpt),
                    excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                )
            )
        result = dict(
            dataset="DS9",
            manifest_sha256=session.manifest_sha256,
            analysis_manifest_sha256=raw.analysis_manifest_sha256,
            ds9_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            session_index=args.session_index,
            policy=(
                "Maximize weaker receiver margin" if args.paired else "Maximize individual margin"
            )
            + "; qualified cached start-zero pilots, either edge, before bit inspection; "
            "peer epochs within five samples. One existing visit only.",
            exports=exports,
        )
        (folder / "inventory.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            cap["session_id"],
            probe.visit_index,
            probe.edge,
            [c.fractional_margin for _, c in paired],
            values.shape,
        )
    finally:
        source.close()
        reader.close()


if __name__ == "__main__":
    main()
