"""Bind the adaptive sample to the real saved publication in a research namespace."""

from contextlib import ExitStack, contextmanager
import json
import math
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from reports.ALGO08.v3.live_adaptive_grid import adaptive_sampler


NAMESPACE = "research-adaptive-position-v1"
SAMPLE_KIND = "research-adaptive-conditional-position-sample"


def phase_digest(signed, fit):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.position_grid import ARMS

    stages = signed["arms"] if fit is None else fit["policy_arms"]
    if set(stages) != set(ARMS):
        raise ValueError("Both arms must bind their published phase state")
    return canonical_digest({arm: dict(reference=[float(v) for v in record["phase_reference"]],
                                        posterior=[float(v) for v in record["state"]["phases"]])
                             for arm, record in stages.items()})


def research_folder(root, run):
    from leo.storage.fast_scan import safe_id

    return root/NAMESPACE/safe_id(run)


def read_manifest(root, run):
    from leo.contracts.digests import canonical_digest

    folder = research_folder(root, run)
    result = json.loads((folder/"research-manifest.json").read_bytes())
    if (result["kind"] != NAMESPACE or result["schema_version"] != 1 or result["run_id"] != run
            or canonical_digest(result["publication"]) != result["publication_sha256"]):
        raise ValueError("Invalid research publication identity")
    return result


def read_sidecar(root, run, name):
    from leo.contracts.digests import canonical_digest

    manifest = read_manifest(root, run)
    file = {"sample": "adaptive-position-sample.json", "path": "recorded-position-path.json"}[name]
    data = json.loads((research_folder(root, run)/file).read_bytes())
    if (canonical_digest(data) != manifest["sidecars_sha256"][name]
            or name == "sample" and data["phase_state_sha256"] != manifest["phase_state_sha256"]):
        raise ValueError("Research sidecar differs from its manifest")
    return data


def check_sample(grid, science):
    from leo.contracts.position_grid import ARMS

    count = grid["evaluated_points"]
    if (grid["schema_version"] != 1 or grid["kind"] != SAMPLE_KIND or grid["matched_c_grid"] is not True
            or grid["complete"] is not True or grid["objective_calls"] != {a: count for a in ARMS}
            or count != len(grid["points"]) or count != grid["planned_points"]
            or not 0 < grid["initial_layout"]["points"] <= count <= grid["reference_layout"]["candidates"]
            or grid["endpoint_latlon"] != {a: row["endpoint_latlon"] for a, row in science["arms"].items()}
            or grid["region_center"] != science["region"]["center"]
            or grid["box_width_km"] != science["region"]["width_km"]):
        raise ValueError("The research sample differs from the original fitted geometry or planned accounting")
    lat, lon = grid["region_center"]
    scale = 111.32*math.cos(math.radians(lat))
    seen = set()
    for point in grid["points"]:
        xy = point["east_km"], point["north_km"]
        scores = point["scores"]
        expected = lat+xy[1]/111., lon+xy[0]/scale
        if (xy in seen or not all(math.isfinite(v) and abs(v) <= grid["box_width_km"]/2 for v in xy)
                or set(scores) != set(ARMS) or set(point["failures"]) != {a for a in ARMS if scores[a] is None}
                or any(v is not None and not math.isfinite(v) for v in scores.values())
                or any(abs(a-b) > 1e-9 for a, b in zip(expected, point["latlon"], strict=True))):
            raise ValueError("Invalid adaptive location, score or regional transform")
        seen.add(xy)
    if not {tuple(grid["endpoints"][a]) for a in ARMS} <= seen:
        raise ValueError("Adaptive sample omitted a published endpoint")


