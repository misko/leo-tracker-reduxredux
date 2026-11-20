"""Recover actual first-ranked and best-of-three initial fits from the sealed v5 archives."""

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .. import corpus
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km
from ..variants.v5_lean import SOURCE_SHA256
from . import prefix_figures
from .search_budget import REPORT, digest
from .v5_postfit import ARCHIVE, _map
from .v5_prefix_audit import DS29, value

CHOICES = (
    b'["audit",["map",[["initial",["map",[["status","complete"],["GPS_used",false],["choices",'
)
SELECTED = b'["selected_hypothesis",'
RANKED = "v5_initial_rank1"
STOCK = "v5_initial_best3"


def read_choices(raw):
    if raw.count(CHOICES) != 1 or raw.count(SELECTED) != 1:
        raise ValueError("expected one complete, truth-free original initial search")
    start = raw.index(CHOICES) + len(CHOICES)
    stop = raw.index(SELECTED, start)
    value, end = json.JSONDecoder().raw_decode(raw[start:stop].decode())
    if value[0] != "list" or raw[start + end : stop] != b"],":
        raise ValueError("malformed original initial search choices")
    selected, end = json.JSONDecoder().raw_decode(raw[stop + len(SELECTED) :][:48].decode())
    rows = [_map(node) for node in value[1]]
    if (
        type(selected) is not int
        or raw[stop + len(SELECTED) + end :][:2] != b"],"
        or not 0 <= selected < len(rows)
    ):
        raise ValueError("malformed selected branch")
    return rows, selected


def audit(task):
    case_id, dataset, catalog, native, center, expected, archived_arms = task
    root = ARCHIVE if dataset == "DS26" else DS29
    directory = root / f"{case_id}-r0"
    file = directory / "baseline/experimental-evidence.zip"
    receipt = json.loads((directory / "baseline-execution.json").read_bytes())
    with file.open("rb") as stream:
        checksum = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if (
        checksum != expected
        or receipt["worker"]["artifact"]["sha256"] != checksum
        or receipt["worker"]["source_sha256"] != SOURCE_SHA256
        or (receipt["role"], receipt["status"]) != ("baseline", "complete")
    ):
        raise ValueError(f"original baseline archive is unmatched for {case_id}")
    with ZipFile(file) as archive:
        raw = archive.read("values.json")
        request_tag = encoded(["request_sha256", receipt["request_sha256"]])
        if raw.count(b'["request_sha256",') != 1 or raw.count(request_tag) != 1:
            raise ValueError(f"archived request differs from its worker for {case_id}")
        choices, selected = read_choices(raw)
        del raw
        fits = [{a: _map(_map(_map(c["arms"])[a])["fit"]) for a in ARMS} for c in choices]
        centers = [value(c["center_score"], archive) for c in choices]
        losses = [value(f["c0"]["score"], archive) for f in fits]
        if (
            [c["hypothesis"] for c in choices] != list(range(len(choices)))
            or centers != sorted(centers)
            or selected != min(range(len(losses)), key=losses.__getitem__)
        ):
            raise ValueError(f"original ranking or zero-calibration winner differs for {case_id}")
        records = {}
        for method, index in ((RANKED, 0), (STOCK, selected)):
            result_arms = {}
            for arm, fit in fits[index].items():
                east, north = value(fit["parameters"], archive)
                latlon = [
                    center[0] + north / 111,
                    center[1] + east / (111.32 * np.cos(np.deg2rad(center[0]))),
                ]
                rms = value(fit["residual_rms_hz"], archive)
                if method == STOCK and (
                    distance_km(latlon, archived_arms[arm]["latlon"]) > 1e-7
                    or rms != archived_arms[arm]["conditional_rms_hz"]
                ):
                    raise ValueError(f"archived selected initial endpoint differs for {case_id}")
                result_arms[arm] = dict(latlon=latlon, rf_rms_hz=rms)
            records[method] = dict(
                id=case_id,
                method=method,
                native_sha256=native,
                catalog_sha256=catalog,
                source_archive_sha256=checksum.removeprefix("sha256:"),
                input_sha256=receipt["request_sha256"].removeprefix("sha256:"),
                result=dict(
                    status="ok",
                    boundary="Original v5 initial branch fit, before conservative recovery",
                    arms=result_arms,
                    metrics=dict(
                        cold_rank=index,
                        winning_rank=selected,
                        refined_hypotheses=len(choices),
                        center_scores=centers,
                        refreshed_c0_objectives=losses,
                    ),
                ),
            )
    return records


def generate(out, jobs):
    out = local_output(out)
    _, bound = corpus._selection("roof16")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", bound))
    prior = prefix_figures.load_rows(prefix_figures.REPORT)
    tasks = []
    for case, (ref, _, row) in sorted(prior.items()):
        item = inputs[case]
        (region,) = item["regions"]
        tasks.append(
            (
                case,
                ref["group"],
                item["catalog"]["sha256"],
                item["native"]["sha256"],
                region["center"],
                row["archive_sha256"],
                row["stages"]["initial"],
            )
        )
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(audit, tasks))
    files = {}
    table = []
    for method in (RANKED, STOCK):
        path = out / f"{method}.jsonl.gz"
        write(path, gzip.compress(b"".join(encoded(d[method]) + b"\n" for d in results), mtime=0))
        files[path.name] = digest(path)
        for pair in results:
            row = pair[method]
            ref = prior[row["id"]][0]
            for arm, endpoint in row["result"]["arms"].items():
                table.append(
                    dict(
                        method=method,
                        recording=row["id"],
                        dataset=ref["group"],
                        arm=arm,
                        winning_rank=row["result"]["metrics"]["winning_rank"],
                        position_error_km=distance_km(endpoint["latlon"], ref["truth"]),
                        conditional_rms_hz=endpoint["rf_rms_hz"],
                    )
                )
    prefix_figures.csv_file(out / "per-recording.csv", table)
    save_json(
        out / "receipt.json",
        dict(cases=sorted(prior), files=files, scientific_source=SOURCE_SHA256),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT / "initial-checkpoints")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    generate(args.out, args.jobs)
