"""Render sealed matched studies declared by a local figures.json file."""

import gzip
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from .. import corpus
from ..__main__ import encoded
from ..position_figure import Mark
from ..scoring import (
    ARMS,
    POSITION_FAILURES,
    ROLES,
    arm_outcome,
    coordinate,
    distance_km,
    terminal_position_decision,
    validate_result,
)
from . import short_receiver_figures as shared

REPORT = corpus.REPO / "reports/2026_11_19_receiver_screening"
SPEC = "figures.json"
ROOF_SERIES = {"one", "stock", "one_native_factors", "all_visits"}
TRANSFER_SERIES = {"candidate", "stock", "one", "four"}
FORCED_SERIES = dict(
    candidate="diagnostic", stock="stock_forced", one="one_forced", four="four_forced"
)
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Chart:
    id: str
    method: str
    scope: str
    title: str
    caption: str
    cases: tuple
    references: dict
    predictions: dict
    labels: dict
    version: int = 1

    def page(self, arm):
        if self.scope == "roof":
            rows = shared._visible_marks(
                [self.references[case] for case in sorted(self.cases)],
                self.predictions["one"],
                self.method,
                arm,
                additional={k: v for k, v in self.predictions.items() if k != "one"},
            )
        else:
            rows = _transfer_marks(self.references, self.predictions, arm, version=self.version)
        return shared.Page(
            self.id,
            self.method,
            self.title,
            self.caption,
            rows,
            self.scope,
            labels=self.labels,
            show_terminal_counts=self.version == 2,
        )


def available(evidence=REPORT):
    return any(Path(evidence).rglob(SPEC))


def _local(folder, name):
    if not isinstance(name, str) or name in ("", ".", "..") or Path(name).name != name:
        raise ValueError(f"screening evidence must name a file within {folder}")
    path = folder / name
    if path.resolve().parent != folder.resolve():
        raise ValueError(f"{path} resolves outside its study directory")
    return path


def _require_keys(spec, required, optional=()):
    if not isinstance(spec, dict) or spec.keys() - set(required) - set(optional):
        raise ValueError("unexpected screening figure fields")
    if missing := set(required) - spec.keys():
        raise ValueError(f"screening figure fields are missing: {sorted(missing)}")


def _case_list(value):
    if (
        not isinstance(value, (list, tuple))
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("screening cases must be nonempty unique identifiers")
    return tuple(value)


def _cases(value, sealed):
    if value == "roof135":
        return tuple(shared._frozen_roof()[0])
    if value in ("ds26-all159", "ds26-excluded32"):
        return tuple(corpus._selection(value)[0])
    known = {"timing-six": shared.TIMING, "smoke-two": shared.SMOKE, "sealed": sealed}
    if isinstance(value, str):
        if value not in known:
            raise ValueError(f"unknown screening roster {value!r}")
        return _case_list(known[value])
    return _case_list(value)


def _sealed_bytes(folder, receipt, name):
    path = _local(folder, name)
    digest = receipt["files"].get(name)
    if not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None:
        raise ValueError(f"{path} must have a bare SHA-256 evidence seal")
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"{path} differs from its frozen content hash")
    return data


def _prediction_rows(name, data):
    if name.endswith(".jsonl.gz"):
        data = gzip.decompress(data)
    elif not name.endswith(".jsonl"):
        raise ValueError(f"{name} is not a standardized JSONL prediction archive")
    return [json.loads(line) for line in data.splitlines()]


def _checked_result(record, name, version=1):
    result = record["result"]
    validate_result(result)
    encoded(result)
    attempted = result["metrics"].get("position_attempted") is not False
    arms = result.get("arms", {})
    if (
        version == 2
        and result["status"] in POSITION_FAILURES
        and any(arm.get("forced_latlon") is not None for arm in arms.values())
    ):
        raise ValueError("a failed or missing result cannot supply a forced coordinate")
    if attempted and result["status"] in ("ok", "withheld") and set(arms) != set(ARMS):
        raise ValueError(f"{name} lacks calibration arms for {record['id']}")
    if (not attempted or result["status"] == "missing") and any(
        arm.get(k) is not None for arm in arms.values() for k in ("latlon", "forced_latlon")
    ):
        raise ValueError(f"{name} supplies a position for an unmeasured {record['id']}")
    return result


