"""Offline ranking ablation on opened challenge data, never a holdout pass.

Restore some/all projection amplitude discarded by normalized correlation.
This uses only IQ and screen diagnostics to select a window; confirmation and
injected truth are inspected afterwards. All-six confirmation is an offline
lookup comparator, not the runtime proposed for ARM.
"""

import argparse
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from tools.presence_decision_challenge import PROTOCOL, associated, cases, generate, passing
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest, write_json


def projection_norms(iq, rate, bins=512):
    """Independent NumPy oracle for the existing centered projection energy."""
    if rate not in (2500000, 5000000) or iq.dtype != np.int16:
        raise ValueError("native CI16 geometry required")
    window, n = rate // 50, round(rate / 750)
    if iq.shape != (6 * window, 2):
        raise ValueError("complete dwell required")
    output = np.zeros((2, 6))
    for slice_index in range(6):
        raw = iq[slice_index * window:(slice_index + 1) * window].astype(np.int64)
        sums, support = np.zeros(n, complex), np.zeros(n)
        for frame in range(15):
            start = round(frame * (rate / 750))
            count = min(n, window - start - 4)
            a, b = raw[start:start + count], raw[start + 4:start + 4 + count]
            sums[:count] += a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]
            sums[:count] += 1j * (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
            support[:count] += 1
        folded = sums / np.maximum(support, 1)
        position = np.arange(bins) * n / bins
        left = position.astype(int)
        point = folded[left] + (position - left) * (folded[(left + 1) % n] - folded[left])
        boundaries = np.arange(bins + 1) * n / bins
        cells = boundaries.astype(int)
        cumulative = np.r_[0, np.cumsum(folded)]
        integral = cumulative[cells] + (boundaries - cells) * folded[np.minimum(cells, n - 1)]
        area = np.diff(integral) / (n / bins)
        for projection, values in enumerate((point, area)):
            output[projection, slice_index] = np.linalg.norm(values - np.mean(values))
    return output


def select(scores, norms, exponent):
    if exponent not in (0, 0.5, 1):
        raise ValueError("undeclared ranking ablation")
    weighted = np.asarray(scores) * (norms**exponent)
    order = np.argsort(-weighted, axis=1, kind="stable")
    contrast = np.array([row[idx[0]] / max(row[idx[1]], 1e-30)
                         for row, idx in zip(weighted, order, strict=True)])
    projection = int(contrast[1] > contrast[0])
    return int(order[projection, 0])


def run(source, output):
    if any(output.resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("output must not be beneath archive storage")
    protocol = json.loads(PROTOCOL.read_text())
    policy = protocol["policies"]["frozen_absolute_score_hypothesis"]
    library = source / "detector.so"
    original = [json.loads(line) for line in (source / "results.jsonl").read_text().splitlines()]
    if len(original) != 528:
        raise ValueError("complete opened challenge required")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "freeze.json", {
        "scope": "post-hoc development ablation; no qualification claim",
        "exponents": [0, 0.5, 1], "source_results_sha256": digest(source / "results.jsonl"),
        "binary_sha256": digest(library), "tool_sha256": digest(Path(__file__)),
    })
    totals = {}
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        engines = {}
        for index, spec in enumerate(cases(protocol)):
            iq, truth = generate(spec)
            if (truth != original[index]["truth"]
                    or hashlib.sha256(iq.tobytes()).hexdigest() != original[index]["iq_sha256"]):
                raise ValueError("opened challenge truth or IQ identity differs")
            key = spec["rate_hz"], spec["edge"]
            if key not in engines:
                engines[key] = stack.enter_context(NativeDwell(library, *key, 512))
            native = engines[key]
            result = unpack(native.run(iq, maximum=6, seeded=False))
            screens = unpack(native.screens())
            norms = projection_norms(iq, key[0])
            choices = {}
            for exponent in (0, 0.5, 1):
                window = select(screens["scores"], norms, exponent)
                position = result["rank"]["order"].index(window)
                confirm = result["confirmations"][position]
                accepted = passing(confirm["candidates"][:confirm["candidate_count"]], policy)
                matched = any(associated(c, truth, window, protocol["association"])
                              for c in accepted)
                choices[str(exponent)] = {"window": window, "flagged": bool(accepted),
                                          "associated": matched}
                label = f"{exponent}:{key[0]}:{spec['kind']}:{spec.get('snr_db', 'none')}"
                stats = totals.setdefault(label, {"cases": 0, "flagged": 0, "associated": 0})
                stats["cases"] += 1
                stats["flagged"] += bool(accepted)
                stats["associated"] += matched
            if (choices["0"]["window"] != original[index]["selected_window"]
                    or choices["0"]["flagged"] != original[index]["decisions"][
                        "frozen_absolute_score_hypothesis"]["flagged"]):
                raise ValueError("normalized baseline does not reproduce opened challenge")
            stream.write(json.dumps({"truth": truth, "norms": norms.tolist(),
                                     "scores": screens["scores"], "choices": choices}) + "\n")
            if (index + 1) % 64 == 0:
                print(f"{index + 1}/528 ranking ablations evaluated", flush=True)
    write_json(output / "summary.json", totals)
    print(json.dumps({k: v for k, v in totals.items() if "pilot_plus_tone" in k}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.source, args.output)
