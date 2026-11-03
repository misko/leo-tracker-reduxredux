"""Bounded replay of previously exported raw excerpts; no source-storage writes."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from estimator import TS, evaluate, rotation

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from tcodes import demodulate, geometry, references, slots  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    out = BASE / "local"
    out.mkdir(exist_ok=True)
    inventory = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    members = json.loads(inventory.read_text())
    sources = {str(inventory): sha(inventory)}
    streams = []
    for dataset, name in [("DS7", "S02"), ("DS8", "S13")]:
        member = next(m for m in members if m["signal"] == name)
        for rx, stream in enumerate(member["streams"]):
            streams.append((dataset, name, rx, Path(stream["folder"]), stream["row"]))
    folder = ROOT / "reports/2026_09_28_sequence_semantics/local/ds9-middle-10m"
    ip = folder / "inventory.json"
    sources[str(ip)] = sha(ip)
    for rx, row in enumerate(json.loads(ip.read_text())["exports"]):
        streams.append(("DS9", "DS9-middle", rx, folder, row))
    results = []
    for dataset, name, rx, folder, row in streams:
        path = folder / (row["name"] + ".npy")
        raw = np.load(path)
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        sources[str(path)] = sha(path)
        x = raw[:, 0].astype(float) + 1j * raw[:, 1]
        rate, edge = row["sample_rate_hz"], row["probe"]["edge"]
        bins, pb, center = geometry(edge)
        _, template, pilot = references(edge)
        candidate = row["candidate"]
        cfo = candidate["fractional_tracking_cfo_hz"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        rf = np.fft.fftfreq(1024, 1 / 240e6)
        bins = bins[abs(rf[bins] - center + cfo) <= 0.45 * rate]
        pilot_mask = abs(rf[pb] - center + cfo) <= 0.45 * rate
        pb, pilot = pb[pilot_mask], pilot[:, pilot_mask]
        assert len(pb) >= 2 and len(bins) > 0
        pm, dm = (rf[pb] - center) / 1e6, (rf[bins] - center) / 1e6
        mapping = slots(bins, np.arange(2, 302))
        for frame in range(12):
            ep = epoch + frame * rate / 750
            start = max(0, int(ep) - round(rate * 10e-6))
            stop = start + round(rate * 0.00137)
            if stop > len(x):
                raise ValueError("Protocol requires twelve complete frames")
            sy = demodulate(x[start:stop], rate, ep - start, cfo, center)[1:]
            pilots = sy[:, pb] / pilot
            data = sy[:, bins] * template[bins, 1:].T.conj()
            result = evaluate(pilots, data, mapping, pm, dm)
            # Known post-FFT perturbation: tests estimator equivariance only.
            injected = evaluate(
                pilots * rotation(np.arange(300) * TS, pm, [137, 7]),
                data * rotation(np.arange(300) * TS, dm, [137, 7]),
                mapping,
                pm,
                dm,
            )
            result["injection"] = dict(
                state_unchanged=result["state"] == injected["state"],
                arms={
                    arm: dict(
                        frequency_error_hz=injected["arms"][arm]["frequency_hz"]
                        - result["arms"][arm]["frequency_hz"]
                        - 137,
                        drift_error_ppm=injected["arms"][arm]["drift_ppm"]
                        - result["arms"][arm]["drift_ppm"]
                        - 7,
                    )
                    for arm in result["arms"]
                },
            )
            result.update(
                dataset=dataset,
                signal=name,
                receiver=rx,
                frame=frame,
                session=row["session_id"],
                rate_hz=rate,
                data_carriers=len(bins),
                pilot_carriers=len(pb),
            )
            results.append(result)
        print(dataset, name, rx, "complete", flush=True)
    for p in [
        BASE / "PROTOCOL.md",
        BASE / "estimator.py",
        BASE / "run.py",
        ROOT / "reports/2026_09_27_ds7_header/tcodes.py",
        ROOT / "reports/2026_09_27_ds7_header/analyze.py",
        ROOT / "reports/2026_09_27_ds7_header/recover.py",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]:
        sources[str(p)] = sha(p)
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    for filename in ["sssVec.mat", "referenceTemplate.mat"]:
        p = refs / filename
        sources[str(p)] = sha(p)
    output = dict(
        rows=results,
        input_sha256=sources,
        elapsed_seconds=time.monotonic() - started,
        python=sys.version,
        numpy=np.__version__,
    )
    (BASE / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    print("rows", len(results), "qualified", sum(r["qualified"] for r in results), flush=True)


if __name__ == "__main__":
    main()
