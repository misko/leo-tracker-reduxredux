"""Replay the predeclared coherent-phase diagnostic against sealed scout centers."""

import gzip
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from ..__main__ import save_json, write
from ..variants import iq_stream, phase_scout_coherent
from . import phase_scout_trials as original
from .full_v5_check import _load_case, _sha
from .pilot_kernel_eval import _windows
from .portable_gate_trials import compressed_rows
from .wide_regional_eval import CHUNK_PREFIX, synthetic, templates


def main():
    from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S

    out = original.REPORT
    base = json.loads((out / "prediction-lock.json").read_bytes())
    for name, digest in base["files"].items():
        assert _sha(out / name) == digest
    rows = list(
        map(json.loads, gzip.decompress((out / "predictions.jsonl.gz").read_bytes()).splitlines())
    )
    config = dict(
        implementation=_sha(Path(phase_scout_coherent.__file__)),
        trial=_sha(Path(__file__)),
        protocol=_sha(out / "COHERENT-PROTOCOL.md"),
        inputs=_sha(out / "prediction-lock.json"),
    )
    save_json(out / "coherent-plan.json", config)
    saved = {}
    for ident in original.CASES:
        case = _load_case(ident)
        for seg, sequences in original.SCHEDULE:
            with patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX):
                windows = _windows(case, seg, sequences)
            saved.update(((ident, w.acquisition["global_visit"]), w) for w in windows)
    estimators = {
        edge: phase_scout_coherent.CoherentPilot(
            templates(original.RATE, edge)[0], OFDM_SYMBOL_DURATION_S
        )
        for edge in ("lower", "upper")
    }
    measured = []
    for row in rows:
        if row["condition"] == "recorded":
            window = saved[row["id"], row["visit"]]
        else:
            j = int(row["id"].rsplit("-", 1)[1])
            signal = [(735, row["plant_hz"], row["amplitude"])] if row["amplitude"] else []
            window = original._test_signal(
                synthetic(original.RATE, row["edge"]),
                signal,
                667201 + 37 * j + (row["edge"] == "upper"),
            )
        assert window.iq_sha256 == row["iq_sha256"]
        data = window.samples
        values = data[:, :, 0].astype(float) + 1j * data[:, :, 1].astype(float)
        estimate = estimators[row["edge"]]
        before = process_time()
        outrow = []
        for t in row["scout"]:
            mask, detail = estimate.allocate(values[:, t["receiver"]], t["epoch"])
            outrow.append(
                dict(receiver=t["receiver"], epoch=t["epoch"], mask=mask, diagnostic=detail)
            )
        measured.append(
            dict(
                id=row["id"],
                visit=row.get("visit"),
                iq_sha256=window.iq_sha256,
                scout=outrow,
                prototype_cpu_s=process_time() - before,
            )
        )
    raw = out / "coherent-diagnostic.jsonl.gz"
    write(raw, compressed_rows(measured))
    save_json(
        out / "coherent-lock.json",
        dict(files={p.name: _sha(p) for p in (raw, out / "coherent-plan.json")}),
    )


if __name__ == "__main__":
    main()
