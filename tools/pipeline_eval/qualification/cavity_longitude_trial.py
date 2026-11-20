"""Build and measure an opt-in seam-safe compact cavity release."""

import argparse
import ast
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..__main__ import encoded, local_output, save_json
from ..variants import cavity_longitude
from . import cavity_payload
from . import cavity_payload_transfer as transfer
from . import direct_cavity_trial as direct
from .fresh_scenes import _destination, _read, _sha

REPORT = transfer.REPORT.with_name("longitude")
SOURCE = cavity_payload.ENTRY.rsplit(".", 1)[0].replace(".", "/")
HELPER = SOURCE + "/cavity_longitude.py"
REGION = "leo/analysis/localization_v3/region.py"
SCAN = "leo/analysis/localization_v3/scan.py"
ENTRY = SOURCE + "/v5_direct_cavity.py"
SALT = b"cavity-longitude-dateline-v1-20261119"
SCREEN = (36.0, -179.96)


def methods(source, owner, replacements):
    text = source.decode()
    tree = ast.parse(text)
    cls = next(cls for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == owner)
    nodes = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
    lines = text.splitlines(keepends=True)
    for name in sorted(replacements, key=lambda name: nodes[name].lineno, reverse=True):
        node = nodes[name]
        if node.decorator_list:
            raise ValueError(f"unexpected coordinate decorator: {owner}.{name}")
        lines[node.lineno : node.end_lineno] = [replacements[name]]
    return "".join(lines)


def overlay(original):
    """Rebind the two coordinate producers and the inter-origin conversion."""
    imports = (
        "from tools.pipeline_eval.variants.cavity_longitude import "
        "local_latlon, local_native_point\n"
    )
    region = methods(
        original[REGION],
        "SearchRegion",
        {
            "latlon": (
                "        return local_latlon(self.center, "
                "111.32 * np.cos(np.deg2rad(self.center[0])), local)\n"
            ),
            "native_point": (
                "        return local_native_point(scan.center, scan.scale, self.latlon(local))\n"
            ),
        },
    )
    region_marker = "import numpy as np\n"
    if region.count(region_marker) != 1:
        raise ValueError("unexpected region source")
    scan = methods(
        original[SCAN],
        "ScanLikelihood",
        {"latlon": "        return local_latlon(self.center, self.scale, xy)\n"},
    )
    scan_marker = "import numpy as np\n"
    if scan.count(scan_marker) != 1:
        raise ValueError("unexpected scan source")
    entry = original[ENTRY].decode()
    signature = '    document = read_native(dict(path=native, sha256="sha256:" + '
    if entry.count(signature) != 1:
        raise ValueError("unexpected wrapped receiver entry")
    entry = entry.replace(
        signature,
        "    from tools.pipeline_eval.variants.cavity_longitude import validate_geometry\n\n"
        "    validate_geometry(tile, screen_center, width_km)\n" + signature,
    )
    return original | {
        REGION: region.replace(region_marker, region_marker + imports).encode(),
        SCAN: scan.replace(scan_marker, scan_marker + imports.split(",")[0] + "\n").encode(),
        ENTRY: entry.encode(),
        HELPER: Path(cavity_longitude.__file__).read_bytes(),
    }


def release(work, *, out=REPORT):
    report = out.with_name("cavity-payload")
    manifest = direct.common.seal(
        report, "prediction-lock.json", ("receiver-source.tar.gz", "package.json")
    )
    package = _read(report / "package.json")
    files = overlay(cavity_payload.read_bundle(report / "receiver-source.tar.gz", package["files"]))
    target = work / "wrapped"
    target.mkdir()
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    script = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from leo.analysis.localization_v4.backend import build_native;"
        "from tools.pipeline_eval.variants.orbit_projector import compile_kernel;"
        "build_native('native');compile_kernel('projector.so')"
    )
    subprocess.run(
        [str(direct.v5_lean.PYTHON), "-IB", "-c", script, str(target)],
        cwd=target,
        env=dict(os.environ, TMPDIR=str(work), **dict.fromkeys(transfer.ENV, "1")),
        check=True,
        timeout=40,
    )
    binaries = {name: _sha(target / name) for name in package["binaries"]}
    if binaries != package["binaries"]:
        raise ValueError("longitude release compiled different numerical C binaries")
    packed = cavity_payload.packed(files)
    (out / "receiver-source.tar.gz").write_bytes(packed)
    return dict(
        parent_archive_sha256=manifest["files"]["receiver-source.tar.gz"],
        archive_sha256=cavity_payload.digest(packed),
        cases=("positive", "far-omitted", "ordinary-in-range"),
        files={key: cavity_payload.digest(value) for key, value in files.items()},
        changed=sorted((REGION, SCAN, ENTRY, HELPER)),
        binaries=binaries,
        native_manifest_sha256=_sha(target / "native/manifest.json"),
        sources={
            str(path.relative_to(direct.common.ROOT)): _sha(path)
            for path in (
                Path(__file__),
                transfer.OBSERVER,
                Path(transfer.__file__),
                REPORT / "PROTOCOL.md",
            )
        },
    )