def _series(folder, receipt, cached, spec, cases, scope, version):
    _require_keys(
        spec,
        ("key", "label", "file", "value"),
        ("field", "where", "match", "native_field", "native_authority", "forced_label"),
    )
    key, name = spec["key"], spec["file"]
    keys = ROOF_SERIES if scope == "roof" else TRANSFER_SERIES
    if key not in keys or not isinstance(spec["label"], str) or not spec["label"]:
        raise ValueError(f"invalid {scope} chart series {key!r}")
    if name not in cached:
        cached[name] = _prediction_rows(name, _sealed_bytes(folder, receipt, name))
    match = {spec.get("field", "method"): spec["value"]}
    where = spec.get("where", {})
    if not isinstance(where, dict) or match.keys() & where.keys():
        raise ValueError("screening series has a conflicting selector")
    match.update(where)
    selected = [
        row
        for row in cached[name]
        if all(row.get(field) == value for field, value in match.items())
    ]
    shared._exact([row["id"] for row in selected], cases, f"{name} / {match}")
    for record in selected:
        _checked_result(record, name, version)
    return {row["id"]: row for row in selected}


@lru_cache(maxsize=1)
def _roof_authority():
    refs, frozen = shared._frozen_roof()
    return {**refs, **{row["id"]: row for row in corpus.references("ds26-all159")}}, frozen


def _roof_binding(records, spec):
    refs, frozen = _roof_authority()
    native_field = spec.get("native_field", "native_sha256")
    source = spec.get("native_authority", "frozen")
    if source == "ordinary":
        ordinary = shared._json(shared.ORDINARY / "recording-receipts.json")["recordings"]
    elif source != "frozen":
        raise ValueError(f"unknown roof native source authority {source!r}")
    for ident, row in records.items():
        if ident not in refs:
            raise ValueError(f"unknown frozen roof recording {ident}")
        reference = frozen[ident]
        if reason := reference.get("unavailable"):
            result = row["result"]
            hashes = (native_field, "native_sha256", "catalog_sha256", "input_sha256")
            worker_flags = ("attempted", "worker_attempted", "worker_returned")
            if (
                source != "frozen"
                or result["status"] != "unavailable"
                or result.get("reason") != reason
                or result["metrics"].get("position_attempted") is True
                or any(row.get(k) is True for k in worker_flags)
                or row.get("tile") not in reference["regions"]
                or any(row.get(k) is not None for k in hashes)
                or any(
                    arm.get(k) is not None
                    for arm in result.get("arms", {}).values()
                    for k in ("latlon", "forced_latlon")
                )
            ):
                raise ValueError(
                    f"{ident} must retain the frozen unavailable input and no estimate"
                )
            continue
        if source == "ordinary" and ident not in ordinary:
            raise ValueError(f"{ident} has no published ordinary native authority")
        native = (
            ordinary[ident]["native_sha256"]
            if source == "ordinary"
            else reference["native"]["sha256"]
        )
        if (
            row.get(native_field) != native
            or row.get("catalog_sha256") != reference["catalog"]["sha256"]
        ):
            raise ValueError(f"{ident} does not match frozen native and causal catalogue authority")
    return refs


def _new_roof_match(record, authority):
    if any(
        key not in record or record[key] != value for key, value in authority["bindings"].items()
    ):
        raise ValueError(
            f"{record['id']} differs from its sealed new roof capture, catalogue or tile"
        )


