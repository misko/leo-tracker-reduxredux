"""Build one matched CDF and position-dot figure per receiver, from saved measurements."""

import csv
import gzip
import hashlib
import io
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from . import corpus
from .__main__ import encoded, read_predictions, references, write
from .position_figure import (
    COLD_START_LABELS,
    DETECTOR_FIT_LABELS,
    MEMORY_LABELS,
    PARTIAL_IQ_CAPTION,
    RX0_FACTOR_LABELS,
    TITLES,
    Mark,
    best_guess_field,
    draw,
    marks,
    run_caption,
    save_png,
)
from .scoring import distribution, validate_result

REPORT = Path(__file__).resolve().parents[2] / "reports/2026_11_18_pipeline_eval"
RAW_RECEIVERS = {"glrt_batch", "glrt_cascade", "iq_stream", "iq_position"}
DESCRIPTIONS = {
    "v5_lean": "Both v5 numerical arms rerun from native detections on the original single tile.",
    "glrt_batch": "Batched Python GLRT, tracking and position search on 80 windows per recording.",
    "glrt_cascade": (
        "Screened Python GLRT, then tracking and position search on 80 windows per recording."
    ),
    "iq_stream": (
        "The streamed reader supplies the same 80 windows to the native GLRT, tracker "
        "and solver used for bounded raw-IQ replay."
    ),
    "iq_position": "Native GLRT, tracking and position search on 80 IQ windows per recording.",
    "orbit_interp": "Reuse orbital states across the original single-tile and four-tile searches.",
    "shape_score": "Screen below-horizon satellites before fitting the measured Doppler tracks.",
    "track_reduce": "Compress the measured Doppler tracks before single-tile and four-tile search.",
    "track_link": "Link native GLRT peaks with a causal tracker, then run the regional solver.",
    "projected_fit": "Remove per-track frequency offsets before estimating receiver position.",
}
TEN = tuple(name for name in TITLES if name in DESCRIPTIONS)
CHANNELS = {
    "glrt_odd_channels": (
        "Keep all visits to RF channels 1, 3, 5 and 7. Rebuild tracks and fit both "
        "v5 positions through the cavity stage."
    ),
    "glrt_even_channels": (
        "Keep all visits to RF channels 2, 4, 6 and 8. Rebuild tracks and fit both "
        "v5 positions through the cavity stage."
    ),
}
STREAMING_REPORT = REPORT.parent / "2026_11_19_receiver_streaming"
STREAMING = {
    "sweep_schedule": (
        "sweep/positions.jsonl.gz",
        "Observe alternate complete eight-channel sweeps. Rebuild the tracks and fit both "
        "positions using the same orbital search and cavity solver.",
    ),
    "arc_validation": (
        None,
        "Fit the first two thirds of each measured Doppler track. Test its remaining samples "
        "before publishing a position on the original one- and four-region offers.",
    ),
    "compact_finish": (
        "finish/compact_finish.jsonl",
        "Full-channel detections, compact orbital projection and final v5 repairs. Two smoke "
        "recordings plus two DS26 cases selected to exercise different repairs.",
    ),
    "catalogue_checksum": (
        "catalogue/positions.jsonl.gz",
        "Replace the orbital element checksum inside a fresh full numerical v5 fit. "
        "Both recordings start from capture-era detector output.",
    ),
    "pilot_kernel": (
        "pilot/positions.jsonl.gz",
        "Eight scheduled IQ windows per recording use the modified pilot detector. The "
        "remaining detections come from the archive. The compact v5 cavity solver runs again.",
    ),
    "native_geometry": (
        "native-geometry/positions.jsonl.gz",
        "Two 20 ms IQ windows per recording were tested with the wideband native detector. "
        "This trial measured its detector outputs and CPU time only.",
    ),
}
FRONTEND_REPORT = REPORT.parent / "2026_11_19_receiver_frontend"
FRONTEND = {
    "native-to-v5": (
        "ordinary/positions.jsonl.gz",
        "All eligible IQ windows on both physical inputs, followed by the full numerical v5 fit. "
        "The six preselected timing recordings use their original clock and capture exclusions.",
    ),
    "native_winner": (
        "winner/positions.jsonl.gz",
        "Apply the fixed 0.060 gate to fractional candidates from the six complete ordinary "
        "native factor sets, then rerun the full numerical v5 fit.",
    ),
    "single_rx0": (
        "single/full-positions.jsonl.gz",
        "Replay all eligible IQ windows through a detector context with only the physical RX0 "
        "input, then run the full numerical v5 fit. The source archive contains both lanes.",
    ),
    "single_rx0_factors": (
        "single/archive-positions.jsonl.gz",
        "Keep the RX0 slot in two complete archived factor sets per recording, one capture-era "
        "and one ordinary native. Run full numerical v5 on each source separately.",
    ),
    "pilot_confirmation": (
        "confirmation/positions.jsonl.gz",
        "Measure late pilot evidence on sampled IQ visits after ordinary fractional GLRT.",
    ),
    "spectral_grid": (
        "spectral/positions.jsonl.gz",
        "Measure a shared sliding-tone coarse search on fixed samples of authenticated IQ visits.",
    ),
    "off_region_test": (
        "regions/predictions.jsonl.gz",
        "Longitude controls on the eight DS29 blind-panel recordings with the correct region "
        "among four offers. This trial did not test DS26 or single-region queries.",
    ),
}
EXTENDED = (
    "native-to-v5",
    *(m for m in TITLES if m.startswith("v5_stop_")),
    "v5_core",
    "shared_doppler",
    "anchor_receiver",
    *CHANNELS,
    "orbit_projector",
    *(m for m in TITLES if m.startswith("early_")),
    *STREAMING,
    *(m for m in FRONTEND if m != "native-to-v5"),
)
FRONTEND_METHODS = (*TEN, *EXTENDED)
COLD_START_REPORT = REPORT.parent / "2026_11_19_glrt_cold_start"
COLD_START = {
    "point_votes": "point-votes",
    "rate_triplets": "rate-triplets",
    "folded_doppler": "folded-doppler",
}
COLD_START_MODES = ("global", "matched-tile")
COLD_START_CAPTION = (
    "Use complete GLRT candidates and causal TLEs on {cohort} recordings. "
    "Global search spans Earth. The supplied search uses v5’s original 25 km tile."
)
MEMORY_STUDIES = {
    "v5_batched_salvage": (
        "memory",
        "the finish that batches the conservative salvage likelihood",
    ),
    "v5_catalogue_memory": (
        "catalogue-memory",
        "the finish that batches catalogue propagation to ECEF",
    ),
}
MEMORY_FILES = ("positions.jsonl.gz", "stock-positions.jsonl.gz", "receipt.json")
SHARED_REPORT = REPORT.parent / "2026_11_19_shared_receiver"
DUTY_REPORT = REPORT.parent / "2026_11_19_receiver_duty"


