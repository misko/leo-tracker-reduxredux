"""Exercise optimized persistence/publication on the completed native result."""

import hashlib
import json
import time
from pathlib import Path

from leo.application.localization_v3_result import publish_saved
from leo.storage import localization_v3_codec
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store

RUN = Path("/srv/bulk/leo-dev/algo07v3-publication-20261105")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    original = json.loads((RUN / "result.receipt.json").read_text())
    run_id = original["publication"]["run_id"]
    source = LocalizationV3Store(RUN / "publication").load(run_id)
    target = RUN / "inline-publication"
    target.mkdir(exist_ok=False)
    scientific, public = LocalizationV3Store(target), FastStandardAnalysisStore(target)
    began = time.perf_counter()
    saved = scientific.save(source["evidence"], source["pngs"])
    stored_at = time.perf_counter()
    manifest = publish_saved(run_id, scientific, public)
    finished = time.perf_counter()
    expected = json.loads((RUN / "codec-abba.json").read_text())
    candidate = next(row for row in expected["rows"] if row["side"] == "candidate")
    assert saved["receipt"]["result_sha256"] == "sha256:" + candidate["raw_sha256"]
    assert saved["receipt"]["result_bytes"] == candidate["bytes"]
    for name, png in source["pngs"].items():
        assert public.artifact(run_id, name) == png
    assert public.position_grid(run_id)["complete"]
    assert public.position_path(run_id)["binding"]["terminal_sha256"] == saved["sha256"]
    assert publish_saved(run_id, scientific, public) == manifest
    result = dict(
        scope="completed native scientific state to optimized archive and UI publication; no refit",
        save_seconds=stored_at - began,
        publication_seconds=finished - stored_at,
        total_seconds=finished - began,
        scientific_receipt=saved,
        publication=manifest,
        codec_sha256=digest(localization_v3_codec.__file__),
        script_sha256=digest(__file__),
        source_receipt_sha256=digest(RUN / "result.receipt.json"),
        all_pngs_exact=True,
        idempotent=True,
        native_to_publication_speedup=None,
    )
    (RUN / "inline-publication.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: result[k] for k in ("save_seconds", "publication_seconds", "total_seconds")})
    )


if __name__ == "__main__":
    main()