def synthetic(work):
    inputs = transfer.prior.INPUTS
    _, used = transfer.history_context()
    rng = np.random.default_rng(int.from_bytes(SALT, "big"))
    site = (36.0 + rng.uniform(-0.03, 0.03), 179.98)
    donors, donor_receipts = inputs.empirical.donors()
    snapshots = inputs.snapshots()
    for _ in range(8):
        early, late, anchor = inputs._history(snapshots, used, rng)
        bank = inputs._true_bank(inputs._tle(early), inputs._tle(late), anchor, late["received"])
        try:
            probes, counter, info = inputs.cold._generate_capture(bank, anchor, site, rng)
        except ValueError as error:
            if str(error) != "insufficient visible causal orbit opportunities":
                raise
        else:
            break
    else:
        raise ValueError("dateline synthetic draw lacks visible causal orbital opportunities")
    inputs.empirical._inject(dict(probes=probes, first_counter=counter), donors, rng)
    native = work / "synthetic-native.json"
    ident = "synthetic-dateline"
    complete = transfer.prior.worker.compact.complete_native
    native.write_bytes(encoded(complete(inputs._native(ident, anchor, counter, probes))))
    archive = work / "tle"
    provider = archive / "archive/space-track"
    provider.mkdir(parents=True)
    stamps, paths, inventory = transfer.prior.worker.compact.history_at(anchor, early["sha256"])
    for row in stamps:
        digest = row["sha256"]
        destination = provider / f"{row['collected_utc_ns']}-{digest}.tle"
        if not destination.exists():
            destination.write_bytes(paths[digest].read_bytes())
        if _sha(destination) != digest:
            raise ValueError("causal element bytes differ from collector digest")
    config = work / "track-config.json"
    save_json(config, dict(config=transfer.prior.worker.compact.portable_v5.TRACK_CONFIG))
    shared = dict(
        capture_id=ident,
        native_sha256=_sha(native),
        catalog_sha256=early["sha256"],
        history_sha256=inputs.cold._sha(encoded(stamps)),
        track_config_sha256=_sha(config),
        screen_center=list(SCREEN),
    )
    rows = []
    for name, center in (
        ("positive", (36.02, 179.97)),
        ("far-omitted", _destination(SCREEN, 50.0, np.pi / 2)),
    ):
        tile = inputs._tile(name, center)
        cavity_longitude.validate_geometry(tile["center"], SCREEN, tile["width_km"])
        row = dict(shared, id=name, tile=tile)
        row["input_sha256"] = inputs.cold._sha(encoded(row))
        rows.append((row, native, config, archive, inventory))
    labels = dict(site=site, trajectory=late, emitter_ids=info["emitters"], donors=donor_receipts)
    return rows, labels


def ordinary():
    case, request, binding = direct.input_case("ordinary-DS29-0082")
    job = request["job"]
    row = dict(
        binding,
        capture_id=case["session_id"],
        screen_center=job["screen_center"],
        track_config_sha256=job["track_config"]["sha256"].removeprefix("sha256:"),
    )
    row["tile"] = dict(row["tile"], width_km=25)
    return (
        row,
        Path(case["native_path"]),
        Path(job["track_config"]["path"]),
        Path(job["tle_root"]),
        [],
    )


def snapshots(root):
    return {str(path.relative_to(root)): _sha(path) for path in sorted(root.rglob("*.tle"))}


def run(work, action):
    if action == "stage":
        work.mkdir(parents=True, exist_ok=False)
        source_lock = release(work)
        jobs, labels = synthetic(work)
        jobs.append(ordinary())
        requests = [(r, str(n), str(c), str(t), i) for r, n, c, t, i in jobs]
        save_json(work / "requests.json", requests)
        save_json(work / "private-labels.json", labels)
        save_json(REPORT / "source-lock.json", source_lock)
        seal = dict(
            source_lock_sha256=_sha(REPORT / "source-lock.json"),
            requests_sha256=_sha(work / "requests.json"),
            private_labels_sha256=_sha(work / "private-labels.json"),
            archives={str(path): snapshots(path) for path in {job[3] for job in jobs}},
        )
        save_json(REPORT / "input-lock.json", seal)
        return

    seal = _read(REPORT / "input-lock.json")
    if (
        _sha(REPORT / "source-lock.json") != seal["source_lock_sha256"]
        or _sha(work / "requests.json") != seal["requests_sha256"]
        or _sha(work / "private-labels.json") != seal["private_labels_sha256"]
    ):
        raise ValueError("sealed longitude inference inputs changed")
    lock = _read(REPORT / "source-lock.json")
    if any(_sha(direct.common.ROOT / path) != digest for path, digest in lock["sources"].items()):
        raise ValueError("qualification source differs from its seal")
    if any(snapshots(Path(path)) != wanted for path, wanted in seal["archives"].items()):
        raise ValueError("causal orbit archive differs from its seal")
    root = work / "wrapped"
    files = (
        lock["files"] | lock["binaries"]
        | {"native/manifest.json": lock["native_manifest_sha256"]}
    )
    if any(_sha(root / name) != digest for name, digest in files.items()):
        raise ValueError("staged longitude release differs from its seal")
    raw = _read(work / "requests.json")
    jobs = [(r, Path(n), Path(c), Path(t), i) for r, n, c, t, i in raw]
    for row, native, config, _, _ in jobs:
        if (_sha(native), _sha(config)) != (row["native_sha256"], row["track_config_sha256"]):
            raise ValueError("stored native or RF calibration payload changed")
    with ThreadPoolExecutor(max_workers=2) as pool:
        positive = pool.submit(transfer.capped, work, work, jobs[0], "wrapped", 6)
        negative = pool.submit(transfer.capped, work, work, jobs[1], "wrapped", 7)
        rows = [positive.result(), negative.result()]
        rows.append(transfer.capped(work, work, jobs[2], "wrapped", 6))
    save_json(REPORT / "predictions.json", rows)
    save_json(
        REPORT / "prediction-lock.json",
        {
            name: _sha(REPORT / name)
            for name in ("source-lock.json", "input-lock.json", "predictions.json")
        },
    )
    save_json(REPORT / "synthetic-labels.json", _read(work / "private-labels.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    run(local_output(args.work), args.action)
