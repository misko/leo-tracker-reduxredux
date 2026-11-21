"""Package verified input samples and score split-frame and held-symbol reference waveforms."""

import argparse
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from ..variants import full_epoch_glrt as g
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_bundle import add
from .reverse_glrt_reference import digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import Verifier, key
from .single_scan_roster import OUT, WORK
from .two_carrier_conditional import labels
from .two_carrier_position import ORIGINAL
from .two_carrier_reference import adjudicate


def archive(out, work):
    work.mkdir(exist_ok=True, parents=True)
    dest = work / "fresh-iq.zip"
    temp = dest.with_suffix(".partial")
    index = []
    for panel in ("fresh", "backward"):
        p = out / panel / "roster.json"
        if _sha(p) != read(p.parent / "manifest.json")["roster_sha256"]:
            raise ValueError("fresh input roster changed")
    with zipfile.ZipFile(temp, "w") as z:
        for panel in ("fresh", "backward"):
            for r in read(out / panel / "roster.json"):
                name = key(r)
                record = read(out / panel / "measurements" / (name + ".json"))
                segment, manifest, w = decode(_load_case(r["case"]), r["visit"])
                raw = w.samples.tobytes()
                if (
                    w.iq_sha256 != record["signed_iq"]
                    or w.iq_sha256 != "sha256:" + digest(raw)
                    or record["row_id"] != r["id"]
                    or manifest != record["manifest"]
                    or w.acquisition["sample_start"] != r["counter"]
                    or w.target["edge"] != r["edge"]
                    or w.target["channel"] != r["channel"]
                ):
                    raise ValueError("raw sample binding failed")
                file = "iq/" + name + ".ci16"
                add(z, file, raw, 1)
                index.append(
                    dict(
                        key=name,
                        panel=panel,
                        case=r["case"],
                        visit=r["visit"],
                        evaluated_antenna=r["rx"],
                        channel=r["channel"],
                        edge=r["edge"],
                        physical_id=r["id"],
                        file=file,
                        sha256=w.iq_sha256,
                        shape=list(w.samples.shape),
                        dtype="<i2",
                        sample_rate_hz=w.sample_rate_hz,
                        hardware_sample_counter=r["counter"],
                        receiver_ids=w.receiver_ids,
                        segment=segment,
                        manifest_sha256=manifest,
                        window_sequence=w.sequence,
                        target=w.target,
                        acquisition=w.acquisition,
                    )
                )
        add(
            z,
            "index.json",
            packed(dict(format="little-endian int16 [sample, antenna, I/Q]", visits=index)) + b"\n",
            6,
        )
    with zipfile.ZipFile(temp) as z:
        rows = json.loads(z.read("index.json"))["visits"]
        if len(rows) != 143 or len({(r["case"], r["visit"]) for r in rows}) != len(rows):
            raise ValueError("fresh panel has duplicate or missing visits")
        for r in rows:
            if "sha256:" + digest(z.read(r["file"])) != r["sha256"]:
                raise ValueError("signed sample archive failed replay")
    temp.replace(dest)
    (out / "inputs.json").write_bytes(
        packed(dict(path=str(dest), sha256=_sha(dest), visits=len(rows), bytes=dest.stat().st_size))
        + b"\n"
    )


def reference(w, row, folder):
    name = key(row)
    m = read(folder / "measurements" / (name + ".json"))
    path = folder / "grids" / (name + ".npz")
    if w.iq_sha256 != m["signed_iq"] or _sha(path) != m["grid_sha256"] or row["id"] != m["row_id"]:
        raise ValueError("receiver reference and raw observation differ")
    iq = w.samples[:, row["rx"]]
    x = np.asarray(iq[:, 0] + 1j * iq[:, 1], np.complex64)
    with np.load(path) as grid:
        sweep = g.Sweep(grid["hz"], grid["exact_epoch"], grid["exact_score"])
    verifier = Verifier(ORIGINAL, row["edge"], w.samples, row["rx"])
    try:
        split = adjudicate(x, g.pilot(row["edge"]), g.pilot(row["edge"], True), sweep, verifier)
    finally:
        verifier.close()
    return dict(
        key=name,
        physical_id=row["id"],
        iq=w.iq_sha256,
        grid_sha256=m["grid_sha256"],
        strongest=m["blind"]["even"] if m["blind"]["replicated"] else None,
        split=split,
        waveforms=labels(x, row["edge"], split),
    )


def score_one(row):
    dest = OUT / "fresh/reference" / (key(row) + ".json")
    _, _, w = decode(_load_case(row["case"]), row["visit"])
    temp = dest.with_suffix(".partial")
    temp.write_bytes(packed(reference(w, row, OUT / "fresh")) + b"\n")
    temp.replace(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("iq", "reference"))
    args = parser.parse_args()
    if args.action == "iq":
        archive(OUT, WORK)
    else:
        (OUT / "fresh/reference").mkdir(exist_ok=True)
        with ProcessPoolExecutor(max_workers=4) as pool:
            list(pool.map(score_one, read(OUT / "fresh/roster.json")))
