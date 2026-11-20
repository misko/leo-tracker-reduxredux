"""Specialize the immutable direct readout once, before building its release."""

import argparse
import ast
import shutil
import subprocess
from pathlib import Path

from . import direct_cavity_trial as direct

ROOT = direct.common.ROOT
REPORT = direct.REPORT.parent.parent / "next/direct-lifetime"
GLUE = direct.VARIANTS + "v5_direct_lifetime.py"
KERNEL = direct.VARIANTS + "direct_lifetime_kernels.py"
PORT = "tools.pipeline_eval.variants.v5_direct_lifetime"
PURE = "tools.pipeline_eval.variants.direct_lifetime_kernels"
LOC = "leo/analysis/localization_v3/"
PREP = "leo/application/localization_v3.py"
INPUTS = "leo/operations/localization_v3_inputs.py"
DONORS = {
    "v5_stream_prepare": (
        "TrackCandidate",
        "CANDIDATE_FIELDS",
        "SPACE",
        "PrivateNativeDocument",
        "project_record",
        "decode_native",
        "read_native",
        "prepare_owned",
    ),
    "v5_catalogue_memory": ("SATELLITES_PER_BATCH", "bounded_states"),
    "prep_stream_sky": ("COARSE_ROWS", "regional_bank"),
    "history_stream_prep": ("last_use",),
    "v5_track_projection": ("TrackColumns", "TrackField"),
    "v5_sparse_discovery": ("RetainedRows", "retain_diagnostics"),
    "v5_family_memory": ("alignment_only",),
    "v5_tiled_salvage": ("ROWS", "coarse_scores", "fine_alternatives", "salvage"),
    "v5_nomination_memory": ("TILE", "screen", "nominate"),
}


def replace(source, old, new, count=1):
    if source.count(old) != count:
        raise ValueError(f"unrecognized specialization anchor {old.strip()!r}")
    return source.replace(old, new)


def module_nodes(source):
    by_name = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            by_name[node.name] = node
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                by_name[target.id] = node
    return by_name


def kernel_source(donors):
    header = (
        '"""Bounded numerical operations assembled from the qualified method sources."""\n'
        "import copy\nimport hashlib\nimport json\nimport re\n"
        "from contextlib import contextmanager\nfrom dataclasses import replace\n"
        "from pathlib import Path\nfrom typing import NamedTuple\nimport numpy as np"
    )
    parts = [header]
    for name, functions in DONORS.items():
        text = donors[name]
        lines, nodes = text.splitlines(keepends=True), module_nodes(text)
        for function in functions:
            item = nodes[function]
            start = min(
                (d.lineno for d in getattr(item, "decorator_list", ())), default=item.lineno
            )
            parts.append("".join(lines[start - 1 : item.end_lineno]).strip("\n"))
    output = "\n\n\n".join(parts) + "\n"
    output = replace(output, "v5_catalogue_memory.bounded_states(", "bounded_states(")
    output = replace(
        output, "def salvage(kernel, counters, trace,", "def salvage(kernel, counters,"
    )
    return replace(
        output,
        '        trace.append(dict(component=track["key"], candidate_indices=sorted(shortlist)))\n',
        "",
    )