@dataclass
class Page:
    name: str
    method: str
    subtitle: str
    rows: list[Mark]


def _offer_digests():
    frozen = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())
    _, hashes = corpus._selection("roof16")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    out = {}
    for case, trial in frozen.items():
        single = inputs[case]
        if (
            single["observation"] != trial["observation_sha256"]
            or single["catalog"]["sha256"] != trial["catalog_sha256"]
        ):
            raise ValueError(f"{case} differs from its frozen four-region inputs")
        for mode, regions in (("one", single["regions"]), ("four", trial["regions"])):
            if len(regions) != {"one": 1, "four": 4}[mode]:
                raise ValueError(f"wrong number of {mode} region offers for {case}")
            out[case, mode] = hashlib.sha256(encoded(regions)).hexdigest()
    return out


def _supplement(filename, offers, evidence=None):
    records = {}
    with gzip.open((evidence or REPORT / "evidence") / filename, "rt") as stream:
        for row in map(json.loads, stream):
            group = records.setdefault((row["method"], row["offers"]), {})
            if row["id"] in group:
                raise ValueError(f"duplicate supplemental recording in {filename}")
            if offers.get((row["id"], row["offers"])) != row["regions_sha256"]:
                raise ValueError(f"{row['id']} used different region offers in {filename}")
            validate_result(row["result"])
            group[row["id"]] = row
    return records


def _complete(records, refs):
    if set(records) != {r["id"] for r in refs}:
        raise ValueError("saved measurements do not cover the requested recording roster")
    return records


def _roof16(arm, selected, offers, evidence):
    refs = references("roof16", None)[1]
    raw, four = {}, {}
    if set(selected) & RAW_RECEIVERS:
        raw = _supplement("roof16-frontend-positions.jsonl.gz", offers, evidence)
    if set(selected) - RAW_RECEIVERS - {"v5_lean"}:
        four = _supplement("roof16-four-region.jsonl.gz", offers, evidence)
    pages = []
    for method in selected:
        path = REPORT / "predictions/roof16" / (method + ".jsonl.gz")
        multi = None
        if method in RAW_RECEIVERS:
            source, single = raw, raw[method, "one"]
        else:
            source, single = four, four.get((method, "one"))
        if single is None:
            single = read_predictions(path)
        if method != "v5_lean":
            multi = _complete(source[method, "four"], refs)
        rows = marks(refs, _complete(single, refs), multi, method, arm)
        pages.append(Page(method, method, DESCRIPTIONS[method], rows))
    return pages


def _matched135(arm, small, offers, evidence):
    ds26 = references("ds26-common127", None)[1]
    regional = {"orbit_interp", "projected_fit"}
    data = {}
    pages = []
    for page in small:
        method = page.method
        right = [m for m in page.rows if m.dataset == "DS29"]
        note = DESCRIPTIONS[method]
        if method == "v5_lean":
            with gzip.open(REPORT / "evidence/v5-postfit-127.json.gz", "rt") as stream:
                archived = [r for r in json.load(stream)["scored_rows"] if r["arm"] == arm]
            errors = _complete({r["id"]: r["error_km"] for r in archived}, ds26)
            if len(archived) != len(errors) or any(e is None for e in errors.values()):
                raise ValueError("expected one returned endpoint for every archived v5 fit")
            left = [
                replace(m, decision="published", error_km=errors[m.recording])
                if m.series == "one"
                else m
                for m in marks(ds26, {}, None, method, arm)
            ]
            note = (
                "DS26 extracts coordinates from the archived numerical fits. "
                "DS29 reruns the full fit from detector outputs."
            )
        else:
            if method in regional:
                filename = "ds26-common127-four-region.jsonl.gz"
            elif method in RAW_RECEIVERS:
                filename = "ds26-common127-frontend-positions.jsonl.gz"
            else:
                filename = "ds26-common127-regional-positions.jsonl.gz"
            if filename not in data:
                data[filename] = _supplement(filename, offers, evidence)
            full = data[filename]
            if method in regional and (method, "one") not in full:
                one = read_predictions(
                    REPORT / "predictions/ds26-common127" / (method + ".jsonl.gz")
                )
            else:
                one = full[method, "one"]
            left = marks(
                ds26, _complete(one, ds26), _complete(full[method, "four"], ds26), method, arm
            )
        pages.append(Page(method, method, note, left + right))
    return pages