def new_roof_references(folder, receipt, spec, cases):
    """Resolve actual four-role v5 predictions for new recordings at a surveyed roof."""
    _require_keys(spec, ("authority", "predictions"))
    frozen, _ = _roof_authority()
    if not cases or set(cases) & frozen.keys():
        raise ValueError("fresh roof references cannot replace frozen roof recordings")
    document = json.loads(_sealed_bytes(folder, receipt, spec["authority"]))
    _require_keys(document, ("cases",))
    authority = document["cases"]
    if not isinstance(authority, list) or any(not isinstance(row, dict) for row in authority):
        raise ValueError("sealed new roof authority needs an array of recording records")
    shared._exact([row["id"] for row in authority], cases, "sealed new roof authority")
    refs = {}
    for row in authority:
        _require_keys(row, ("id", "group", "recording", "truth", "bindings"))
        ident, bindings = row["id"], row["bindings"]
        if (
            row["recording"] != ident
            or not isinstance(row["group"], str)
            or not row["group"].strip()
            or coordinate(row["truth"]) is None
            or not isinstance(bindings, dict)
            or any(
                not isinstance(bindings.get(key), str) or DIGEST.fullmatch(bindings[key]) is None
                for key in ("paired_capture_sha256", "catalog_sha256")
            )
            or not isinstance(bindings.get("tile"), dict)
            or coordinate(bindings["tile"].get("center")) is None
        ):
            raise ValueError(f"{ident} needs surveyed truth and exact new roof capture bindings")
        refs[ident] = dict(row, reference={})

    name = spec["predictions"]
    rows = _prediction_rows(name, _sealed_bytes(folder, receipt, name))
    for record in rows:
        ident, role = record["id"], record.get("method")
        if ident not in refs or role not in ROLES or role in refs[ident]["reference"]:
            raise ValueError("fresh v5 predictions must use four distinct original roles per case")
        ref = refs[ident]
        _new_roof_match(record, ref)
        if record.get("native_sha256") != ref["bindings"]["paired_capture_sha256"]:
            raise ValueError(f"fresh v5 used a different capture-era native input for {ident}")
        result = _checked_result(record, name)
        unattempted = result["metrics"].get("position_attempted") is False
        endpoints = {}
        for arm in ARMS:
            endpoint = result.get("arms", {}).get(arm, {})
            point = endpoint.get("latlon")
            state, _ = arm_outcome(result, endpoint)
            if (
                unattempted
                and state in ("ok", "withheld")
                and not terminal_position_decision(result)
            ):
                state = "stage_only"
            endpoints[arm] = dict(
                status="withheld" if state == "ok" and point is None else state,
                error_km=distance_km(point, ref["truth"]),
            )
        ref["reference"][role] = endpoints
    for ident, ref in refs.items():
        shared._exact(ref["reference"], ROLES, f"fresh original v5 roles for {ident}")
    return refs


def _transfer_binding(folder, receipt, file, cases, labels):
    queries = json.loads(_sealed_bytes(folder, receipt, file))["queries"]
    shared._exact([row["id"] for row in queries], cases, "sealed transfer queries")
    if labels is not None:
        if (
            not isinstance(labels, dict)
            or any(not isinstance(text, str) or not text for text in labels.values())
            or len(labels) != len(set(labels.values()))
        ):
            raise ValueError("transfer conditions need nonempty distinct labels")
        shared._exact(labels, {q["condition"] for q in queries}, "transfer condition labels")
        order = {condition: index for index, condition in enumerate(labels)}
        queries.sort(key=lambda query: order[query["condition"]])
    used = set()
    for query in queries:
        _require_keys(query, ("id", "condition", "recording", "truth", "bindings"), ("eligible",))
        identity = query["condition"], query["recording"]
        if not all(isinstance(key, str) and key for key in identity) or identity in used:
            raise ValueError("transfer queries must have distinct recording/condition pairs")
        used.add(identity)
        coordinate(query["truth"])
        if not isinstance(query.get("eligible", True), bool):
            raise ValueError("transfer contract eligibility must be explicit")
        if not isinstance(query["bindings"], dict) or not any(
            isinstance(digest, str) and DIGEST.fullmatch(digest) is not None
            for key, digest in query["bindings"].items()
            if key
            in (
                "input_sha256",
                "native_sha256",
                "observation_sha256",
                "document_sha256",
                "worker_input_sha256",
            )
        ):
            raise ValueError("transfer query needs a sealed observation or request digest")
    return {
        row["id"]: dict(row, condition=labels[row["condition"]]) if labels is not None else row
        for row in queries
    }


