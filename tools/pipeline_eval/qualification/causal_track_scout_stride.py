"""Run the already sealed causal tracker on two newly authenticated wide controls."""

import gzip
import json
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, save_json
from .causal_track_scout_trial import REPORT, prospective
from .input_factor_bridge import REPO, SCREEN, _sha, check, read

PARENT = SCREEN / "receiver-core/full-stride"
CASES = ("DS26-0162", "DS29-0519")


def run():
    frozen = REPORT / "source-lock.json"
    primary = read(REPORT / "prediction-lock.json")
    check(frozen, primary["source_lock_sha256"])
    pins = read(frozen)
    for rel, digest in pins["sources"].items():
        check(REPO / rel, digest)
    parent = PARENT / "prediction-lock.json"
    release = read(parent)
    names = {ident: f"native/control/{ident}.json.gz" for ident in CASES}
    paths = {ident: PARENT / name for ident, name in names.items()}
    for ident, path in paths.items():
        check(path, release["files"][names[ident]])
    lock = REPORT / "stride-source-lock.json"
    if lock.exists():
        raise ValueError("the fixed stride extension is already sealed")
    save_json(
        lock,
        dict(
            cases=list(CASES),
            primary_source_sha256=_sha(frozen),
            full_stride_prediction_sha256=_sha(parent),
            extension_sha256=_sha(Path(__file__)),
            compressed_sources={ident: _sha(path) for ident, path in paths.items()},
        ),
    )
    data = {}
    out = REPORT / "stride-proposals.jsonl.gz"
    with (
        out.open("xb") as handle,
        gzip.GzipFile(filename="", fileobj=handle, mode="wb", mtime=0, compresslevel=4) as stream,
    ):
        for ident in CASES:
            content = gzip.decompress(paths[ident].read_bytes())
            document = json.loads(content)
            data[ident] = prospective(
                ident, document, lambda row: stream.write(encoded(row) + b"\n")
            )
            data[ident]["wide_native_sha256"] = sha256(content).hexdigest()
    save_json(REPORT / "stride-timing.json", data)
    save_json(
        REPORT / "stride-prediction-lock.json",
        dict(
            cases=list(CASES),
            source_lock_sha256=_sha(lock),
            files={name: _sha(REPORT / name) for name in ("stride-timing.json", out.name)},
        ),
    )


if __name__ == "__main__":
    run()
