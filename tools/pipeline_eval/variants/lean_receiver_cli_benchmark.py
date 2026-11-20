"""Bind the standard scorer to public, complete native GLRT capture inputs."""

import os
from pathlib import Path

from .. import corpus
from . import lean_receiver_cli as lean

LOCATORS = dict(native="native", catalogue="catalog", track_config="track_config")


def project(item, bulk):
    ident = item["id"]
    if (
        any(not isinstance(item.get(key), dict) for key in LOCATORS.values())
        or not item.get("recording", {}).get("window_count")
        or not item.get("cutoff_utc_ns")
        or not item.get("catalog_timestamp_ns")
        or len(item.get("regions", ())) != 1
    ):
        return dict(
            id=ident, unsupported="complete native GLRT, track policy and one tile required"
        )
    issues = {}
    paths = {key: corpus._locate(bulk, item[field], key, issues) for key, field in LOCATORS.items()}
    if issues:
        return dict(id=ident, unsupported=", ".join(issues.values()))
    try:
        capture = lean.capture_anchor(paths["native"])
    except (OSError, ValueError, KeyError) as exc:
        return dict(id=ident, unsupported=f"unavailable native capture clock: {exc}")
    return dict(
        id=ident,
        files={key: str(path) for key, path in paths.items()},
        expected={key: item[field]["sha256"] for key, field in LOCATORS.items()},
        capture=capture,
        cutoff=item["cutoff_utc_ns"],
        catalogue_acquired=item["catalog_timestamp_ns"],
        offer=item["regions"][0],
        probe_limit=2 * item["recording"]["window_count"],
    )


def cases(panel, ids):
    roster, authority = corpus._selection(panel)
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", authority))
    if not set(ids) <= set(roster):
        raise ValueError("native adapter cannot expose cases outside the selected corpus")
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK)).resolve()
    return [project(inputs[ident], bulk) for ident in ids]


def run(case, solver):
    if "unsupported" in case:
        return lean.failed("unavailable", case["unsupported"])["result"]
    req = {key: value for key, value in case.items() if key != "id"}
    receipt = lean.solve(**req, solver=solver)
    result = receipt.pop("result")
    result["input_binding"] = dict(
        input_sha256=receipt["input_sha256"],
        native_sha256=receipt["input_files_sha256"]["native"],
        catalog_sha256=receipt["input_files_sha256"]["catalogue"],
        track_config_sha256=receipt["input_files_sha256"]["track_config"],
        cutoff_utc_ns=receipt["cutoff_utc_ns"],
        capture_utc_ns=receipt["capture_utc_ns"],
        catalogue_acquired_utc_ns=receipt["catalogue_acquired_utc_ns"],
        tile=receipt["offer"],
    )
    result["metrics"]["portable_worker"] = receipt
    return result
