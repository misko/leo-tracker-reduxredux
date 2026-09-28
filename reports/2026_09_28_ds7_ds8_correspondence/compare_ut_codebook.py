"""Cross-frequency validation of UT T-codes and comparison with DS7/DS8."""

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from summarize import family

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).parent
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from tcodes import bit_word, fit_code, references, score_code, select_window, slots  # noqa: E402


def recover_catalogue(bins0, bins1, z0, z1):
    accepted = []
    for frame, (a, b) in enumerate(zip(z0, z1, strict=True)):
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            continue
        first, selection, _ = select_window(a, bins0)
        symbols = np.arange(first, first + 64)
        m0, m1 = slots(bins0, symbols), slots(bins1, symbols)
        code0, _, count0 = fit_code(a[symbols - 2], m0)
        code1, _, count1 = fit_code(b[symbols - 2], m1)
        held = score_code(b[symbols - 2], m1, code0)
        if (
            selection > 0.9
            and held > 0.9
            and count0.all()
            and count1.all()
            and np.array_equal(code0, code1)
        ):
            word = bit_word(code0)
            accepted.append(
                dict(
                    frame=frame,
                    first_symbol=first,
                    word=word,
                    family=family(word),
                    selection=selection,
                    held=held,
                )
            )
    return accepted


def main():
    inputs = []
    archives = []
    etags = []
    for k in [100, 200]:
        path = BASE / f"local/ut-codebook/bins-{k}.npz"
        meta = json.loads(path.with_suffix(".json").read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["output_sha256"]
        inputs.append(path)
        archives.append(np.load(path))
        etags.append(meta["etag"])
    assert etags[0] == etags[1]
    _, template, _ = references()
    bins0, bins1 = [a["bins"] for a in archives]
    z0, z1 = [a["symbols"][:, 1:] * template[a["bins"], 1:].T.conj() for a in archives]
    accepted = recover_catalogue(bins0, bins1, z0, z1)
    families = {r["family"] for r in accepted}
    exact_words = {r["word"] for r in accepted}
    source = BASE / "local/decoded-bits.csv"
    inputs.append(source)
    local = [dict(group=r["group"], word=r["raw_bits"]) for r in csv.DictReader(source.open())]
    for path in sorted((BASE / "local/rate-validation/native").glob("*/native-results.json")):
        inputs.append(path)
        result = json.loads(path.read_text())
        local.extend(
            dict(group=result["group"], word=r["rx0_word"])
            for r in result["results"]
            if r["full_word_candidate"]
        )
    summary = dict(
        ut_frames_tested=len(z0),
        ut_frames_accepted=len(accepted),
        ut_exact_words=len({r["word"] for r in accepted}),
        ut_families=len(families),
        local_observations=len(local),
        local_matching=sum(family(r["word"]) in families for r in local),
        local_exact_matching=sum(r["word"] in exact_words for r in local),
        local_families=len({family(r["word"]) for r in local}),
        local_unmatched_families=sorted({family(r["word"]) for r in local} - families),
    )
    output = dict(
        summary=summary,
        accepted=accepted,
        local_matches=[
            dict(
                **r,
                exact_reference_frames=[u["frame"] for u in accepted if u["word"] == r["word"]],
                family_reference_frames=[
                    u["frame"] for u in accepted if u["family"] == family(r["word"])
                ],
            )
            for r in local
        ],
        input_sha256={
            str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs
        },
        limitation="Published hard-symbol cross-frequency check, not independent raw demodulation. "
        "64-symbol windows miss shorter T-code blocks. "
        "Family permits cyclic rotation and inversion. "
        "No ID, time, header metadata or payload interpretation.",
    )
    (BASE / "local/ut-codebook/comparison.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