def _complete_recordings(arm, evidence=None):
    smoke = references("smoke", None)[1]
    whole = {}
    for r in smoke:
        file = (evidence or REPORT / "evidence") / "full-iq" / r["id"] / "prediction.jsonl"
        whole.update(read_predictions(file))
    return Page(
        "native-to-v5",
        "native-to-v5",
        "All eligible IQ windows in two five-minute recordings, followed by the original v5 fit.",
        marks(smoke, _complete(whole, smoke), None, "native-to-v5", arm),
    )


def _common_roof():
    ds26 = references("ds26-common127", None)[1]
    ds29 = [r for r in references("roof16", None)[1] if r["group"] == "DS29"]
    return ds26 + ds29


def _duty_pages(arm, selected, directory):
    from .qualification.duty_results import measurements
    from .qualification.prefix_figures import TIMING_IDS

    refs = _common_roof()
    pages = []
    if channels := [m for m in selected if m in CHANNELS]:
        paired = measurements(directory)
        timing_refs = [r for r in refs if r["id"] in TIMING_IDS]
        for method in channels:
            predictions = {case: paired[case, method] for case in TIMING_IDS}
            rows = marks(timing_refs, _complete(predictions, timing_refs), None, method, arm)
            pages.append(Page(method, method, CHANNELS[method], rows))
    if "orbit_projector" in selected:
        method = "orbit_projector"
        predictions = read_predictions(directory / "projector-roof.jsonl.gz")
        rows = marks(refs, _complete(predictions, refs), None, method, arm)
        pages.append(
            Page(
                method,
                method,
                "All eight channels, from archived native detections to a fresh v5 cavity fit. "
                "Project Doppler directly from the causal orbit knots.",
                rows,
            )
        )
    return pages


def _streaming_pages(arm, selected, directory):
    from .qualification.prefix_figures import TIMING_IDS

    full = _common_roof()
    smoke = references("smoke", None)[1]
    pages = []
    for method in selected:
        filename, subtitle = STREAMING[method]
        if method == "arc_validation":
            refs, offers = full, _offer_digests()
            single, multi = {}, {}
            for dataset, path in (("DS26", "ds26-roof.jsonl.gz"), ("DS29", "roof16.jsonl.gz")):
                sets = _supplement(path, offers, directory / "field")
                for mode, records in (("one", single), ("four", multi)):
                    records.update(
                        {
                            r["id"]: sets[method, mode][r["id"]]
                            for r in refs
                            if r["group"] == dataset
                        }
                    )
            rows = marks(refs, _complete(single, refs), _complete(multi, refs), method, arm)
        else:
            refs = smoke
            if method == "sweep_schedule":
                refs = [r for r in full if r["id"] in TIMING_IDS]
            elif method == "compact_finish":
                cases = {"DS26-0002", "DS26-0036", "DS26-0066", "DS29-0082"}
                refs = [r for r in full if r["id"] in cases]
            records = _complete(read_predictions(directory / filename), refs)
            if any(r.get("method", method) != method for r in records.values()):
                raise ValueError(f"{filename} contains predictions for a different modification")
            rows = marks(refs, records, None, method, arm)
        pages.append(Page(method, method, subtitle, rows))
    return pages


def _off_region_roof(path):
    from .qualification.transfer_figures import _longitude_evidence

    refs = [r for r in references("roof16", None)[1] if r["group"] == "DS29"]
    queries = [
        r
        for r in references("transfer124", None)[1]
        if r["group"] == "DS29" and r["condition"] == "present"
    ]
    by_recording = {r["recording"]: r for r in queries}
    if not len(refs) == len(queries) == len(by_recording) == 8 or set(by_recording) != {
        r["recording"] for r in refs
    }:
        raise ValueError("expected the eight DS29 roof recordings with correct regions offered")
    ids, hashes = corpus._selection("transfer124")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    offers = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())
    sealed = _longitude_evidence(path)["transfer124"]
    if sealed.keys() != set(ids):
        raise ValueError("longitude predictions differ from the frozen transfer query IDs")

    records = {}
    for ref in refs:
        recording = ref["recording"]
        query = by_recording[recording]
        prediction = sealed[query["id"]]
        transfer = inputs[query["id"]]
        roof = inputs[ref["id"]]
        offer = offers[ref["id"]]
        result = prediction["results"]["off_region_test"]
        tile_ids = {tile["id"] for tile in offer["regions"]}
        if (
            ref["truth"] != query["truth"]
            or len(offer["regions"]) != 4
            or len(tile_ids) != 4
            or offer["regions"] != transfer["regions"]
            or result["metrics"]["regional_scores"].keys() != tile_ids
        ):
            raise ValueError(f"longitude recording or four-region offers differ for {recording}")
        for key, roof_digest in (
            ("observation", roof["observation"]),
            ("catalog", roof["catalog"]["sha256"]),
        ):
            field = key + "_sha256"
            if not (prediction[field] == transfer[key] == offer[field] == roof_digest):
                raise ValueError(f"longitude {key} digest differs for {recording}")
        records[ref["id"]] = {"result": result}
    return refs, records


