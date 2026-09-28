"""Bounded uniform re-analysis of all locally exported DS7/DS8 IQ visits.

No new RF, no use of satellite labels/codebooks in decoding, no overwritten
historical results. Single-RX and partial words remain explicitly provisional.
"""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
ROOT = BASE.parents[1]
JOINT = ROOT / "reports/2026_09_28_ds7_ds8_correspondence"
sys.path.insert(0, str(JOINT))
from native_rate_decode import recover  # noqa: E402
from tcodes import bit_word, fit_code, score_code, select_window, slots  # noqa: E402

OUT = BASE / "local"


def inventory():
    old = ROOT / "reports/2026_09_27_ds7_header/local"
    paths = [
        old / "inventory.json",
        *old.glob("*/inventory.json"),
        *JOINT.glob("local/*/inventory.json"),
        *JOINT.glob("local/rate-validation/native/*/inventory.json"),
    ]
    best = {}
    for path in sorted(paths):
        data = json.loads(path.read_text())
        for row in data.get("exports", []):
            iq = path.parent / (row["name"] + ".npy")
            if not iq.exists():
                continue
            probe = row["probe"]
            key = (
                row["session_id"],
                probe["visit_index"],
                probe["edge"],
                probe["probe_start_ms"],
                probe["receiver_id"],
            )
            samples = len(np.load(iq, mmap_mode="r"))
            item = dict(
                row=row,
                folder=str(path.parent),
                samples=samples,
                inventory_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            if key not in best or samples > best[key]["samples"]:
                best[key] = item
    visits = defaultdict(list)
    for key, item in best.items():
        visits[key[:-1]].append(item)
    labels = {
        (g["session_id"], g["visit"]): g["norad_id"]
        for g in json.loads((JOINT / "local/joint-results.json").read_text())["groups"]
    }
    result = []
    for i, (key, streams) in enumerate(sorted(visits.items())):
        streams.sort(key=lambda item: item["row"]["probe"]["receiver_id"])
        result.append(
            dict(
                signal=f"S{i + 1:02}",
                session=key[0],
                visit=key[1],
                edge=key[2],
                probe_start_ms=key[3],
                norad_id=labels.get(key[:2]),
                streams=streams,
            )
        )
    return result


def evaluate_words(streams):
    bins0, z0, meta0 = streams[0]
    results = []
    frames = set(meta0["evaluation_frames"])
    if len(streams) == 2:
        frames &= set(streams[1][2]["evaluation_frames"])
    for frame in sorted(frames):
        first, selection, _ = select_window(z0[frame], bins0)
        symbols = np.arange(first, first + 64)
        a = z0[frame, symbols - 2]
        m0 = slots(bins0, symbols)
        code0, _, count0 = fit_code(a, m0)
        result = dict(
            frame=frame,
            first_symbol=first,
            word=bit_word(code0),
            selection=float(selection),
            observed=int((count0 > 0).sum()),
            accepted=False,
            status="single_receiver_unverified",
        )
        if len(streams) == 2:
            bins1, z1, meta1 = streams[1]
            m1 = slots(bins1, symbols)
            b = z1[frame, symbols - 2]
            code1, _, count1 = fit_code(b, m1)
            shared = (count0 > 0) & (count1 > 0)
            mask = shared[m1]
            held = score_code(b[mask], m1[mask], code0) if mask.any() else 0.0
            rng = np.random.default_rng(701 + frame)
            wrong_scores = []
            for _ in range(1000):
                wrong = code0.copy()
                wrong[shared] = rng.permutation(code0[shared])
                wrong_scores.append(score_code(b[mask], m1[mask], wrong) if mask.any() else 0.0)
            pilot = min(
                meta["diagnostics"][frame]["held_pilot_coherence"] for meta in [meta0, meta1]
            )
            agrees = bool(shared.any() and np.array_equal(code0[shared], code1[shared]))
            passed = bool(
                selection > 0.25
                and held > 0.25
                and held > max(wrong_scores)
                and pilot > 0.5
                and agrees
            )
            full = bool(passed and shared.all())
            result.update(
                peer_word=bit_word(code1),
                shared=int(shared.sum()),
                disagreements=int(np.sum(code0[shared] != code1[shared])),
                held=held,
                wrong_max=max(wrong_scores),
                pilot_min=pilot,
                accepted=full,
                status="verified_full" if full else "partial_candidate" if passed else "rejected",
            )
        results.append(result)
    return results


def header_features(streams, edge):
    """Stable early-symbol signs corroborated across RX and disjoint frame halves.

    These are descriptive reference-relative header features, not message bits.
    Unstable/unreceived positions are omitted, never silently filled with zeros.
    """
    if len(streams) != 2:
        return []
    common = np.intersect1d(streams[0][0], streams[1][0])
    panels = []
    for bins, z, meta in streams:
        frames = np.array(meta["evaluation_frames"])
        indices = [np.flatnonzero(bins == k)[0] for k in common]
        for half in [frames[::2], frames[1::2]]:
            if len(half) < 3:
                return []
            good = [f for f in half if meta["diagnostics"][int(f)]["held_pilot_coherence"] > 0.5]
            if len(good) < 3:
                return []
            panel = z[np.array(good), :8][:, :, indices]
            panels.append(np.mean(np.sign(panel.real), axis=0))
    panels = np.array(panels)
    stable = (np.min(abs(panels), axis=0) >= 0.8) & (
        np.all(panels > 0, axis=0) | np.all(panels < 0, axis=0)
    )
    return [
        dict(key=f"{edge}:{i + 2}:{int(k)}", bit=int(panels[0, i, j] > 0))
        for i in range(8)
        for j, k in enumerate(common)
        if stable[i, j]
    ]


def main():
    OUT.mkdir(exist_ok=True)
    visits = inventory()
    (OUT / "inventory.json").write_text(json.dumps(visits, indent=2) + "\n")
    for visit in visits:
        path = OUT / (visit["signal"] + ".json")
        binding = hashlib.sha256(json.dumps(visit, sort_keys=True).encode()).hexdigest()
        if path.exists() and json.loads(path.read_text()).get("binding") == binding:
            print(visit["signal"], "checkpoint exists", flush=True)
            continue
        try:
            streams = [
                recover(item["row"], Path(item["folder"]), frame_limit=90)
                for item in visit["streams"]
            ]
            results = evaluate_words(streams)
            output = dict(
                binding=binding,
                signal=visit["signal"],
                results=results,
                receivers=[s[2] for s in streams],
                header_features=header_features(streams, visit["edge"]),
            )
        except (ValueError, AssertionError, IndexError) as exc:
            output = dict(
                binding=binding,
                signal=visit["signal"],
                error=f"{type(exc).__name__}: {exc}",
                results=[],
            )
        path.write_text(json.dumps(output, indent=2) + "\n")
        print(
            visit["signal"],
            visit["visit"],
            "accepted",
            sum(r["accepted"] for r in output["results"]),
            "/",
            len(output["results"]),
            output.get("error", ""),
            flush=True,
        )


if __name__ == "__main__":
    main()
