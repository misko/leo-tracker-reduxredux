"""Probe symbols 8–9 using region-matched, disjoint reference-frame pairs."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from blind_header_114 import check_score, mixed_null_check, qualified_checks
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def frame_split(rows, symbol):
    eligible = [
        r["frame_index"]
        for r in rows
        if r["binary_like_intervals"][0][0] == 2 and r["binary_like_intervals"][0][1] >= symbol
    ]
    if len(eligible) < 8:
        raise ValueError("Need eight eligible frames for two pairs per split")
    return eligible[:4], eligible[4:8], eligible[8:]


def main():
    source = BASE / "local/full-reference-0-12.npz"
    map_path = BASE / "local/frame_binary_map.json"
    bins_path = BASE / "local/pilot_referenced_header_bits.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    frames = json.loads(map_path.read_text())["frames"]
    bins = np.load(bins_path)["bins"]
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 7:9][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 7:9].T)
    bits = (z.real >= 0).astype(np.uint8)
    valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    candidates, splits = [], {}
    tested = {layout: 0 for layout in ("interleaved", "stream_blocks")}
    for symbol in (8, 9):
        discovery, evaluation, unused = frame_split(frames, symbol)
        splits[symbol] = dict(discovery=discovery, evaluation=evaluation, unused=unused)
        for name, order in [
            ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
            ("fft", np.argsort(bins)),
        ]:
            for direction in (1, -1):
                ids = order[::direction]
                groups = []
                for indices in (discovery, evaluation):
                    b = bits[indices, symbol - 8][:, ids]
                    q = valid[indices, symbol - 8][:, ids]
                    groups.append((b[::2] ^ b[1::2], q[::2] & q[1::2]))
                for start, layout, pair in itertools.product(
                    range(len(ids) - 113), tested, itertools.combinations(range(3), 2)
                ):
                    b, q = groups[0]
                    w, support, enough = qualified_checks(
                        b[:, start : start + 114], q[:, start : start + 114], layout, pair
                    )
                    if not enough:
                        continue
                    tested[layout] += 1
                    mask = mixed_null_check(w, activity_floor=0)
                    if mask is None:
                        continue
                    b, q = groups[1]
                    e, eval_support, enough = qualified_checks(
                        b[:, start : start + 114], q[:, start : start + 114], layout, pair
                    )
                    selected = ((mask >> np.arange(14)) & 1).astype(bool)
                    means = e[:, selected].mean(axis=0) if len(e) else np.array([0.0])
                    candidates.append(
                        dict(
                            symbol=symbol,
                            order=name,
                            direction=direction,
                            start=start,
                            first_bin=int(bins[ids[start]]),
                            layout=layout,
                            pair=pair,
                            mask=mask,
                            discovery_support=support,
                            evaluation_support=eval_support,
                            evaluation=check_score(e, mask) if len(e) else None,
                            evaluation_qualified=enough,
                            evaluation_variable=bool(((means > 0) & (means < 1)).all()),
                        )
                    )
    summary = {
        layout: dict(
            tested=n,
            exact_discovery=sum(c["layout"] == layout for c in candidates),
            exact_evaluation=sum(
                c["layout"] == layout
                and c["evaluation"] == 1
                and c["evaluation_qualified"]
                and c["evaluation_variable"]
                for c in candidates
            ),
        )
        for layout, n in tested.items()
    }
    result = dict(
        summary=summary,
        splits=splits,
        candidates=candidates,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, map_path, bins_path, template_path)
        },
        limitation="Exploratory reuse of one recording. Eligibility uses mapped region "
        "extent, not parity scores. Two disjoint pairs per split. Necessary exact "
        "relations only, noise-sensitive; no full code, semantic field, or FEC recovery.",
    )
    (BASE / "local/extended_header_probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(summary=summary, splits=splits), indent=2))


if __name__ == "__main__":
    main()