def _frontend_pages(arm, selected, directory):
    from .qualification.prefix_figures import TIMING_IDS

    full = _common_roof()
    timing = [r for r in full if r["id"] in TIMING_IDS]
    smoke = references("smoke", None)[1]
    pages = []
    for method in selected:
        filename, subtitle = FRONTEND[method]
        if method == "off_region_test":
            refs, records = _off_region_roof(directory / filename)
            pages.append(Page(method, method, subtitle, marks(refs, None, records, method, arm)))
            continue
        refs = timing if method in ("native-to-v5", "native_winner") else smoke
        records = _complete(read_predictions(directory / filename), refs)
        if any(r.get("method", method) != method for r in records.values()):
            raise ValueError(f"{filename} contains predictions for a different modification")
        if method == "single_rx0" and any(
            r.get("variant") != "fresh-native-rx0" for r in records.values()
        ):
            raise ValueError("full RX0 replay evidence must start from raw IQ")
        ordinary = None
        if method == "single_rx0_factors":
            ordinary = _complete(
                read_predictions(directory / "single/ordinary-factor-positions.jsonl.gz"), refs
            )
            for source, factor_rows in (
                ("capture-era-rx0", records),
                ("ordinary-native-rx0", ordinary),
            ):
                if any(r.get("variant") != source for r in factor_rows.values()):
                    raise ValueError(f"RX0 factor evidence must come from {source}")
        if method not in ("pilot_confirmation", "spectral_grid"):
            for record in [*records.values(), *(ordinary or {}).values()]:
                result = record["result"]
                if result["status"] in ("ok", "withheld") and (
                    "arms" not in result or result["metrics"].get("position_attempted") is False
                ):
                    raise ValueError(f"{method} requires a position attempt for {record['id']}")
        modes = {"one_native_factors": ordinary} if ordinary is not None else None
        rows = marks(refs, records, None, method, arm, additional_modes=modes)
        if method == "pilot_confirmation" and all(
            m.decision == "stage_only" for m in rows if m.series == "one"
        ):
            subtitle += " The detector gate did not advance to position fitting."
        pages.append(Page(method, method, subtitle, rows))
    return pages


def _cold_start_pages(arm, selected, directory):
    from .qualification.prefix_figures import TIMING_IDS

    timing = [r for r in _common_roof() if r["id"] in TIMING_IDS]
    smoke = references("smoke", None)[1]
    smoke_ids = {r["id"] for r in smoke}
    _, hashes = corpus._selection("roof16")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    pages = []
    for method in selected:
        folder = directory / COLD_START[method]
        receipts = {mode: folder / f"{mode}.jsonl.gz" for mode in COLD_START_MODES}
        predictions = {mode: read_predictions(path) for mode, path in receipts.items()}
        reduced = method == "folded_doppler" and predictions["global"].keys() == smoke_ids
        refs = smoke if reduced else timing
        lock = folder / "prediction-lock.json"
        if lock.is_file():
            seal = json.loads(lock.read_bytes())
            if len(seal["cases"]) != len(refs) or set(seal["cases"]) != {r["id"] for r in refs}:
                raise ValueError(f"{folder} prediction seal differs from its recording roster")
            for path in receipts.values():
                if hashlib.sha256(path.read_bytes()).hexdigest() != seal["files"].get(path.name):
                    raise ValueError(f"{path} differs from its prediction seal")
        for mode, records in predictions.items():
            _complete(records, refs)
            path = receipts[mode]
            for case, record in records.items():
                if (record.get("method"), record.get("mode")) != (method, mode):
                    raise ValueError(f"{path} contains a different receiver or search mode")
                result = record["result"]
                complete = result["status"] in ("ok", "withheld")
                for field in ("native", "catalog"):
                    digest = record.get(field + "_sha256")
                    if (complete or digest is not None) and digest != inputs[case][field]["sha256"]:
                        raise ValueError(f"{path} has unmatched {field} input for {case}")
                if complete and "arms" not in result:
                    raise ValueError(f"{path} has no paired position arms for {case}")
        rows = marks(
            refs,
            predictions["matched-tile"],
            None,
            method,
            arm,
            additional_modes={"global": predictions["global"]},
            diagnostic_modes=("global", "one"),
        )
        caption = COLD_START_CAPTION.format(cohort="two smoke" if reduced else "six timing")
        pages.append(Page(method, method, caption, rows))
    return pages


