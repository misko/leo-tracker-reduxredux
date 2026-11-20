"""Seal receiver-lane epoch forecasts from the eight earlier wide recordings."""

import gzip
import json
from pathlib import Path

from ..__main__ import ROOT, save_json, write
from ..variants import epoch_carry
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
ARCHIVES = (SCREEN / "detector-origins/whole-band", SCREEN / "acquisition-support/fresh-waveform")
OUT = SCREEN / "receiver-core/epoch-carry"


def roster():
    result = []
    for folder in ARCHIVES:
        lock_path = folder / "prediction-lock.json"
        seal = json.loads(lock_path.read_bytes())
        result.extend(
            dict(
                id=ident,
                native=str((folder / f"native/{ident}.json.gz").relative_to(SCREEN)),
                native_sha256=seal["files"][f"native/{ident}.json.gz"],
                archive_lock_sha256=_sha(lock_path),
            )
            for ident in seal["cases"]
        )
    if len(result) != 8 or len({r["id"] for r in result}) != 8:
        raise ValueError("expected eight independently sealed complete wide waveforms")
    return result


def load(row):
    path = SCREEN / row["native"]
    if _sha(path) != row["native_sha256"]:
        raise ValueError("saved wide pilot factors changed")
    return json.loads(gzip.decompress(path.read_bytes()))


def key(probe):
    return tuple(probe[k] for k in ("visit_index", "receiver_id", "probe_index"))


def lane(probe):
    return tuple(probe[k] for k in ("receiver_id", "channel", "edge"))


def predict(authority):
    doc = load(authority)
    source = doc["source"]
    carry = epoch_carry.Holdover(source["sample_rate_hz"])
    latest = {}
    for probe in source["probes"]:
        sample, port = probe["valid_start_counter"], lane(probe)
        if port[0] in latest and sample <= latest[port[0]]:
            raise ValueError("receiver probes arrived out of hardware counter order")
        latest[port[0]] = sample
        self_result = carry.forecast(port, sample)
        other = carry.null_channel(port, sample) if self_result is not None else None
        wrong = (
            dict(self_result, epoch=(self_result["epoch"] + carry.period / 3) % carry.period)
            if self_result is not None
            else None
        )
        yield dict(
            id=authority["id"],
            key=key(probe),
            lane=port,
            sample=sample,
            own=self_result,
            wrong_channel=other,
            wrong_time=wrong,
        )
        carry.advance(port, sample, probe["candidates"])


def main():
    plan = dict(
        cases=roster(),
        sources={
            p.name: _sha(p)
            for p in (Path(__file__), Path(epoch_carry.__file__), OUT / "PROTOCOL.md")
        },
    )
    save_json(OUT / "plan.json", plan)
    raw = OUT / "predictions.jsonl.gz"
    write(raw, compressed_rows(r for case in plan["cases"] for r in predict(case)))
    save_json(
        OUT / "prediction-lock.json",
        dict(
            files={p.name: _sha(p) for p in (raw, OUT / "plan.json")},
            cases=[c["id"] for c in plan["cases"]],
        ),
    )


if __name__ == "__main__":
    main()
