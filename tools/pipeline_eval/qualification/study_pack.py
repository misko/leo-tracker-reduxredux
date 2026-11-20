"""Package the measured position and sealed stage evidence under a study directory."""

import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS
from . import receiver_core_pack as pack
from . import screening_figures as position
from .full_v5_check import _sha
from .original_support_benchmark import score_charts
from .prefix_figures import csv_file


def descriptors(root):
    paths = sorted([*root.rglob(position.SPEC), *root.rglob(pack.STAGE_SPEC)])
    for path in paths:
        if path.resolve() != path or not path.is_file():
            raise ValueError(f"study descriptor must be a regular local file: {path}")
    return paths


def catalog(root, paths, panels):
    """Record supplied descriptors, their receipts, and the exact exported chart IDs."""
    stage_ids = defaultdict(list)
    for panel, path in panels:
        stage_ids[path].append(panel.id)
    scopes, files, entries, positions = {}, {}, {}, {}
    declared = set()
    for path in paths:
        name = path.relative_to(root).as_posix()
        scope = path.parent.relative_to(root).parts[:1]
        scope = scope[0] if scope else "."
        study = scopes.setdefault(scope, dict(position_charts=[], stage_charts=[]))
        payload = path.read_bytes()
        spec = json.loads(payload)
        files[name] = sha256(payload).hexdigest()
        entries[name] = records = []
        is_stage = path.name == pack.STAGE_SPEC
        if is_stage:
            charts = [spec]
        else:
            position._require_keys(spec, ("version", "charts"))
            charts = spec["charts"]
        if not isinstance(charts, list):
            raise ValueError(f"invalid position descriptor: {path}")
        for chart in charts:
            if not isinstance(chart, dict) or not isinstance(chart.get("id"), str):
                raise ValueError(f"invalid chart ID in {path}")
            ident = chart["id"]
            ids = [ident]
            if is_stage and "profile_image" in chart:
                ids.append(f"{ident}-profile")
            if duplicate := declared.intersection(ids):
                raise ValueError(f"duplicate study chart IDs: {', '.join(sorted(duplicate))}")
            declared.update(ids)
            seal = position._local(path.parent, chart.get("seal"))
            receipt = seal.relative_to(root).as_posix()
            if seal.is_file():
                files[receipt] = _sha(seal)
            record = dict(ids=ids, receipt=receipt)
            records.append(record)
            if is_stage:
                for field in ("image", "csv", "pdf", "profile_image", "profile_csv", "profile_pdf"):
                    if field in chart:
                        position._local(path.parent, chart[field])
                selected = stage_ids[path]
                study["stage_charts"].extend(selected)
                record["state"] = "exported" if selected else "unsealed"
            else:
                positions[ident] = (scope, record)
    return dict(studies=scopes, descriptors=entries, source_sha256=files), positions


def run(source, out):
    root, out = Path(source).expanduser().resolve(), local_output(out)
    if not root.is_dir():
        raise ValueError(f"study directory does not exist: {root}")
    if out.exists():
        raise ValueError(f"choose a new output directory for --pack: {out}")
    paths = descriptors(root)
    stage_paths = [p for p in paths if p.name == pack.STAGE_SPEC]
    panels = pack.stage_specs(root, descriptors=stage_paths)
    inventory, positions = catalog(root, paths, panels)
    candidates = position.charts(evidence=root) if len(stage_paths) != len(paths) else []
    if {model.id for model in candidates} != positions.keys():
        raise ValueError("position chart roster changed during export")
    models, chart_scopes = [], {}
    for model in candidates:
        scope, record = positions[model.id]
        if pack.position_attempted(model):
            models.append(model)
            chart_scopes[model.id] = scope
            inventory["studies"][scope]["position_charts"].append(model.id)
            record["state"] = "exported"
        else:
            record["state"] = "stage_only"
    if not models and not panels:
        raise ValueError("no measured position comparisons or sealed stage charts in the study")
    expected = {(model.id, arm) for model in models for arm in ARMS}
    expected.update((panel.id, "stage") for panel, _ in panels)

    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".study-pack-", dir=out.parent) as temp:
        work = Path(temp)
        downloads = {"Study descriptors and receipts": "study-evidence.json"}
        save_json(work / "study-evidence.json", inventory)
        if models:
            scores, rf, _ = score_charts(models, chart_scopes)
            csv_file(work / "summary.csv", scores)
            csv_file(work / "position-rf.csv", rf)
            downloads.update(
                {
                    "Position error and RF summaries": "summary.csv",
                    "Per-recording position and RF scores": "position-rf.csv",
                }
            )
        rows = pack.build(
            root, out=work, models=models, downloads=downloads, stage_panels=panels, fit_titles=True
        )
        if len(rows) != len(expected) or {(row.panel_id, row.arm) for row in rows} != expected:
            raise ValueError("exported charts differ from the study descriptor inventory")
        if descriptors(root) != paths:
            raise ValueError("study descriptor roster changed during export")
        if pack.stage_specs(root, descriptors=stage_paths) != panels:
            raise ValueError("sealed stage chart roster changed during export")
        for name, digest in inventory["source_sha256"].items():
            whole_iq.checked(root / name, digest)
        out.mkdir()
        try:
            work.replace(out)
        except OSError:
            out.rmdir()
            raise
    print(f"{len(models)} paired position comparisons and {len(panels)} stage charts")
    print(out / "index.html")