def paired_finish_page(arm, method, directory, subtitle, expected_cases=None):
    receipt = json.loads((directory / "receipt.json").read_bytes())
    cases = receipt["cases"] if "cases" in receipt else [receipt["case"]]
    refs = [r for r in _common_roof() if r["id"] in cases]
    if len(cases) != len(refs) or len(refs) not in (1, 2):
        raise ValueError("the paired memory trial must identify one or two roof recordings")
    if expected_cases is not None and set(cases) != set(expected_cases):
        raise ValueError("the paired finish trial uses a different recording roster")
    results = {}
    for name, run, receiver in zip(
        MEMORY_FILES[:2], ("candidate", "control"), (method, "compact_finish"), strict=True
    ):
        path = directory / name
        expected = receipt["runs"][run]["position_sha256"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"memory trial position seal differs for {path.name}")
        records = read_predictions(path)
        _complete(records, refs)
        if any(r.get("method") != receiver for r in records.values()):
            raise ValueError("memory trial receipt contains an unmatched receiver")
        results[run] = records
    for case in cases:
        candidate = results["candidate"][case].get("input_sha256")
        control = results["control"][case].get("input_sha256")
        bound = receipt.get("input_sha256", candidate)
        if isinstance(bound, dict):
            bound = bound.get(case)
        if not candidate or candidate != control or candidate != bound:
            raise ValueError(f"memory trial inputs differ for {case}")
    return Page(
        method,
        method,
        subtitle,
        marks(
            refs,
            results["candidate"],
            None,
            method,
            arm,
            additional_modes={"stock": results["control"]},
        ),
    )


def _memory_page(arm, method, directory):
    folder, difference = MEMORY_STUDIES[method]
    return paired_finish_page(
        arm,
        method,
        directory / folder,
        "Full compact v5 fits from the same stored GLRT detections. Compare the stock finish "
        f"with {difference}.",
    )


def bundled(arm, selected, additional=False, panel="matched135", evidence=None):
    offers = _offer_digests()
    small = _roof16(arm, selected, offers, evidence)
    if panel == "roof16" and not additional:
        return small, []
    full = _matched135(arm, small, offers, evidence)
    if panel == "matched135":
        pages, other, suffix = full, small, "-roof16"
    elif panel == "roof16":
        pages, other, suffix = small, full, "-matched135"
    else:
        raise ValueError("choose matched135 or roof16 for the published measurements")
    extra = []
    if additional:
        extra = [replace(page, name=page.name + suffix) for page in other]
        extra.append(_complete_recordings(arm))
    return pages, extra


def live_pages(root, panel, arm, methods):
    return live_pages_by_arm(root, panel, (arm,), methods)[arm]


def live_pages_by_arm(root, panel, arms, methods):
    refs = references(panel, None)[1]
    panel_ids = {r["id"] for r in refs}
    directory = root / panel
    candidates = methods or sorted(p.name for p in directory.iterdir() if p.is_dir())

    def saved_predictions(folder):
        for location in (folder / "current", folder):
            location = location.resolve()
            path = location / "predictions.jsonl"
            if path.is_file():
                return path.resolve()
            if (location / "summary.json").is_file():
                raise ValueError(f"missing predictions for completed run in {location}")
        return None

    def outcome(record, method):
        result = record.get("result", {})
        endpoints = {}
        for name, endpoint in result.get("arms", {}).items():
            fix = endpoint["latlon"]
            field = best_guess_field(method, endpoint)
            if fix is not None or field is not None:
                endpoints[name] = (fix, field is not None, endpoint.get(field))
        position_unattempted = result.get("metrics", {}).get("position_attempted") is False
        return result.get("status", "missing"), endpoints, position_unattempted

    pages = {arm: [] for arm in arms}
    for method in candidates:
        if Path(method).name != method or method in (".", ".."):
            raise ValueError("variant must be a single directory name")
        folder = directory / method
        full = saved_predictions(folder)
        generations = (
            [(folder, full)]
            if full
            else [
                (subset, path)
                for subset in sorted(folder.glob("subset-*"))
                if (path := saved_predictions(subset)) is not None
            ]
        )
        if not generations:
            if methods:
                raise ValueError(f"no finished {panel} predictions for {method}")
            continue

        attempts, records, digests = {}, {}, set()
        for generation, path in generations:
            ids = panel_ids
            summary_path = path.with_name("summary.json")
            if summary_path.is_file():
                summary = json.loads(summary_path.read_bytes())
                if not isinstance(summary, dict) or (
                    summary.get("panel"),
                    summary.get("method"),
                ) != (panel, method):
                    raise ValueError(f"wrong panel or method in {summary_path}")
                declared = summary.get("ids")
                if not isinstance(declared, list) or not all(isinstance(k, str) for k in declared):
                    raise ValueError(f"invalid recording roster in {summary_path}")
                ids = set(declared)
                if not ids or len(ids) != len(declared) or not ids <= panel_ids:
                    raise ValueError(f"invalid recording roster in {summary_path}")
                if full and ids != panel_ids:
                    raise ValueError(f"full run roster differs from {panel} in {summary_path}")
                run = summary.get("run")
                digest = run.get("implementation_sha256") if isinstance(run, dict) else None
                if isinstance(digest, str):
                    digests.add(digest)
            elif not full:
                raise ValueError(f"missing completion summary for {generation}")

            submitted = read_predictions(path)
            if extra := submitted.keys() - ids:
                raise ValueError(f"prediction outside the declared roster in {path}: {min(extra)}")
            for case in sorted(ids):
                record = submitted.get(case, {})
                decision = outcome(record, method)
                if case in attempts:
                    previous, previous_generation = attempts[case]
                    if previous != decision:
                        raise ValueError(
                            f"conflicting outcomes for {case} in {previous_generation} and "
                            f"{generation}. Plot the subsets from separate run roots."
                        )
                    continue
                attempts[case] = (decision, generation)
                if record:
                    records[case] = record

        selected = [ref for ref in refs if ref["id"] in attempts]
        coverage = ""
        if not full:
            source = "completed subsets" if len(generations) > 1 else "a completed subset"
            coverage = f" {len(selected)}/{len(refs)} panel recordings from {source}."
            if len(digests) > 1:
                coverage += " Implementation digests differ."
        for arm, book in pages.items():
            rows = marks(selected, records, None, method, arm)
            book.append(Page(method, method, run_caption(rows, method) + coverage, rows))
    if not any(pages.values()):
        raise ValueError("no completed roof receiver runs to plot")
    return pages


