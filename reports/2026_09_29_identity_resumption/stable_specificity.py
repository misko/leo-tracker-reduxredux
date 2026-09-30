"""Do discovery-consensus stable signs distinguish other candidate satellites?"""

import hashlib
import json
from pathlib import Path

import numpy as np
from corpus_identity import separation_bin

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / "2026_09_29_ds10_signal_extension/local"
OUT = BASE / "local"


def main():
    rows = json.loads((OUT / "rows.json").read_text())
    stability = json.loads((OUT / "within-visit.json").read_text())
    profiles = [p for p in stability["stability"] if p["donor"] == p["target"]
                and p["mode"] == "consensus"]
    results, sources = [], {}
    for profile in profiles:
        name = profile["donor"]
        visit = int(name.split("-v")[1])
        donor_meta = next(r for r in rows if r["unit"] == "DS10-F010" and r["visit"] == visit)
        assert donor_meta["norad_id"] == 63400
        path = PRIOR / f"paired/{name}/{name}-data-soft.npz"
        summary = json.loads(path.with_name("summary.json").read_text())
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert sources[str(path)] == summary["header"]["sha256"]
        with np.load(path) as data:
            lookup = {int(k): i for i, k in enumerate(data["bins0"])}
            discovery = data["z0"][summary["header"]["discovery_frames"], :6]
            majority = (discovery.real >= 0).mean(0) >= .5
        for mode in ("all_early", "exclude_symbol2"):
            coords = [tuple(c) for c in profile["coordinates"] if mode == "all_early" or c[0] != 2]
            candidates = []
            for r in rows:
                if r["edge"] != "lower" or r["norad_id"] is None:
                    continue
                if r["session"] == donor_meta["session"] and r["visit"] == visit:
                    continue
                p = Path(r["source_artifact"])
                assert hashlib.sha256(p.read_bytes()).hexdigest() == r["source_artifact_sha256"]
                with np.load(p) as data:
                    bins = {int(k): i for i, k in enumerate(data["bins"])}
                    common = [c for c in coords if c[1] in bins]
                    if len(common) < 3:
                        continue
                    meta = json.loads(str(data["metadata"]))
                    frame = meta["evaluation_frames"][1]
                    signs = np.array([data["z"][frame, s - 2, bins[k]].real >= 0
                                      for s, k in common])
                expected = np.array([majority[s - 2, lookup[k]] for s, k in common])
                dt = abs(r["selected_utc_ns"] - donor_meta["selected_utc_ns"]) / 1e9
                candidates.append(dict(id=r["id"], candidate=r["norad_id"],
                                       same=r["norad_id"] == donor_meta["norad_id"],
                                       agreement=float((signs == expected).mean()),
                                       coordinates=common, channel=r["channel"], rate=r["rate"],
                                       receiver=r["receiver"], pilot=r["pilot"],
                                       same_session=r["session"] == donor_meta["session"],
                                       time_bin=separation_bin(dt)))
            comparisons = []
            for target in (r for r in candidates if r["same"]):
                control = [r for r in candidates if not r["same"] and all(r[k] == target[k]
                           for k in ("coordinates", "channel", "rate", "receiver"))
                           and abs(r["pilot"] - target["pilot"]) <= .1]
                strict = [r for r in control if all(r[k] == target[k]
                          for k in ("same_session", "time_bin"))]
                comparisons.append(dict(target=target["id"], agreement=target["agreement"],
                                        controls=len(control), strict_controls=len(strict),
                                        control_mean=float(np.mean(
                                            [r["agreement"] for r in control]))
                                        if control else None,
                                        strict_mean=float(np.mean([r["agreement"] for r in strict]))
                                        if strict else None))
            results.append(dict(donor=name, mode=mode, selected_coordinates=coords,
                                candidates=candidates, comparisons=comparisons))
    result = dict(experiments=results, input_sha256=sources,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitations="Masks and values learned from early donor frames; second reserved "
                  "evaluation frame tests other tracks. At least three shared coordinates. "
                  "Conditional candidate IDs, same coordinate footprint/channel/rate/RX and "
                  "pilot gap<=.1 matched controls; strict controls additionally match session "
                  "relation and time bin. Exploratory descriptive comparisons, no field claims.")
    (OUT / "stable-specificity.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in results:
        print(r["donor"], r["mode"], "coverage", len(r["candidates"]), r["comparisons"])


if __name__ == "__main__":
    main()