def specialized(sources):
    out = {}
    text = sources[direct.ENTRY]
    text = replace(text, 'METHOD = "v5_direct_cavity"', 'METHOD = "v5_direct_lifetime"')
    text = replace(
        text,
        "import orbit_projector, v5_core\n",
        "import orbit_projector, v5_core\n"
        f"from {PORT} import project, reclaim\n"
        f"from {PURE} import read_native\n",
    )
    text = replace(
        text,
        "    def evaluate(grid, *args, **kwargs):\n"
        "        operation = (\n"
        "            projector.evaluate\n"
        "            if isinstance(grid, orbit_projector.Stencil)\n"
        "            else phase_linear_frequency\n"
        "        )\n"
        "        return operation(grid, *args, **kwargs)\n",
        "    def evaluate(grid, *args, **kwargs):\n"
        "        if isinstance(grid, orbit_projector.Stencil):\n"
        "            return project(projector.evaluate, grid, args, kwargs)\n"
        "        return phase_linear_frequency(grid, *args, **kwargs)\n",
    )
    text = replace(
        text,
        "    document = verified_json(native, native_sha256)\n",
        '    document = read_native(dict(path=native, sha256="sha256:" + '
        'native_sha256.removeprefix("sha256:")))\n',
    )
    text = replace(
        text,
        "    started = perf_counter()\n    signed = signed_context(",
        "    started = perf_counter()\n    reclaim()\n    signed = signed_context(",
    )
    text = replace(
        text,
        '    stages["signed"] = perf_counter() - started\n    del conservative, family\n',
        "    del conservative, family\n    reclaim()\n"
        '    stages["signed"] = perf_counter() - started\n',
    )
    text = replace(
        text,
        "    if offered:\n        cavity = cavity_policy(",
        "    if offered:\n        reclaim()\n        cavity = cavity_policy(",
    )
    out[direct.ENTRY] = text

    core = direct.VARIANTS + "v5_core.py"
    out[core] = replace(
        sources[core],
        "    return fit_initial_nodes(scan, ranked_initial_nodes(scan)[:3])\n",
        f"    from {PORT} import projection_columns\n\n"
        "    with projection_columns():\n"
        "        ranked = ranked_initial_nodes(scan)[:3]\n"
        "    return fit_initial_nodes(scan, ranked)\n",
    )
    path = LOC + "scan.py"
    text = replace(
        sources[path],
        "from leo.sky.propagation import ElementSetCatalogue\n",
        "from leo.sky.propagation import ElementSetCatalogue\n"
        f"from {PORT} import columns_active\n"
        f"from {PURE} import retain_diagnostics\n",
    )
    out[path] = replace(
        text,
        "            visible = e[:, ix].min(axis=1) >= 0\n"
        '            good = terms["passing"] & visible\n',
        "            visible = e[:, ix].min(axis=1) >= 0\n"
        "            if columns_active.get() and not all_tracks and method in "
        '("shared_phase", "receiver_smooth"):\n'
        "                retain_diagnostics(terms, visible)\n"
        '            good = terms["passing"] & visible\n',
    )
    out[INPUTS] = replace(
        sources[INPUTS],
        "from leo.analysis.localization_v3.orbits import regional_bank\n",
        f"from {PORT} import regional_bank\n",
    )
    text = replace(
        sources[PREP],
        "    prepared = prepare_tracks(document, track_config)\n",
        f"    from {PORT} import phase_history\n"
        f"    from {PURE} import prepare_owned\n\n"
        "    prepared = prepare_owned(prepare_tracks, document, track_config)\n",
    )
    text = replace(
        text,
        "    if element_parser is None:\n        element_parser = ElementParser()\n",
        "    own_parser = element_parser is None\n"
        "    if own_parser:\n        element_parser = ElementParser()\n",
    )
    out[PREP] = replace(
        text,
        "    history = prepare_phase_history(archive, sky['nominal_elements'], "
        "prepared['metadata'],\n"
        "                                    element_parser=element_parser)\n",
        "    if own_parser:\n"
        "        history = phase_history(prepare_phase_history, element_parser, archive,\n"
        "                                sky['nominal_elements'], prepared['metadata'])\n"
        "    else:\n"
        "        history = prepare_phase_history(archive, sky['nominal_elements'], "
        "prepared['metadata'],\n"
        "                                        element_parser=element_parser)\n",
    )
    path = LOC + "retained_position.py"
    text = replace(
        sources[path],
        "def phase_widths(scan, labels):\n",
        "def phase_widths(scan, labels, *, bank_reader=previous_bank):\n",
    )
    out[path] = replace(
        text,
        "    _, _, alignments = previous_bank(scan, labels)\n",
        "    _, _, alignments = bank_reader(scan, labels)\n",
    )
    path = LOC + "family_weighting.py"
    text = replace(
        sources[path],
        "from leo.analysis.localization_v3.retained_position import phase_widths\n",
        f"from {PORT} import phase_widths, projection_columns\n",
    )
    out[path] = replace(
        text,
        "        f, e, d = phase_linear_frequency(scan.geometry, "
        "*scan.search_region.latlon(anchor))\n",
        "        with projection_columns():\n"
        "            f, e, d = phase_linear_frequency(scan.geometry, "
        "*scan.search_region.latlon(anchor))\n",
    )
    path = LOC + "signed_context.py"
    text = replace(
        sources[path],
        "from leo.analysis.localization_v3.retained_position import phase_widths\n",
        f"from {PORT} import phase_widths\n",
    )
    text = replace(
        text,
        "    base = problem(scan, node, 'c0', keep)\n",
        "    labels = problem(scan, node, 'c0', keep).labels\n",
    )
    out[path] = replace(text, "phase_widths(scan, base.labels)", "phase_widths(scan, labels)", 2)
    path = LOC + "event_position.py"
    text = sources[path]
    refit = ast.get_source_segment(text, module_nodes(text)["refit"])
    alternative = replace(
        refit,
        "    reference = np.zeros(len(means))\n",
        f"    from {PORT} import dispose_model\n\n    reference = np.zeros(len(means))\n",
    )
    alternative = replace(
        alternative,
        "        reference = phase\n",
        "        reference = phase\n"
        "        if _epoch < 4:\n            dispose_model(p)\n            del p\n",
    )
    alternative = replace(
        alternative, "    return record", "    dispose_model(p)\n    return record"
    )
    out[path] = replace(text, refit, alternative)
    path = LOC + "conservative_recovery.py"
    text = sources[path]
    stock = ast.get_source_segment(text, module_nodes(text)["salvage"])
    out[path] = replace(
        text,
        stock,
        "def salvage(scan, node, keep, *, rounds=5, iterations=48):\n"
        "    from collections import Counter\n"
        "    from leo.analysis.localization_v3 import conservative_recovery as kernel\n"
        f"    from {PURE} import salvage as tiled\n\n"
        "    return tiled(kernel, Counter(), scan, node, keep, "
        "rounds=rounds, iterations=iterations)",
    )
    path = LOC + "family_cavity.py"
    text = sources[path]
    stock = ast.get_source_segment(text, module_nodes(text)["nominate_families"])
    out[path] = replace(
        text,
        stock,
        "def nominate_families(d):\n"
        "    from leo.analysis.localization_v3 import family_cavity as kernel\n"
        f"    from {PURE} import nominate\n\n"
        "    return nominate(kernel, d)",
    )
    return out