def _match_pairs(cases, candidate, paired, fields):
    if not isinstance(fields, (list, tuple)) or any(
        not isinstance(field, str) or not field for field in fields
    ):
        raise ValueError("matched series fields must be a list of row keys")
    for ident in cases:
        if any(
            candidate[ident].get(k) is None or candidate[ident][k] != paired[ident].get(k)
            for k in fields
        ):
            raise ValueError(f"screening control has an unmatched input for {ident}")


def _chart(folder, spec, version=1):
    _require_keys(
        spec,
        ("id", "method", "scope", "title", "caption", "cases", "seal", "series"),
        ("queries", "condition_labels", "provenance", "source_lock", "roof_references"),
    )
    if any(
        not isinstance(spec[key], str) or NAME.fullmatch(spec[key]) is None
        for key in ("id", "method")
    ):
        raise ValueError("screening requires safe chart and method identifiers")
    scope = spec["scope"]
    if scope not in ("roof", "transfer") or (scope == "transfer") != ("queries" in spec):
        raise ValueError("screening charts specify roof or transfer with sealed queries")
    if scope == "roof" and "condition_labels" in spec:
        raise ValueError("only transfer charts can label sealed query conditions")
    new_roof = "roof_references" in spec
    if new_roof and scope != "roof":
        raise ValueError("fresh roof references require a surveyed roof chart")
    if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ("title", "caption")):
        raise ValueError("a screening chart needs a title and measured-boundary caption")
    receipt = shared._json(_local(folder, spec["seal"]))
    sealed = _case_list(receipt["cases"])
    cases = _cases(spec["cases"], sealed)
    shared._exact(sealed, cases, "scheduled screening lock and figure cases")
    for name in spec.get("provenance", ()):
        _sealed_bytes(folder, receipt, name)
    if "source_lock" in spec:
        source = spec["source_lock"]
        _require_keys(source, ("file", "digest_key"))
        shared._verify_seal(_local(folder, source["file"]), receipt[source["digest_key"]])
    if not isinstance(spec["series"], list) or not spec["series"]:
        raise ValueError("screening chart needs prediction series")
    series, labels, cached = {}, {}, {}
    refs, fresh = {}, {}
    if scope == "transfer":
        refs = _transfer_binding(
            folder, receipt, spec["queries"], cases, spec.get("condition_labels")
        )
    elif new_roof:
        frozen, _ = _roof_authority()
        fresh = new_roof_references(
            folder,
            receipt,
            spec["roof_references"],
            [ident for ident in cases if ident not in frozen],
        )
        refs = {ident: frozen[ident] for ident in cases if ident in frozen} | fresh
    main = "one" if scope == "roof" else "candidate"
    for series_spec in spec["series"]:
        records = _series(folder, receipt, cached, series_spec, cases, scope, version)
        key = series_spec["key"]
        if key in series:
            raise ValueError("screening chart repeats a plot series key")
        if scope == "roof":
            if new_roof:
                known = {ident: row for ident, row in records.items() if ident not in fresh}
                if known:
                    _roof_binding(known, series_spec)
                for ident, reference in fresh.items():
                    _new_roof_match(records[ident], reference)
            else:
                refs = _roof_binding(records, series_spec)
        elif any(
            any(row.get(k) != value for k, value in refs[ident]["bindings"].items())
            for ident, row in records.items()
        ):
            raise ValueError("transfer result differs from its sealed query input")
        series[key] = records
        labels[key] = series_spec["label"]
        if series_spec.get("forced_label"):
            forced_key = (
                ("one_forced" if key == "one" else None) if scope == "roof" else FORCED_SERIES[key]
            )
            if forced_key is None or not isinstance(series_spec["forced_label"], str):
                raise ValueError("a forced label must name a displayed diagnostic series")
            labels[forced_key] = series_spec["forced_label"]
    if main not in series:
        raise ValueError("screening chart is missing its candidate series")
    paired_cases = cases
    if scope == "roof":
        # Missing captures already passed the explicit absence check in every series.
        authority = _roof_authority()[1]
        paired_cases = [ident for ident in cases if not authority.get(ident, {}).get("unavailable")]
    for series_spec in spec["series"]:
        if series_spec["key"] != main:
            _match_pairs(
                paired_cases, series[main], series[series_spec["key"]], series_spec.get("match", ())
            )
    return Chart(
        spec["id"],
        spec["method"],
        scope,
        spec["title"],
        spec["caption"],
        cases,
        refs,
        series,
        labels,
        version,
    )


