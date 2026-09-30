"""Audit the post-hoc highest-scoring parity relation for marginal-bit bias."""

import hashlib
import json
from pathlib import Path

import numpy as np
from blind_header_114 import qualified_checks
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def agreement_audit(columns):
    columns = np.asarray(columns, dtype=int)
    signs = 1 - 2 * columns
    correlation = float(np.prod(signs, axis=1).mean())
    baseline = float(np.prod(signs.mean(axis=0)))
    return dict(
        rows=len(columns),
        ones=columns.sum(axis=0).tolist(),
        observed_agreement=(1 + correlation) / 2,
        independent_marginal_agreement=(1 + baseline) / 2,
        agreement_excess=(correlation - baseline) / 2,
    )


def main():
    source = BASE / "local/blind_header_114_activity_0_parity_window.json"
    candidates = json.loads(source.read_text())["exact_discovery_candidates"]
    chosen = max(candidates, key=lambda c: c["evaluation"])
    old_path = BASE / "local/pilot_referenced_header_bits.npz"
    new_path = BASE / "local/full-reference-0-12.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.load(old_path)["bins"]
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(new_path)["symbols"][:, 1:7][:, :, bins]
    z = z * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8)
    valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    order = (
        np.argsort(np.fft.fftfreq(1024)[bins])
        if chosen["order"] == "physical"
        else np.argsort(bins)
    )
    ids = order[:: chosen["direction"]][chosen["start"] : chosen["start"] + 114]
    bits = bits[:12, chosen["symbol"] - 2][:, ids]
    valid = valid[:12, chosen["symbol"] - 2][:, ids]
    windows, support, enough = qualified_checks(
        bits[::2] ^ bits[1::2], valid[::2] & valid[1::2], "interleaved", chosen["pair"]
    )
    columns = [i for i in range(14) if chosen["mask"] >> i & 1]
    selected = windows[:, columns]
    assert enough and support == [32] * 6 and len(columns) == 2
    table = np.bincount(selected @ np.array([2, 1]), minlength=4).reshape(2, 2)
    pairs = selected.reshape(6, 32, 2)
    shifts = [
        float((pairs[:, :, 0] == np.roll(pairs[:, :, 1], shift, axis=1)).mean())
        for shift in range(32)
    ]
    result = dict(
        candidate=chosen,
        metrics=agreement_audit(selected),
        contingency_rows_first_bit_columns_second_bit=table.tolist(),
        within_pair_circular_shift_agreement=shifts,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, old_path, new_path, template_path)
        },
        limitation="Candidate selected using evaluation scores; exploratory reuse. "
        "Marginal baseline is descriptive, not an independence claim. Overlapping "
        "windows and selected shifts do not supply independent statistical trials. "
        "No full encoder or RF message is recovered.",
    )
    (BASE / "local/parity_bias_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