def write_research(root, run, document, images, grid, path, phases):
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.contracts.fast_standard_analysis import PLOTS, standard_model, validate
    from leo.contracts.position_grid import binding
    from leo.contracts.position_path import validate as validate_path
    from leo.storage.fast_scan import immutable_json

    if set(images) != set(PLOTS) or document["run_id"] != run or len(phases) != 1:
        raise ValueError("The research sink requires all eight artifacts and a completed adaptive sample")
    figures = [dict(name=name, sha256=sha256_digest(images[name]), byte_count=len(images[name])) for name in PLOTS]
    ordinary_projection = validate(dict(document, artifacts=figures), model=standard_model(run))
    bound = binding(ordinary_projection)
    science = {k: v for k, v in ordinary_projection.items() if k != "schema_version"}
    check_sample(grid, science)
    adaptive = dict(grid, binding=bound, phase_state_sha256=phases[0])
    recorded = validate_path(dict(path, binding=bound), ordinary_projection)
    manifest = dict(schema_version=1, kind=NAMESPACE, run_id=run, publication=science,
                    publication_sha256=canonical_digest(science), phase_state_sha256=phases[0],
                    sidecars_sha256=dict(sample=canonical_digest(adaptive), path=canonical_digest(recorded)))
    target = research_folder(root, run)
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        raise ValueError("The research publication already exists")
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        stage = Path(temporary)/"publication"
        stage.mkdir()
        for figure in figures:
            data = images[figure["name"]]
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Every research artifact must be a PNG")
            file = stage/(figure["sha256"][7:]+".png")
            if not file.exists():
                with file.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        for name, value in (("adaptive-position-sample", adaptive), ("recorded-position-path", recorded),
                            ("research-manifest", manifest)):
            immutable_json(stage/(name+".json"), value)
        stage.rename(target)
    return science


def label_figure(original, *args, position_grid=None, **kwargs):
    figure = original(*args, position_grid=position_grid, **kwargs)
    if position_grid and position_grid.get("kind") == SAMPLE_KIND:
        main = figure.axes[0]
        title = main.get_title()
        n, plan = position_grid["evaluated_points"], position_grid["planned_points"]
        full = position_grid["reference_layout"]["candidates"]
        main.set_title(title.replace(f"{n}/{plan} grid locations", f"{n}/{full} reference locations sampled"))
        figure._suptitle.set_text(figure._suptitle.get_text().replace("diagnostic position map", "adaptive research position map"))
        footer = figure._supxlabel
        footer.set_text(footer.get_text().replace("Coloured grid: post-fit conditional loss.",
                                                  "Coloured dots: exact post-fit loss at adaptive samples."))
    return figure


@contextmanager
def research_layout(output):
    """Keep analysis, rendering and readback on their normal live ports."""
    from functools import partial

    from leo.contracts.digests import sha256_digest
    from leo.presentation import fast_standard_analysis as figures, localization_v3 as position
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore as store_type
    from tools import algo08_position

    root = output.resolve()
    phases = []
    detail, artifact, publish, path, grid, selected = (
        store_type.detail, store_type.artifact, store_type.publish, store_type.position_path,
        store_type.position_grid, algo08_position.selected_packet)

    def selected_bound(prepared, signed, fit):
        phases.append(phase_digest(signed, fit))
        return selected(prepared, signed, fit)

    def published(store, run, document, images, *, position_grid=None, position_path=None):
        if store.root == root:
            return write_research(root, run, document, images, position_grid, position_path, phases)
        return publish(store, run, document, images, position_grid=position_grid, position_path=position_path)

    def detail_at(store, run):
        if store.root == root and research_folder(root, run).is_dir():
            return read_manifest(root, run)["publication"]
        return detail(store, run)

    def figure_at(store, run, name, expected=None):
        if store.root != root:
            return artifact(store, run, name, expected)
        manifest = read_manifest(root, run)["publication"]
        matches = [a for a in manifest["artifacts"] if a["name"] == name and (expected is None or a["sha256"] == expected)]
        if len(matches) != 1:
            raise FileNotFoundError("Research figure revision unavailable")
        entry, = matches
        raw = (research_folder(root, run)/(entry["sha256"][7:]+".png")).read_bytes()
        if sha256_digest(raw) != entry["sha256"] or len(raw) != entry["byte_count"]:
            raise ValueError("Research figure integrity failure")
        return raw

    with ExitStack() as stack:
        stack.enter_context(patch.object(position, "sample_position_grid", adaptive_sampler))
        stack.enter_context(patch.object(figures, "position_figure", partial(label_figure, figures.position_figure)))
        stack.enter_context(patch.object(algo08_position, "selected_packet", selected_bound))
        stack.enter_context(patch.object(store_type, "publish", published))
        stack.enter_context(patch.object(store_type, "detail", detail_at))
        stack.enter_context(patch.object(store_type, "artifact", figure_at))
        stack.enter_context(patch.object(store_type, "position_grid", lambda store, run:
                                       read_sidecar(root, run, "sample") if store.root == root else grid(store, run)))
        stack.enter_context(patch.object(store_type, "position_path", lambda store, run:
                                       read_sidecar(root, run, "path") if store.root == root else path(store, run)))
        yield