def published_pages(arm, selected, evidence=None):
    """Use each published modification's measured roster and receiver boundary."""
    from .qualification import embedded_figures, prefix_figures

    cold_directory = evidence or COLD_START_REPORT
    if not selected:
        selected = list(FRONTEND_METHODS)
        available = [
            method
            for method, folder in COLD_START.items()
            if all(
                (cold_directory / folder / f"{mode}.jsonl.gz").is_file()
                for mode in COLD_START_MODES
            )
        ]
        if {"point_votes", "rate_triplets"} <= set(available):
            selected.extend(available)
            for method, (folder, _) in MEMORY_STUDIES.items():
                if all((cold_directory / folder / name).is_file() for name in MEMORY_FILES):
                    candidates = read_predictions(cold_directory / folder / "positions.jsonl.gz")
                    if any(
                        r["result"]["metrics"].get("position_attempted") is not False
                        for r in candidates.values()
                    ):
                        selected.append(method)
    if unknown := set(selected) - set(FRONTEND_METHODS) - set(COLD_START) - set(MEMORY_STUDIES):
        raise ValueError(f"unknown published modifications: {sorted(unknown)}")
    earlier = [m for m in selected if m in TEN]
    pages = bundled(arm, earlier, evidence=evidence)[0] if earlier else []
    if any(m == "v5_core" or m.startswith("v5_stop_") for m in selected):
        directory = evidence or prefix_figures.REPORT
        cases = prefix_figures.load_rows(directory)
        fresh, _ = prefix_figures.fresh_pairs(directory / "paired.jsonl.gz", cases)
        pages.extend(
            p for p in prefix_figures.checkpoint_pages(cases, fresh, arm) if p.name in selected
        )
    directory = evidence or SHARED_REPORT
    if "shared_doppler" in selected:
        method = "shared_doppler"
        ds26 = references("ds26-common127", None)[1]
        roof = references("roof16", None)[1]
        refs = ds26 + [r for r in roof if r["group"] == "DS29"]
        offers = _offer_digests()
        four_ds26 = _supplement("ds26-four-offers.jsonl.gz", offers, directory)[method, "four"]
        four_roof = _supplement("roof16-four-offers.jsonl.gz", offers, directory)[method, "four"]
        _complete(four_ds26, ds26)
        _complete(four_roof, roof)
        multi = {**four_ds26, **{r["id"]: four_roof[r["id"]] for r in roof if r["group"] == "DS29"}}
        single = _complete(read_predictions(directory / "single-tile.jsonl.gz"), refs)
        pages.append(
            Page(
                method,
                method,
                "Shared receiver clocks and satellite timing corrections on the original "
                "one- and four-region offers.",
                marks(refs, single, _complete(multi, refs), method, arm),
            )
        )
    if "anchor_receiver" in selected:
        method = "anchor_receiver"
        refs = references("smoke", None)[1]
        records = _complete(read_predictions(directory / "partial-iq-position.jsonl.gz"), refs)
        pages.append(
            Page(
                method,
                method,
                PARTIAL_IQ_CAPTION,
                marks(refs, records, None, method, arm),
            )
        )
    if any(m in CHANNELS or m == "orbit_projector" for m in selected):
        pages.extend(_duty_pages(arm, selected, evidence or DUTY_REPORT))
    if early := [m for m in selected if m in embedded_figures.TITLES]:
        pages.extend(embedded_figures.pages(arm, early, evidence))
    if latest := [m for m in selected if m in STREAMING]:
        pages.extend(_streaming_pages(arm, latest, evidence or STREAMING_REPORT))
    if frontend := [m for m in selected if m in FRONTEND]:
        pages.extend(_frontend_pages(arm, frontend, evidence or FRONTEND_REPORT))
    if cold := [m for m in selected if m in COLD_START]:
        pages.extend(_cold_start_pages(arm, cold, cold_directory))
    pages.extend(_memory_page(arm, m, cold_directory) for m in selected if m in MEMORY_STUDIES)
    order = {m: i for i, m in enumerate(selected)}
    return sorted(pages, key=lambda p: order[p.name])


