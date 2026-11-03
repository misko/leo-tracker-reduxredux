import json

import numpy as np
from study import HERE, ROOT, read, sha


def cosine(a, b):
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return None if norm == 0 else float(np.dot(a, b) / norm)


def main():
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    results, failures = [], []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        r = read(HERE / f"{ds}.json")
        assert r["manifest_sha256"] == sha(HERE / "manifest.json")
        assert len(r["audits"]) == 24
        for window in ("early", "middle", "late"):
            tracks = [t for t in r["rows"] if t["window"] == window]
            assert len({t["session_id"] for t in tracks}) == 8
            receivers = []
            for rx in (0, 1):
                subset = [t for t in tracks if t["receiver"] == rx]
                receivers.append(
                    dict(
                        receiver=rx,
                        tracks=len(subset),
                        raw_gradient=sum(np.array(t["gradient"][:2]) for t in subset).tolist(),
                        profiled_gradient=sum(
                            np.array(t["profiled_gradient"]) for t in subset
                        ).tolist(),
                    )
                )
            bands = []
            total = sum(np.array(t["profiled_gradient"]) for t in tracks)
            for rf in sorted({t["rf_hz"] for t in tracks}):
                subset = [t for t in tracks if t["rf_hz"] == rf]
                g = sum(np.array(t["profiled_gradient"]) for t in subset)
                bands.append(
                    dict(
                        rf_hz=rf,
                        tracks=len(subset),
                        profiled_gradient=g.tolist(),
                        cosine_with_total=cosine(g, total),
                    )
                )
            norms = sorted(
                (float(np.linalg.norm(t["profiled_gradient"])) for t in tracks), reverse=True
            )
            results.append(
                dict(
                    dataset=ds,
                    window=window,
                    tracks=len(tracks),
                    receivers=receivers,
                    raw_rx_cosine=cosine(*[x["raw_gradient"] for x in receivers]),
                    profiled_rx_cosine=cosine(*[x["profiled_gradient"] for x in receivers]),
                    profiled_total=total.tolist(),
                    top10_gross_norm_fraction=sum(norms[:10]) / sum(norms),
                    bands=bands,
                )
            )
    with (HERE / "summary.json").open("x") as out:
        json.dump(dict(results=results, failures=failures), out, indent=2, allow_nan=False)
    for r in results:
        print(
            r["dataset"],
            r["window"],
            r["tracks"],
            "raw",
            r["raw_rx_cosine"],
            "profiled",
            r["profiled_rx_cosine"],
            "top10",
            r["top10_gross_norm_fraction"],
            "RF",
            [(b["rf_hz"] / 1e9, round(b["cosine_with_total"], 3)) for b in r["bands"]],
        )
    print("Failures", failures)


if __name__ == "__main__":
    main()