def stage(work, original):
    original = original.resolve()
    old = original / "bundle.json"
    receipt = direct.common.seal(direct.REPORT, "receipt.json", ("bundle.json",))
    if direct.common.sha(old) != receipt["files"]["bundle.json"]:
        raise ValueError("direct source archive changed")
    previous = direct.common.read(old)
    base = original / direct.RELEASE
    for name, digest in previous["files"].items():
        if direct.common.sha(base / name) != digest:
            raise ValueError(f"immutable archive differs at {name}")
    affected = (
        direct.ENTRY,
        direct.VARIANTS + "v5_core.py",
        PREP,
        INPUTS,
        *(
            LOC + k + ".py"
            for k in (
                "scan",
                "retained_position",
                "family_weighting",
                "signed_context",
                "event_position",
                "conservative_recovery",
                "family_cavity",
            )
        ),
    )
    donors = {k: ROOT / f"{direct.VARIANTS}{k}.py" for k in DONORS}
    legacy = REPORT.parent.parent / "integration/cavity-lifetime/plan.json"
    authority = direct.common.read(legacy)["source"]["sources"]
    for path in donors.values():
        name = str(path.relative_to(ROOT))
        if name in authority and direct.common.sha(path) != authority[name]:
            raise ValueError(f"reviewed bounded source changed: {name}")
    changes = specialized({name: (base / name).read_text() for name in affected})
    changes.update(
        {
            KERNEL: kernel_source({k: p.read_text() for k, p in donors.items()}),
            GLUE: (ROOT / GLUE).read_text(),
        }
    )
    bundle = work / direct.RELEASE
    bundle.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in sorted(set(previous["files"]) | set(changes)):
        dst = bundle / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if name in changes:
            code = changes[name]
            compile(code, name, "exec")
            dst.write_text(code)
        else:
            shutil.copyfile(base / name, dst)
        files[name] = direct.common.sha(dst)
    code = (
        "from leo.analysis.localization_v4.backend import build_native; "
        "import sys; build_native(sys.argv[1])"
    )
    subprocess.run(
        [str(direct.v5_lean.PYTHON), "-B", "-c", code, str(bundle / "native")],
        cwd=bundle,
        env=direct.command_env(bundle),
        check=True,
        timeout=40,
    )
    if direct.common.sha(bundle / "native/native_bound.so") != previous["binary"]:
        raise ValueError("rebuilt native bound differs from the staged control")
    direct.save_json(
        work / "bundle.json",
        dict(
            files=files,
            binary=previous["binary"],
            frozen_source=previous["frozen_source"],
            altered={
                k: dict(before=previous["files"].get(k), after=files[k]) for k in sorted(changes)
            },
            donors={str(p.relative_to(ROOT)): direct.common.sha(p) for p in donors.values()},
            base_bundle_sha256=direct.common.sha(old),
            legacy_lock_sha256=direct.common.sha(legacy),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("original", type=Path)
    a = p.parse_args()
    stage(direct.local_output(a.work), a.original)