def write_book(pages, destination, name, arm, *, images=True):
    pdf = io.BytesIO()
    metadata = dict(Title="Matched roof position errors", CreationDate=None, ModDate=None)
    with PdfPages(pdf, metadata=metadata) as book:
        for page in pages:
            fig = draw(page.rows, page.method, arm, page.subtitle)
            try:
                if images:
                    save_png(fig, destination / (page.name + ".png"))
                book.savefig(fig, facecolor="white")
            finally:
                plt.close(fig)
    write(destination / (name + ".pdf"), pdf.getvalue())
    output = io.StringIO(newline="")
    fields = ["figure", "arm", *Mark.__dataclass_fields__]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for page in pages:
        writer.writerows(dict(figure=page.name, arm=arm, **asdict(row)) for row in page.rows)
    write(destination / (name + ".csv"), output.getvalue().encode())


def _index(out, panel, arms, pages, count_arm, additional):
    labels = {"fitted_c": "Fitted calibration", "c0": "Zero calibration"}
    text = [
        "# Position error by receiver modification",
        "",
        "[Browse individual charts](index.html)",
        "",
    ]
    if panel == "matched135":
        text += ["Each figure uses the same 127 DS26 and eight DS29 roof recordings.", ""]
    if panel == "published":
        text += [
            "Each page compares a modification with v5 on exactly the same recordings. "
            "The chart headings give the dataset and number of recordings. Both roof datasets "
            "come from the same receiver site.",
            "",
            "The 127 common DS26 recordings had successful runs under every original v5 option "
            "in both repeats. The eight DS29 recordings come from the original blind panel. "
            "These charts score subsequent experiments retrospectively on that panel.",
            "",
        ]
    text += [
        "The upper plots count all recordings. The lower plots show each returned estimate",
        "and mark its median with a diamond. The four original v5 configurations are",
        "shown on every page. A forced estimate includes the best guess when a fix is withheld.",
        "",
    ]
    for arm in arms:
        links = [
            f"[View every chart]({arm}/README.md)",
            f"[Figure book]({arm}/modifications.pdf)",
            f"[Source rows]({arm}/modifications.csv)",
        ]
        if additional:
            links.append(f"[Additional recordings]({arm}/additional-recordings.pdf)")
        text.extend([f"**{labels[arm]}**  " + " · ".join(links), ""])
    groups = list(dict.fromkeys(m.dataset for p in pages for m in p.rows))
    columns = [
        "Modification",
        *(f"{g} fixes · median km · P95 km" for g in groups),
        *(labels[a] for a in arms),
    ]
    text += [
        f"Fix counts use {labels[count_arm].lower()} and the four-region decision when available. "
        "Other rows use the decision described on their chart. Median and P95 use published fixes.",
        "",
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for page in pages:
        mode = "four" if any(m.series == "four" for m in page.rows) else "one"
        if any(m.series == "global" for m in page.rows):
            series = {k: COLD_START_LABELS[k] for k in ("global", "one")}
        elif page.method == "single_rx0_factors":
            series = RX0_FACTOR_LABELS
        elif page.method in MEMORY_LABELS:
            series = MEMORY_LABELS[page.method]
        elif page.method in DETECTOR_FIT_LABELS and any(m.series == "stock" for m in page.rows):
            present = {m.series for m in page.rows}
            series = {k: v for k, v in DETECTOR_FIT_LABELS[page.method].items() if k in present}
        else:
            series = {mode: ""}
        columns = [TITLES.get(page.name, page.name)]
        for group in groups:
            cells = []
            for code, label in series.items():
                sample = [m for m in page.rows if m.dataset == group and m.series == code]
                errors = [m.error_km for m in sample if m.decision == "published"]
                measured = any(m.decision in ("published", "withheld") for m in sample)
                cell = "Unmeasured" if sample else "Untested"
                if measured:
                    cell = f"{len(errors)}/{len(sample)}"
                elif sample and page.method in COLD_START:
                    cell = f"0/{len(sample)} · unmeasured"
                if errors:
                    stats = distribution(errors)
                    cell += f" · {stats['p50']:.3f} · {stats['p95']:.3f}"
                cells.append(f"{label} · {cell}" if label else cell)
            columns.append("<br>".join(cells))
        columns += [f"[Figure]({a}/{page.name}.png)" for a in arms]
        text.append("| " + " | ".join(columns) + " |")
    if panel in ("matched135", "published"):
        names = {page.method for page in pages}
        if "v5_lean" in names:
            text += [
                "",
                "The lean v5 trial extracts positions from archived numerical fits on DS26. "
                "The full numerical fit was rerun on the 16-recording panel.",
            ]
        if names & RAW_RECEIVERS:
            text += [
                "",
                "The four bounded raw-IQ changes use 80 scheduled windows per recording. "
                "Streamed IQ decoding and bounded raw-IQ replay share the same measured native "
                "detector and downstream position decision.",
            ]
    write(Path(out) / "README.md", ("\n".join(text) + "\n").encode())


def _gallery(destination, pages, arm):
    calibration = "Fitted calibration" if arm == "fitted_c" else "Zero calibration"
    lines = [
        f"# Position error by receiver modification · {calibration}",
        "",
        "The top row counts every recording. A curve that ends at 50% means the receiver "
        "returned positions on half the recordings. Each dot below is one returned position. "
        "The diamond marks their median. A forced estimate is the receiver’s best guess "
        "even when it withheld a fix.",
        "",
        "[PDF](modifications.pdf) · [Per-recording errors](modifications.csv) · "
        "[Fix counts and both calibration settings](../README.md)",
    ]
    for page in pages:
        title = TITLES.get(page.method, page.method)
        lines.extend(["", f"## {title}", "", page.subtitle, "", f"![{title}]({page.name}.png)"])
    write(destination / "README.md", ("\n".join(lines) + "\n").encode())


def generate(out, arms, methods=None, runs=None, panel=None, additional=False, evidence=None):
    from . import atlas

    methods = list(dict.fromkeys(methods or []))
    if panel == "screening":
        from .qualification import screening_figures

        if runs is not None or additional:
            raise ValueError("the screening panel uses sealed study evidence")
        manifest = screening_figures.generate(
            out, arms, methods, evidence=evidence or screening_figures.REPORT
        )
        atlas.write_index(
            out,
            [atlas.screening_section(manifest, arms, folder=".")],
            arms,
            description="Roof charts use the four original v5 choices on the named recordings. "
            "Each independent location plot uses its own measured or simulated queries. "
            "Unmeasured attempts remain visible in counts and tables.",
        )
        return manifest
    if panel == "convergence":
        from .qualification import convergence_figures

        if runs is not None or additional:
            raise ValueError("the convergence panel uses the sealed matched experiments")
        manifest = convergence_figures.generate(
            out, arms, methods, evidence=evidence or convergence_figures.REPORT
        )
        atlas.write_index(
            out,
            [atlas.convergence_section(manifest, arms, folder=".")],
            arms,
            description="Roof charts use the four original v5 references and the declared matched "
            "control. Independent waveform and site trials retain their own sample counts.",
        )
        return manifest
    if panel == "short-receiver":
        from .qualification import short_receiver_figures

        if runs is not None or additional or evidence is not None:
            raise ValueError("the short-receiver panel uses the published matched experiments")
        manifest = short_receiver_figures.generate(out, arms, methods)
        atlas.write_index(
            out,
            atlas.short_receiver_sections(manifest, arms, folder="."),
            arms,
            description="Each roof chart compares the modification with the four v5 options on "
            "the recordings shown. The location trials label the offered region and the source "
            "of the measurements. The curves count every scheduled case in the displayed cohort.",
        )
        return manifest
    if panel == "atlas":
        if runs is not None or evidence is not None or additional or methods:
            raise ValueError(
                "the atlas includes all measured modifications and their published cohorts"
            )
        return atlas.generate(out, arms)
    if panel == "transfer124":
        from .qualification import transfer_figures

        if runs is not None or evidence is not None or additional:
            raise ValueError("the transfer chart book uses the complete published paired queries")
        return transfer_figures.generate(out, arms, methods)
    if panel is None:
        panel = "roof16" if runs is not None else "published"
        if runs is None and (additional or (evidence is not None and not methods)):
            panel = "matched135"
    if panel == "published" and (runs is not None or additional):
        raise ValueError("use the published gallery for each modification's measured cohort")
    if (
        runs is None
        and panel != "published"
        and (panel not in ("roof16", "matched135") or set(methods) - set(TEN))
    ):
        raise ValueError(
            "choose a published modification on matched135 or roof16, or provide --runs"
        )
    if runs is not None and panel == "matched135":
        raise ValueError("choose a live roof panel for --runs")
    if runs is not None and additional:
        raise ValueError("the additional qualification pages use the published measurements")
    if runs is not None and evidence is not None:
        raise ValueError("choose a live run directory or the matched-study evidence directory")
    count_arm = "fitted_c" if "fitted_c" in arms else arms[0]
    index_pages = []
    live = live_pages_by_arm(runs, panel, arms, methods) if runs is not None else None
    for arm in arms:
        if live is not None:
            pages, extra = live[arm], []
        elif panel == "published":
            if evidence is None:
                from .qualification.atlas_roof import roof_pages

                pages = roof_pages(arm, methods)
            else:
                pages = published_pages(arm, methods, evidence)
            extra = []
        else:
            pages, extra = bundled(arm, methods or TEN, additional, panel, evidence)
        destination = Path(out) / arm
        write_book(pages, destination, "modifications", arm)
        _gallery(destination, pages, arm)
        if extra:
            write_book(extra, destination, "additional-recordings", arm)
        if arm == count_arm:
            index_pages = pages
        print(f"{len(pages)} modification figures, {arm}: {destination / 'modifications.pdf'}")
    _index(out, panel, arms, index_pages, count_arm, additional)
    atlas.write_roof(out, index_pages, arms)
    return index_pages