def _transfer_marks(queries, predictions, arm, *, version=1):
    cohorts = defaultdict(list)
    for ident, query in queries.items():
        group, recording = query["condition"], query["recording"]
        for key, rows in predictions.items():
            result = rows[ident]["result"]
            endpoint = result.get("arms", {}).get(arm, {})
            point, forced = endpoint.get("latlon"), endpoint.get("forced_latlon")
            status, _ = arm_outcome(result, endpoint)
            unattempted = result["metrics"].get("position_attempted") is False
            if (
                unattempted
                and (version == 1 or status in ("ok", "withheld"))
                and not terminal_position_decision(result)
            ):
                status = "stage_only"
            if not query.get("eligible", True):
                forced = forced if forced is not None else point
                point, status = None, "unavailable"
            decision = (
                "published" if point is not None else "withheld" if status == "ok" else status
            )
            cohorts[group].append(
                Mark(group, recording, key, decision, distance_km(point, query["truth"]))
            )
            cohorts[group].append(
                Mark(
                    group,
                    recording,
                    FORCED_SERIES[key],
                    "diagnostic" if forced is not None else "no_estimate",
                    distance_km(forced, query["truth"]),
                )
            )
    return [
        row
        for rows in cohorts.values()
        for row in rows
        if row.series not in FORCED_SERIES.values()
        or any(item.series == row.series and item.decision == "diagnostic" for item in rows)
    ]


def charts(methods=None, evidence=REPORT):
    requests = set(methods or ())
    seen = set()
    selected = []
    for path in sorted(Path(evidence).rglob(SPEC)):
        descriptor = shared._json(path)
        _require_keys(descriptor, ("version", "charts"))
        version = descriptor["version"]
        if (
            type(version) is not int
            or version not in (1, 2)
            or not isinstance(descriptor["charts"], list)
        ):
            raise ValueError(f"unknown screening figure descriptor version in {path}")
        for spec in descriptor["charts"]:
            name, method = spec["id"], spec["method"]
            if name in seen:
                raise ValueError(f"duplicate screening chart ID {name!r}")
            seen.add(name)
            if not requests or requests & {name, method}:
                selected.append(_chart(path.parent, spec, version))
    if unknown := requests - {value for c in selected for value in (c.id, c.method)}:
        raise ValueError(f"screening evidence unavailable for {sorted(unknown)}")
    if not selected:
        raise ValueError("no sealed screening figure descriptors")
    return selected


def generate(out, arms=ARMS, methods=None, *, evidence=REPORT):
    """Load the evidence once and render both calibration arms from that snapshot."""
    studies = charts(methods, evidence)
    return shared.render(
        out,
        arms,
        lambda arm: [study.page(arm) for study in studies],
        title="Receiver screening position errors",
    )
