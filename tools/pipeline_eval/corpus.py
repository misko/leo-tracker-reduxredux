"""Resolve frozen receiver inputs and load independent benchmark references.

Set PIPELINE_EVAL_BULK_ROOT to the mounted archive root and
PIPELINE_EVAL_BLIND_ROOT to the directory containing the original public trees.
"""

import csv
import hashlib
import io
import json
import os
from collections import defaultdict
from collections.abc import Iterator, Set
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZipFile

FROZEN = Path(__file__).with_name("frozen")
REPO = Path(__file__).resolve().parents[2]
DEFAULT_BULK = Path("/srv/bulk")
DEFAULT_BLIND = REPO / "reports/2026_11_18_blind_regional_receiver"
TRANSFER_SAMPLE = FROZEN / "transfer16-inputs.zip"
PANELS = ("smoke", "roof16", "ds26-common127", "ds26-all159", "ds26-excluded32", "transfer124")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_frozen(name: str, files: dict) -> bytes:
    raw = (FROZEN / name).read_bytes()
    if _sha(raw) != files[name]:
        raise ValueError(f"Frozen benchmark fixture SHA-256 mismatch for {name}")
    return raw


def _index(raw: bytes) -> dict:
    rows = map(json.loads, raw.splitlines())
    return {row["id"]: row for row in rows}


def _selection(panel: str) -> tuple[list[str], dict]:
    if panel not in PANELS:
        raise ValueError(f"Unknown benchmark panel {panel!r}. Choose from {', '.join(PANELS)}.")
    manifest = json.loads((FROZEN / "provenance.json").read_bytes())
    files = manifest["files"]
    rosters = json.loads(_read_frozen("panels.json", files))
    if panel == "ds26-excluded32":
        common = set(rosters["ds26-common127"])
        return [i for i in rosters["ds26-all159"] if i not in common], files
    return rosters[panel], files


def _optional_number(value: str) -> float | None:
    return float(value) if value else None


def _references(ids: list[str], files: dict) -> Iterator[dict]:
    targets = _index(_read_frozen("targets.jsonl", files))
    selected = set(ids)
    methods = defaultdict(dict)
    raw = _read_frozen("scores.csv", files).decode()
    for row in csv.DictReader(io.StringIO(raw)):
        if row["id"] in selected:
            method = methods[row["id"]].setdefault(row["method"], {})
            point = (
                [float(row[key]) for key in ("latitude_deg", "longitude_deg")]
                if row["latitude_deg"]
                else None
            )
            method[row["arm"]] = dict(
                status=row["status"],
                error_km=_optional_number(row["error_km"]),
                latlon=point,
                rf_rms_hz=_optional_number(row["rms_hz"]),
                matched_rf_rms_hz=_optional_number(row["matched_rms_hz"]),
                matched_observations=int(row["matched_observations"])
                if row["matched_observations"]
                else None,
                wall_s=_optional_number(row["wall_s"]),
            )
    for case_id in ids:
        yield dict(targets[case_id], reference=methods[case_id])


def references(panel: str) -> Iterator[dict]:
    """Return scorer-only records without opening any public or archived input."""
    ids, files = _selection(panel)
    yield from _references(ids, files)


def _checked(
    path: Path, expected: str, key: str, issues: dict, *, delegate_read=False
) -> Path | None:
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except FileNotFoundError:
        issues[key] = f"frozen {key} file is missing"
        return None
    except PermissionError as error:
        if delegate_read:
            issues[key] = "SHA-256 validation delegated to the read-only IQ archive reader"
            return path
        issues[key] = f"cannot read frozen {key} file ({error.strerror})"
        return None
    except OSError as error:
        issues[key] = f"cannot read frozen {key} file ({error.strerror})"
        return None
    if digest != expected:
        issues[key] = f"frozen {key} file failed SHA-256 validation"
        return None
    return path


def _locate(bulk: Path, locator: dict, key: str, issues: dict) -> Path | None:
    return _checked(bulk / locator["path"], locator["sha256"], key, issues)


