"""Bounded lower-edge UT symbol reference; compare independently with upper edge."""

import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from fetch_ut_reference import URL, Remote  # noqa: E402
from recover import geometry, references  # noqa: E402
from tcodes import compact_indices, fit_code, score_code, select_window, slots  # noqa: E402


def main():
    dest = OUT / "ut-lower-806-818.npz"
    bins = geometry("lower")[0]
    if not dest.exists():
        remote = Remote()
        with h5py.File(remote, "r") as source:
            raw = source["yDataDec"][806:819, :, bins]
        np.savez_compressed(dest, symbols=raw["real"] + 1j * raw["imag"], bins=bins)
        (OUT / "ut-lower-inventory.json").write_text(
            json.dumps(
                dict(
                    url=URL,
                    etag=remote.etag,
                    fetched_bytes=remote.total,
                    elapsed_s=time.monotonic() - remote.started,
                    sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                    limitation="Published hard symbols, not raw IQ; zero-based frames 806..818",
                ),
                indent=2,
            )
            + "\n"
        )
    upper_folder = ROOT / "reports/2026_09_27_ds7_header/local/ut-reference"
    upper_path = upper_folder / "decoded-upper-806-818.npz"
    upper_inventory = json.loads((upper_folder / "inventory.json").read_text())
    lower_inventory = json.loads((OUT / "ut-lower-inventory.json").read_text())
    assert upper_inventory["etag"] == lower_inventory["etag"]
    assert hashlib.sha256(upper_path.read_bytes()).hexdigest() == upper_inventory["output_sha256"]
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == lower_inventory["sha256"]
    upper = np.load(upper_path)
    lower = np.load(dest)
    _, template, _ = references()
    rows = []
    for frame, upper_symbols, lower_symbols in zip(
        upper["zero_based_frames"], upper["symbols"], lower["symbols"], strict=True
    ):
        uz = upper_symbols[1:] * template[upper["bins"], 1:].T.conj()
        first, selection, _ = select_window(uz, upper["bins"])
        symbols = np.arange(first, first + 64)
        code, _, _ = fit_code(uz[first - 2 : first + 62], slots(upper["bins"], symbols))
        z = lower_symbols[1:] * template[bins, 1:].T.conj()
        z = z[first - 2 : first + 62]
        finite = ((compact_indices(bins)[None, :] - (16 * symbols[:, None]) % 60) % 1004) % 60
        simple = (compact_indices(bins)[None, :] - 16 * symbols[:, None]) % 60
        row = dict(
            frame=int(frame),
            first_symbol=first,
            upper_selection=selection,
            lower_finite_prediction=score_code(z, finite, code),
            lower_simple_prediction=score_code(z, simple, code),
            finite_best_shift=max(score_code(z, finite, np.roll(code, j)) for j in range(60)),
            simple_best_shift=max(score_code(z, simple, np.roll(code, j)) for j in range(60)),
        )
        rows.append(row)
        print(row, flush=True)
    (OUT / "ut-lower-reference-check.json").write_text(json.dumps(rows, indent=2) + "\n")
    assert all(r["lower_simple_prediction"] > 0.99 for r in rows)


if __name__ == "__main__":
    main()
