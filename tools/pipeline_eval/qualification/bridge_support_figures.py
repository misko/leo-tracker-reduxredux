"""Create one locally sealed standard chart package for each bridge cohort."""

import gzip

from tools.pipeline_eval.__main__ import encoded, read_predictions, save_json, write
from tools.pipeline_eval.qualification.bridge_support_eval import (
    CANDIDATE,
    COHORTS,
    FILES,
    PRIOR,
    REPORT,
    STOCK,
    _sha,
    read,
)

CHARTS = {
    "diagnosed": (
        "Previously diagnosed recordings",
        "Two previously diagnosed recordings with fresh matched bridge replays. "
        "Compact cavity was fresh on DS29-0082 and archived on DS26-0066.",
    ),
    "comparison": (
        "Prior favorable comparison",
        "DS26-0036 with all three methods replayed on the same CPU.",
    ),
    "confirmation": (
        "New salted roof controls",
        "Six hash-selected recordings outside development. Bridge replays share the same CPU "
        "per recording. Compact cavity endpoints are source-sealed archives.",
    ),
}


def main():
    receipt = read(REPORT / "receipt.json")
    source = REPORT / "source-lock.json"
    if _sha(source) != receipt["source_lock_sha256"] or any(
        _sha(REPORT / name) != sha for name, sha in receipt["files"].items()
    ):
        raise ValueError("staged chart evidence differs from the sealed trial")
    records = {method: read_predictions(REPORT / name) for method, name in FILES.items()}
    for cohort, cases in COHORTS.items():
        folder = REPORT / cohort
        files = {}
        for method, name in FILES.items():
            rows = [records[method][i] for i in cases]
            write(folder / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
            files[name] = _sha(folder / name)
        write(folder / source.name, source.read_bytes())
        save_json(
            folder / "receipt.json",
            dict(
                cases=cases,
                files=files,
                source_lock_sha256=receipt["source_lock_sha256"],
                parent_receipt_sha256=_sha(REPORT / "receipt.json"),
            ),
        )
        title, caption = CHARTS[cohort]
        series = []
        for method, key, label in (
            (CANDIDATE, "one", "Whole-track reclassification"),
            (PRIOR, "one_native_factors", "Prior bridge, fresh matched replay"),
            (STOCK, "stock", "Compact cavity"),
        ):
            item = dict(key=key, label=label, file=FILES[method], value=method)
            if method != CANDIDATE:
                item["match"] = ["input_sha256", "scientific_request_sha256"]
            series.append(item)
        chart = dict(
            id=f"bridge_support_{cohort}",
            method=CANDIDATE,
            scope="roof",
            title=f"Held-component bridge · {title}",
            caption=caption,
            cases=cases,
            seal="receipt.json",
            series=series,
            source_lock=dict(file=source.name, digest_key="source_lock_sha256"),
        )
        save_json(folder / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    main()
