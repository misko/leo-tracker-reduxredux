"""Matched raw-IQ frequency assay on frozen training-selected excerpts."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from estimator import errors, fit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HEADER = ROOT / "reports/2026_09_27_ds7_header"
sys.path.insert(0, str(HEADER))
from tcodes import demodulate, geometry, references  # noqa: E402


def main():
    inventory = HERE / "inventory.json"
    source = json.loads(inventory.read_text())
    plan = json.loads((HERE / "plan.json").read_text())
    expected = {(r["unit_id"], r["receiver_id"]) for r in plan["selections"]}
    actual = {(r["unit_id"], r["receiver_id"]) for r in source["rows"]}
    assert actual == expected and len(source["rows"]) == len(expected)
    for path, digest in source["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    hashes = {}
    rows = []
    for r in source["rows"]:
        result = {
            k: r[k]
            for k in (
                "unit_id",
                "session_id",
                "receiver_id",
                "track_id",
                "visit",
                "sample_rate_hz",
                "status",
            )
        }
        if r["status"] != "ok":
            result["reason"] = r["reason"]
            rows.append(result)
            continue
        path = ROOT / r["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"]
        hashes[r["path"]] = r["sha256"]
        try:
            iq = np.load(path)
            x = iq[:, 0].astype(float) + 1j * iq[:, 1]
            fs = r["sample_rate_hz"]
            _, pb, center = geometry(r["edge"])
            _, _, pilot = references(r["edge"])
            c = r["candidate"]
            cfo = c["fractional_tracking_cfo_hz"]
            epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            rf = np.fft.fftfreq(1024, 1 / 240e6)
            keep = abs(rf[pb] - center + cfo) <= 0.45 * fs
            pb = pb[keep]
            pilot = pilot[:, keep]
            assert len(pb) >= 2
            frames = []
            for n in range(8):
                ep = epoch + n * fs / 750
                start = max(0, int(ep) - round(fs * 10e-6))
                stop = start + round(fs * 0.00137)
                assert stop <= len(x)
                symbols = demodulate(x[start:stop], fs, ep - start, cfo, center)[1:]
                frames.append(symbols[:, pb] / pilot)
            frames = np.asarray(frames)
            f = dict(
                cached=0.0, short=fit(frames, np.arange(64)), long=fit(frames, np.arange(20, 220))
            )
            result.update(
                pilot_carriers=len(pb),
                cached_cfo_hz=cfo,
                arms={
                    name: dict(
                        residual_frequency_hz=value,
                        boundary=abs(value) >= 1499.999,
                        frame_nmse=errors(frames, value).tolist(),
                    )
                    for name, value in f.items()
                },
            )
        except Exception as exc:
            result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        rows.append(result)
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    for p in [
        inventory,
        HERE / "run.py",
        HERE / "estimator.py",
        HERE / "PROTOCOL.md",
        refs / "sssVec.mat",
        refs / "referenceTemplate.mat",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ] + list(HEADER.glob("*.py")):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    summary = {}
    for ds in ("all", "DS7", "DS8", "DS9"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        s = dict(planned=len(selected), returned=len(valid), frames=len(valid) * 8)
        for arm in ("short", "long"):
            gains = np.array(
                [
                    np.mean(r["arms"]["cached"]["frame_nmse"])
                    - np.mean(r["arms"][arm]["frame_nmse"])
                    for r in valid
                ]
            )
            s[arm] = dict(
                excerpts_improved=int((gains > 0).sum()),
                median_excerpt_gain=float(np.median(gains)) if len(gains) else None,
                mean_excerpt_gain=float(np.mean(gains)) if len(gains) else None,
                boundaries=sum(r["arms"][arm]["boundary"] for r in valid),
                median_absolute_frequency_change_hz=float(
                    np.median([abs(r["arms"][arm]["residual_frequency_hz"]) for r in valid])
                )
                if valid
                else None,
            )
        summary[ds] = s
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2, allow_nan=False)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