def _packed(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _store(cache: Path, kind: str, raw: bytes, suffix: str = ".json") -> Path:
    root = cache.resolve() / kind
    if root.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("Receiver input cache must be outside /mnt/qnap01")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_sha(raw)}{suffix}"
    if path.is_file() and path.read_bytes() == raw:
        return path
    with NamedTemporaryFile(dir=root, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(raw)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def _portable_input(public, cache, key, digest, issues):
    folder, suffix = ("observations", ".json") if key == "observation" else ("orbits", ".tle")
    filename = digest + suffix
    external = public / folder / filename
    if external.exists():
        return _checked(external, digest, key, issues)
    try:
        with ZipFile(TRANSFER_SAMPLE) as archive:
            raw = archive.read(filename)
    except (FileNotFoundError, KeyError):
        issues[key] = f"frozen {key} file is missing"
        return None
    except (OSError, BadZipFile) as error:
        issues[key] = f"cannot read bundled {key}: {error}"
        return None
    if _sha(raw) != digest:
        issues[key] = f"bundled {key} failed SHA-256 validation"
        return None
    return _store(cache, folder, raw, suffix)


def _observation(item: dict, graph: Path, cache: Path, issues: dict) -> Path | None:
    doc = json.loads(graph.read_bytes())
    metadata = doc["metadata"]
    if (
        metadata["causal_cutoff_utc_ns"] != item["cutoff_utc_ns"]
        or metadata["run_id"] != item["run_id"]
    ):
        issues["observation"] = "frozen graph has a different capture identity"
        return None
    projection = dict(
        anchor_utc_ns=metadata["anchor_utc_ns"],
        cutoff_utc_ns=item["cutoff_utc_ns"],
        duration_s=metadata["duration_s"],
        catalog_timestamp_ns=item["catalog_timestamp_ns"],
        tracks=[
            {key: track[key] for key in ("times", "values", "receiver", "channel", "rf_hz")}
            for track in doc["tracks"]
        ],
    )
    raw = _packed(projection)
    if _sha(raw) != item["observation"]:
        issues["observation"] = "graph projection did not match the frozen observation SHA-256"
        return None
    return _store(cache, "observations", raw)


def _request(item: dict, bulk: Path, cache: Path, native: Path | None, issues: dict) -> Path | None:
    if not item.get("request") or native is None:
        issues["request"] = "no replay request with verified native input"
        return None
    path = _locate(bulk, item["request"], "request", issues)
    config = _locate(bulk, item["track_config"], "track configuration", issues)
    if path is None or config is None:
        return None
    doc = json.loads(path.read_bytes())
    job = doc["job"]
    if (
        job["evaluation_reference"] is not None
        or doc["role"] != "baseline"
        or job["identity"]["session_id"] != item["session_id"]
        or job["native_input"]["sha256"] != f"sha256:{item['native']['sha256']}"
        or job["search_center"] != item["regions"][0]["center"]
    ):
        issues["request"] = "frozen replay request does not match the blind baseline input"
        return None
    job["native_input"]["path"] = str(native)
    job["track_config"]["path"] = str(config)
    job["tle_root"] = str(bulk / Path(job["tle_root"]).relative_to(DEFAULT_BULK))
    job["output_root"] = str(cache.resolve() / "replay-output" / item["id"])
    return _store(cache, "requests", _packed(doc))


def _recording(item: dict, bulk: Path, issues: dict) -> list[dict]:
    if not item.get("recording"):
        issues["recording"] = "no frozen raw recording for this input boundary"
        return []
    segments = []
    for locator in item["recording"]["segments"]:
        path = _checked(
            bulk / locator["path"], locator["sha256"], "recording", issues, delegate_read=True
        )
        if path is None:
            return []
        segments.append(dict(path=str(path), sha256="sha256:" + locator["sha256"]))
    return segments


def _public(item: dict, bulk: Path, blind: Path, cache: Path) -> dict:
    issues = {}
    paths = {}
    for key in ("native", "graph", "catalog"):
        if isinstance(locator := item.get(key), dict):
            paths[key] = _locate(bulk, locator, key, issues)
    if tree := item.get("blind_tree"):
        public = blind / tree
        digest = item["observation"]
        paths["observation"] = _portable_input(public, cache, "observation", digest, issues)
        if not paths.get("catalog"):
            # DS29 has the identical causal catalog in both archives.
            digest = (
                item["catalog"]["sha256"] if isinstance(item["catalog"], dict) else item["catalog"]
            )
            paths["catalog"] = _portable_input(public, cache, "catalog", digest, issues)
            if paths["catalog"]:
                issues.pop("catalog", None)
    elif graph := paths.get("graph"):
        paths["observation"] = _observation(item, graph, cache, issues)
    for key in ("native", "graph", "observation", "catalog"):
        if not paths.get(key):
            issues.setdefault(
                key, item.get("unavailable", f"no frozen {key} for this input boundary")
            )
    segments = []
    if "session_id" in item:
        paths["request"] = _request(item, bulk, cache, paths.get("native"), issues)
        segments = _recording(item, bulk, issues)
    else:
        issues["recording"] = "the original four-region query supplies portable observations only"

    case = {key: item[key] for key in ("id", "panel", "regions")}
    for key in ("native", "graph", "observation", "catalog", "request"):
        case[f"{key}_path"] = str(paths[key]) if paths.get(key) else None
    case["catalog_timestamp_ns"] = item.get("catalog_timestamp_ns")
    if "session_id" in item:
        case.update(
            session_id=item["session_id"],
            run_id=item["run_id"],
            cutoff_utc_ns=item.get("cutoff_utc_ns"),
            native_sha256="sha256:" + item["native"]["sha256"] if "native" in item else None,
            recording_path=segments[0]["path"] if segments else None,
            recording_sha256=segments[0]["sha256"] if segments else None,
            iq_recording_dir=str(Path(segments[0]["path"]).parents[1]) if segments else None,
            recording_segments=segments,
            recording_window_count=item["recording"]["window_count"] if segments else None,
        )
    case["input_issues"] = issues
    return case


def cases(panel: str, cache: Path, only: Set[str] | None = None) -> Iterator[tuple[dict, dict]]:
    """Yield public inputs and separate scorer records for a fixed panel."""
    ids, files = _selection(panel)
    if only is not None:
        ids = [case_id for case_id in ids if case_id in only]
    inputs = _index(_read_frozen("inputs.jsonl", files))
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", DEFAULT_BULK)).resolve()
    blind = Path(os.environ.get("PIPELINE_EVAL_BLIND_ROOT", DEFAULT_BLIND)).resolve()
    for reference in _references(ids, files):
        yield _public(inputs[reference["id"]], bulk, blind, cache), reference
