"""Fixed-rate identity transfer using the full common 10MS/s carrier support."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import corpus_identity as protocol
import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/bandwidth-extension"
NAMES = ["four_carrier_sign_baseline", "wide_phase", "wide_relative_phase", "wide_sign"]


def extract(z, bins, core):
    u = z / np.maximum(abs(z), 1e-10)
    adjacent = np.flatnonzero(np.diff(bins) == 1)
    relative = u[:, :, adjacent] * u[:, :, adjacent + 1].conj()
    ids = np.searchsorted(bins, core)
    assert np.array_equal(bins[ids], core)
    return [((z[:, :, ids].real >= 0) * 2 - 1).reshape(2, -1),
            np.concatenate([u.real.reshape(2, -1), u.imag.reshape(2, -1)], axis=1),
            np.concatenate([relative.real.reshape(2, -1), relative.imag.reshape(2, -1)], axis=1),
            ((z.real >= 0) * 2 - 1).reshape(2, -1)]


def main():
    OUT.mkdir(exist_ok=True)
    source = BASE / "local/rows.json"
    seal = json.loads((BASE / "local/seal.json").read_text())["files"]
    assert protocol.sha(source) == seal["local/rows.json"]
    rows = [r for r in json.loads(source.read_text()) if r["rate"] == 10000000]
    support = {}
    for r in rows:
        path = Path(r["source_artifact"])
        assert protocol.sha(path) == r["source_artifact_sha256"]
        with np.load(path) as data:
            meta = json.loads(str(data["metadata"]))
            bins = set(map(int, data["bins"])) - set(meta["pilot_bins"])
            edge = r["edge"]
            support[edge] = support[edge] & bins if edge in support else bins
    support = {edge: np.array(sorted(bins)) for edge, bins in support.items()}
    assert len(support["upper"]) == len(support["lower"])
    arrays = [[] for _ in NAMES]
    for r in rows:
        with np.load(r["source_artifact"]) as data:
            meta = json.loads(str(data["metadata"]))
            bins = support[r["edge"]]
            z = data["z"][meta["evaluation_frames"], :6][:, :, np.searchsorted(data["bins"], bins)]
            core = [486, 487, 496, 497] if r["edge"] == "upper" else [526, 527, 536, 537]
            for a, f in zip(arrays, extract(z, bins, core), strict=True):
                a.append(f)
    arrays = [np.array(a, dtype=float) for a in arrays]
    strata = defaultdict(list)
    for i, r in enumerate(rows):
        strata[r["edge"], r["channel"], r["receiver"]].append(i)
    for ids in strata.values():
        for a in arrays:
            mean, scale = a[ids, 0].mean(0), np.maximum(a[ids, 0].std(0), .25)
            a[ids] = (a[ids] - mean) / scale
    arrays = [protocol.unit(a) for a in arrays]
    np.savez_compressed(OUT / "features.npz", **dict(zip(NAMES, arrays, strict=True)))
    protocol.FEATURES = NAMES
    results = []
    for scope in ("same_channel", "cross_channel_session",
                  "same_channel_pairs", "cross_channel_session_pairs"):
        for tier in ("all", "strong"):
            result = protocol.experiment(rows, arrays, scope, tier)
            # The inherited four-carrier-specific ablation is not applicable to
            # the 26-carrier representation and is deliberately not reported.
            result.pop("exclude_symbol2_sign_effect", None)
            results.append(result)
            print(json.dumps({k: v for k, v in result.items()
                              if k in ("scope", "tier", "same_candidate_pairs",
                                       "matched_same_pairs",
                                       "effect", "session_preserving_corrected_p",
                                       "trajectory_preserving_max_p", "abstention")}), flush=True)
    result = dict(rows=len(rows), labeled=sum(r["norad_id"] is not None for r in rows),
                  dataset_counts=dict(Counter(r["dataset"] for r in rows)),
                  support={k: v.tolist() for k, v in support.items()}, features=NAMES,
                  experiments=results, input_sha256={str(source): protocol.sha(source),
                                                     str(Path(protocol.__file__)): protocol.sha(
                                                         Path(protocol.__file__))},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitations="Additional common carrier measurements, fixed 10MS/s population. "
                  "Same reserved frame split and matching/permutation protocol as the initial "
                  "study. Computational holdout, previously inspected recordings. Conditional "
                  "labels; no decoded RF identity. Four feature maxima and eight-scope correction "
                  "are within this exploratory follow-up, not across all historical hypotheses.")
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
