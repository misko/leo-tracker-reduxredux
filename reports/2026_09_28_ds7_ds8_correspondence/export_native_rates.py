"""Bounded read-only native-rate sample, selected without decoding data bits."""

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local/rate-validation/native"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260928)
    survey = []
    for dataset, relative in [
        ("DS7", "reports/2026_09_27_ds7_post_ds6/manifest.json"),
        ("DS8", "reports/2026_09_28_ds8_post_ds7/manifest.json"),
    ]:
        path = ROOT / relative
        manifest = json.loads(path.read_text())
        store = AdaptiveHopIqStore(Path(manifest["source_bulk_root"]), read_only=True)
        inputs = ScannerTrackingInputStore(Path(manifest["source_bulk_root"]))
        for rate in [7500000, 5000000, 2500000]:
            captures = [c for c in manifest["captures"] if c["sample_rate_hz"] == rate]
            capture = captures[int(rng.integers(len(captures)))]
            sid = capture["session_id"]
            session = store.inspect(sid)
            assert session.manifest_sha256 == capture["manifest_sha256"]
            raw = inputs.load(sid)
            assert raw.input_manifest_sha256 == session.manifest_sha256
            pairs = {}
            for probe in raw.probes:
                if probe.probe_start_ms != 0:
                    continue
                for candidate in probe.candidates:
                    if not candidate.passed_fractional_margin_gate:
                        continue
                    key = (probe.visit_index, probe.edge)
                    by_rx = pairs.setdefault(key, {})
                    old = by_rx.get(probe.receiver_id)
                    if old is None or candidate.fractional_margin > old[1].fractional_margin:
                        by_rx[probe.receiver_id] = (probe, candidate)
            eligible = [
                (key, rows)
                for key, rows in pairs.items()
                if set(rows) == {0, 1}
                and abs(rows[0][1].integer_epoch_sample - rows[1][1].integer_epoch_sample)
                <= rate * 0.5e-6
            ]
            eligible.sort(
                key=lambda item: min(c.fractional_margin for p, c in item[1].values()), reverse=True
            )
            summary = dict(
                dataset=dataset,
                rate_hz=rate,
                session_id=sid,
                eligible_pairs=len(eligible),
                exports=[],
            )
            seen = set()
            with store.reader(sid, expected=session) as reader:
                for (index, edge), rows in eligible:
                    if index in seen:
                        continue
                    seen.add(index)
                    folder = OUT / f"{dataset}-{rate}-{index}"
                    folder.mkdir(exist_ok=True)
                    visit, values = reader.read_visit_ci16(index)
                    exports = []
                    for rx, (probe, candidate) in sorted(rows.items()):
                        excerpt = values[: round(rate * 0.120), rx, :].copy()
                        name = f"rx{rx}"
                        np.save(folder / (name + ".npy"), excerpt)
                        exports.append(
                            dict(
                                name=name,
                                session_id=sid,
                                sample_rate_hz=rate,
                                manifest_sha256=session.manifest_sha256,
                                analysis_manifest_sha256=raw.analysis_manifest_sha256,
                                visit=visit.model_dump(mode="json"),
                                probe={
                                    k: v
                                    for k, v in dataclasses.asdict(probe).items()
                                    if k != "candidates"
                                },
                                candidate=dataclasses.asdict(candidate),
                                excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                            )
                        )
                    (folder / "inventory.json").write_text(
                        json.dumps(
                            dict(
                                dataset=dataset,
                                dataset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                selection=(
                                    "Seed 20260928, one random session per dataset/rate; "
                                "two strongest distinct dual-RX pilot visits, "
                                "no data-bit selection"
                                ),
                                exports=exports,
                            ),
                            indent=2,
                        )
                        + "\n"
                    )
                    summary["exports"].append(str(folder.relative_to(OUT)))
                    print(dataset, rate, sid, index, edge, flush=True)
                    if len(seen) == 2:
                        break
            survey.append(summary)
        inputs.close()
    (OUT / "survey.json").write_text(json.dumps(survey, indent=2) + "\n")


if __name__ == "__main__":
    main()
