"""Score and package the sealed receiver deadline studies."""

import csv
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS
from . import receiver_core_pack as pack
from . import screening_figures as position
from .full_v5_check import _sha
from .original_support_benchmark import score_charts
from .prefix_figures import csv_file

ROOT = position.REPORT / "receiver-deadline"
SCOPES = (
    "external-spectrum",
    "parallel-acquisition",
    "parallel-position",
    "pilot-distillation",
    "prepared-hotpath",
    "selector-waveform",
    "sequential-fix",
    "two-rate-holdout",
)


def catalog(root, models):
    """Bind the comparison charts to the study directories and source receipts."""
    positions = {model.id for model in models}
    scopes = {scope: dict(position_charts=[], stage_charts=[]) for scope in SCOPES}
    files, chart_scopes = {}, {}

    def add(descriptor, kind, ident, seal):
        relative = descriptor.relative_to(root)
        scope = relative.parts[0]
        if scope not in scopes or not descriptor.resolve().is_relative_to(root):
            raise ValueError(f"unexpected deadline evidence directory for {relative}")
        lock = position._local(descriptor.parent, seal)
        for path in (descriptor, lock):
            name = str(path.relative_to(root))
            if name not in files:
                files[name] = _sha(path)
        scopes[scope][kind].append(ident)
        if kind == "position_charts":
            chart_scopes[ident] = scope

    for descriptor in sorted(root.rglob(position.SPEC)):
        for chart in whole_iq.read(descriptor)["charts"]:
            if chart["id"] in positions:
                add(descriptor, "position_charts", chart["id"], chart["seal"])
    for panel, descriptor in pack.stage_specs(root):
        if descriptor is not None:
            add(descriptor, "stage_charts", panel.id, panel.seal)
    if positions != chart_scopes.keys():
        raise ValueError("deadline position descriptors differ from the loaded chart roster")
    if positions & {ident for scope in scopes.values() for ident in scope["stage_charts"]}:
        raise ValueError("deadline stage and position chart IDs must be distinct")
    if missing := [scope for scope, entry in scopes.items() if not any(entry.values())]:
        raise ValueError(f"deadline scopes without sealed charts: {', '.join(missing)}")
    return scopes, files, chart_scopes


def run(out, *, root=None):
    root = local_output(ROOT if root is None else root)
    out = local_output(out)
    models = [model for model in position.charts(evidence=root) if pack.position_attempted(model)]
    scopes, sources, chart_scopes = catalog(root, models)
    scores, rf, _ = score_charts(models, chart_scopes)
    if not scores:
        raise ValueError("deadline benchmark requires sealed position comparisons")
    csv_file(out / "summary.csv", scores)
    csv_file(out / "position-rf.csv", rf)
    save_json(out / "study-evidence.json", dict(studies=scopes, source_sha256=sources))
    rows = pack.build(
        root,
        out=out,
        models=models,
        downloads={
            "Position error and RF summaries": "summary.csv",
            "Per-recording position and RF scores": "position-rf.csv",
            "Study and receipt inventory": "study-evidence.json",
        },
    )
    for name, digest in sources.items():
        whole_iq.checked(root / name, digest)
    expected_stages = {ident for scope in scopes.values() for ident in scope["stage_charts"]}
    expected_pages = {(model.id, arm) for model in models for arm in ARMS}
    expected_pages.update((ident, "stage") for ident in expected_stages)
    if expected_pages != {(r.panel_id, r.arm) for r in rows} or len(rows) != len(expected_pages):
        raise ValueError("deadline descriptors differ from the exported chart roster")
    with (out / "positions.csv").open(newline="") as stream:
        plotted_rows = sum(1 for _ in csv.DictReader(stream))
    files = ("pack-lock.json", "study-evidence.json", "summary.csv", "position-rf.csv")
    save_json(
        out / "benchmark-lock.json",
        dict(
            schema="receiver-deadline/v1",
            source_program_sha256=_sha(Path(__file__)),
            files={name: _sha(out / name) for name in files},
            position_comparisons=len(models),
            stage_charts=len(expected_stages),
            plotted_position_rows=plotted_rows,
        ),
    )
    print(f"{len(models)} paired position comparisons and {len(expected_stages)} stage charts")
    print(out / "index.html")
