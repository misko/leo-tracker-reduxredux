"""Position follow-ups to the detector-only studies and the two-recording receiver trials."""

import json

from .. import corpus
from .. import figure_books as books
from ..__main__ import read_predictions, references
from ..position_figure import marks

REPORT = books.REPORT.parent / "2026_11_19_position_atlas"
DETECTORS = {
    "native_geometry": (
        "native-geometry",
        "Two scheduled 20 ms IQ visits per recording use the wideband detector. Other visits "
        "use capture-era GLRT. Both the modified input and its control run through the compact "
        "v5 finish, including final reassociation.",
    ),
    "spectral_grid": (
        "spectral-grid",
        "Eight scheduled IQ visits per recording use the sliding-tone pilot grid. The remaining "
        "visits use capture-era GLRT. Modified and original inputs receive fresh full v5 fits.",
    ),
    "pilot_confirmation": (
        "pilot-confirmation",
        "Apply late-pilot confirmation on 112 scheduled visits per recording. Other visits retain "
        "ordinary native GLRT. Both inputs receive fresh full v5 fits.",
    ),
}
NEW = ("v5_stream_prepare", "pass_geometry")


def _receipts(path, refs, method=None):
    rows = books._complete(read_predictions(path), refs)
    for row in rows.values():
        if method is not None and row.get("method") != method:
            raise ValueError(f"wrong receiver in {path}")
        if row["result"]["status"] in ("ok", "withheld") and (
            "arms" not in row["result"]
            or row["result"]["metrics"].get("position_attempted") is False
        ):
            raise ValueError(f"completed position comparison without both position arms in {path}")
    return rows


def detector_page(method, arm, root):
    name, subtitle = DETECTORS[method]
    folder = root / name
    refs = references("smoke", None)[1]
    _, hashes = corpus._selection("roof16")
    bindings = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    candidate = _receipts(folder / "positions.jsonl.gz", refs, method)
    stock = _receipts(folder / "control-positions.jsonl.gz", refs)
    extra = {"stock": stock}
    if method == "pilot_confirmation" and (folder / "full-positions.jsonl.gz").is_file():
        extra["all_visits"] = _receipts(folder / "full-positions.jsonl.gz", refs, method)
        subtitle += " The all-visits curve applies the gate throughout each recording."
    ordinary = {}
    if method == "pilot_confirmation":
        ordinary = json.loads(
            (books.FRONTEND_REPORT / "ordinary/recording-receipts.json").read_bytes()
        )["recordings"]
    expected_control = {
        "spectral_grid": "spectral_grid_capture_control",
        "native_geometry": "archive_control",
        "pilot_confirmation": "ordinary_control",
    }
    for case, original in stock.items():
        source = original.get("source_archive_sha256", "")
        if (
            len(source) != 64
            or any(c not in "0123456789abcdef" for c in source)
            or original.get("method") != expected_control[method]
        ):
            raise ValueError(f"invalid paired detector control for {case}")
        expected = (
            ordinary[case]["native_sha256"] if ordinary else bindings[case]["native"]["sha256"]
        )
        if source != expected:
            raise ValueError(f"unmatched detector GLRT source for {case}")
        if any(
            rows[case].get("source_archive_sha256") != source
            for rows in (candidate, *extra.values())
        ):
            raise ValueError(f"unmatched source GLRT for {case}")
        if method == "pilot_confirmation":
            variants = [(candidate[case], "partial-visits"), (original, "matched-ordinary")]
            if "all_visits" in extra:
                variants.append((extra["all_visits"][case], "all-visits"))
            if any(row.get("variant") != expected for row, expected in variants):
                raise ValueError(f"unmatched pilot confirmation run scope for {case}")
    return books.Page(
        method, method, subtitle, marks(refs, candidate, None, method, arm, additional_modes=extra)
    )


def stream_page(arm, root):
    refs = references("smoke", None)[1]
    return books.paired_finish_page(
        arm,
        "v5_stream_prepare",
        root / "stream-prepare",
        "Read the original GLRT candidates one probe at a time. The original and incremental "
        "readers feed the same compact v5 tracker and complete position fit.",
        expected_cases=[r["id"] for r in refs],
    )


def pass_page(arm, root):
    folder = root / "pass-geometry"
    refs = references("smoke", None)[1]
    _, hashes = corpus._selection("roof16")
    bindings = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    modes = {}
    for mode in ("matched-tile", "global"):
        rows = _receipts(folder / f"{mode}.jsonl.gz", refs, "pass_geometry")
        for case, row in rows.items():
            if row.get("mode") != mode or any(
                row.get(f"{field}_sha256") != bindings[case][field]["sha256"]
                for field in ("catalog", "native")
            ):
                raise ValueError(f"unmatched pass-geometry receiver inputs for {case}")
        modes[mode] = rows
    return books.Page(
        "pass_geometry",
        "pass_geometry",
        "Estimate two possible receiver locations from each Doppler pass. Run global and supplied "
        "25 km tile searches on two development recordings using complete GLRT and causal TLEs.",
        marks(
            refs,
            modes["matched-tile"],
            None,
            "pass_geometry",
            arm,
            additional_modes={"global": modes["global"]},
            diagnostic_modes=("one", "global"),
        ),
    )


def roof_pages(arm, methods, root=REPORT):
    """Include paired position fits for the earlier timing-only studies."""
    legacy = [m for m in methods if m not in NEW]
    pages = books.published_pages(arm, legacy) if legacy or not methods else []
    selected = methods or [*(p.name for p in pages), *NEW]
    mapping = {p.name: p for p in pages}
    for name in selected:
        if name in DETECTORS:
            mapping[name] = detector_page(name, arm, root)
        elif name == "v5_stream_prepare":
            mapping[name] = stream_page(arm, root)
        elif name == "pass_geometry":
            mapping[name] = pass_page(arm, root)
    return [mapping[m] for m in selected]
