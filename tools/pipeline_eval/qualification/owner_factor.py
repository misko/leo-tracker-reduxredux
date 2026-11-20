"""Run fixed-owner factors with a sealed blind association and privileged refit."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, references, save_json, write
from ..scoring import ARMS, distance_km
from ..variants.v5_lean import SOURCE
from . import owner_factor_archive as archive
from . import robust_orbit_fit_trials as parent
from .fresh_scenes import _new, _read, _sandbox, _sha
from .robust_em_trials import load

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/owner-model"
CASES = ("DS26-0197", "DS26-0223", "DS29-0316", "DS26-0036")
WORKERS = {4, 5}
BOUND_S = 110
FILE = "predictions.jsonl.gz"
RESIDUALS = "residuals.jsonl.gz"
WORKER = """
import json
import sys
from tools.pipeline_eval.qualification import owner_factor_models as model

packet = json.load(sys.stdin)
result = model.blind(packet) if sys.argv[1] == 'blind' else model.refit(**packet)
json.dump(result, sys.stdout, allow_nan=False)
"""


def sources():
    baseline = parent.locked_sources()
    if baseline != _read(parent.OUTPUT / "source-lock.json"):
        raise ValueError("locked exact-fit control changed")
    local = Path(__file__).parent
    paths = (
        REPORT / "PROTOCOL.md",
        Path(__file__),
        *(
            local / f"{name}.py"
            for name in (
                "owner_factor_archive",
                "owner_factor_models",
                "robust_em_trials",
                "robust_orbit_fit_diagnostic",
                "joint_orbits_worker",
                "fresh_scenes",
                "v5_postfit",
                "v5_prefix_audit",
            )
        ),
        corpus.FROZEN / "provenance.json",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    )
    v5 = SOURCE / "leo/analysis"
    return {
        "baseline": baseline,
        "cases": list(CASES),
        "files": {str(p.resolve().relative_to(ROOT)): _sha(p) for p in paths},
        "v5_design": {
            name: _sha(v5 / name)
            for name in (
                "localization_v3/marginal.py",
                "localization_v3/history_position.py",
                "localization_v3/retained_position.py",
                "localization_v3/noise.py",
                "research/retained_track_likelihood.py",
            )
        },
    }


def _namespace(stage, request, cpu):
    cmd = _sandbox(cpu)
    cmd[-1:] = [WORKER, stage]
    try:
        response = subprocess.run(
            cmd,
            input=encoded(request),
            capture_output=True,
            check=True,
            timeout=BOUND_S,
        )
    except subprocess.CalledProcessError as err:
        raise ValueError(err.stderr.decode(errors="replace")[-2800:]) from None
    return json.loads(response.stdout)


def _serial(path, rows):
    content = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    with path.open("xb") as stream:
        stream.write(content)


def _load(path):
    with gzip.open(path, "rt") as stream:
        return list(map(json.loads, stream))


def _schedule(fn):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= WORKERS:
        raise ValueError("use assigned CPU4 and CPU5")

    def lane(i):
        return [fn(case, cpus[i]) for case in CASES[i :: len(cpus)]]

    with ThreadPoolExecutor(len(cpus)) as pool:
        return [row for group in pool.map(lane, range(len(cpus))) for row in group]


def blind(root, cache):
    root.mkdir(mode=0o700)
    _new(root / "source-lock.json", sources())

    def one(case, cpu):
        packet, bindings = load(case, "matched-tile", cache)
        fit = _namespace("blind", packet, cpu)
        print(case, "blind exact fit sealed", flush=True)
        return dict(case=case, packet=packet, bindings=bindings, **fit)

    rows = _schedule(one)
    _serial(root / "blind-input-and-owners.jsonl.gz", rows)
    _new(
        root / "blind-lock.json",
        dict(
            inputs_sha256=_sha(root / "blind-input-and-owners.jsonl.gz"),
            source_lock_sha256=_sha(root / "source-lock.json"),
        ),
    )


def _blind(root):
    lock = _read(root / "blind-lock.json")
    blind_rows = root / "blind-input-and-owners.jsonl.gz"
    if (
        _sha(blind_rows) != lock["inputs_sha256"]
        or _sha(root / "source-lock.json") != lock["source_lock_sha256"]
        or _read(root / "source-lock.json") != sources()
    ):
        raise ValueError("blind owners or numerical source changed")
    return {row["case"]: row for row in _load(blind_rows)}


def privileged(root):
    rows = _blind(root)

    def prepare(case, _):
        factors, priors, model, receipts, endpoint = archive.load_archive(case)
        return dict(
            case=case,
            factors=factors,
            priors=priors,
            model=model,
            receipt=receipts,
            archived=endpoint,
        )

    bound = _schedule(prepare)
    _serial(root / "privileged-inputs.jsonl.gz", bound)
    _new(
        root / "input-lock.json",
        dict(
            privileged_sha256=_sha(root / "privileged-inputs.jsonl.gz"),
            blind_lock_sha256=_sha(root / "blind-lock.json"),
        ),
    )
    reference = {v["case"]: v for v in bound}

    def fit(case, cpu):
        data = reference[case]
        request = dict(
            packet=rows[case]["packet"],
            owned=data["factors"],
            chosen=rows[case]["rows"],
            priors=data["priors"],
            model=data["model"],
        )
        result = _namespace("fit", request, cpu)
        print(case, "fixed-owner and clock fits sealed", flush=True)
        return case, result

    predictions, residuals = [], []
    for case, result in _schedule(fit):
        witness = rows[case]
        predictions.append(
            dict(
                id=case,
                counts=result["counts"],
                blind_exact=witness["result"],
                estimates=result["estimates"],
                bindings=witness["bindings"],
                source_receipt=reference[case]["receipt"],
                archived_v5=reference[case]["archived"],
                prior_model=reference[case]["model"],
                phase_priors=reference[case]["priors"],
            )
        )
        residuals.extend(dict(case=case, **r) for r in result["residuals"])
    _serial(root / FILE, predictions)
    _serial(root / RESIDUALS, residuals)
    _new(
        root / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(root / "input-lock.json"),
            source_lock_sha256=_sha(root / "source-lock.json"),
            cases=list(CASES),
            files={name: _sha(root / name) for name in (FILE, RESIDUALS)},
        ),
    )


def score(root, output):
    lock = _read(root / "prediction-lock.json")
    names = FILE, RESIDUALS
    if (
        _sha(root / "input-lock.json") != lock["input_lock_sha256"]
        or _sha(root / "source-lock.json") != lock["source_lock_sha256"]
        or any(_sha(root / file) != lock["files"][file] for file in names)
    ):
        raise ValueError("unsealed predictions are ineligible for geographic scoring")
    refs = {}
    for panel, case_group in (
        ("ds26-common127", [c for c in CASES if c.startswith("DS26")]),
        ("roof16", [c for c in CASES if c.startswith("DS29")]),
    ):
        refs.update((r["id"], r) for r in references(panel, case_group)[1])
    summaries = []
    for trial in _load(root / FILE):
        case = trial["id"]
        truth = refs[case]["truth"]
        for arm in ARMS:
            archived = trial["archived_v5"][arm]
            if (
                distance_km(
                    archived["endpoint_latlon"], refs[case]["reference"]["baseline"][arm]["latlon"]
                )
                > 1e-6
            ):
                raise ValueError("archived reference differs from original v5 endpoint")
            summaries.append(
                dict(
                    case=case,
                    arm=arm,
                    cell="archived_v5",
                    source="published_archive",
                    error_km=distance_km(archived["endpoint_latlon"], truth),
                    **archived,
                )
            )
            for cell, record in {"blind_exact": trial["blind_exact"], **trial["estimates"]}.items():
                estimate = record["arms"][arm]
                coord = estimate.get("forced_latlon") or estimate.get("latlon")
                summaries.append(
                    dict(
                        case=case,
                        arm=arm,
                        cell=cell,
                        source="blind_receiver"
                        if cell == "blind_exact"
                        else "privileged_diagnostic",
                        status=record["status"],
                        reason=record["reason"],
                        published_latlon=estimate.get("latlon"),
                        endpoint_latlon=coord,
                        error_km=distance_km(coord, truth),
                        residual_rms_hz=estimate.get("rf_rms_hz"),
                        points=estimate.get("points"),
                        groups=estimate.get("groups"),
                    )
                )
    for name in (
        "source-lock.json",
        "blind-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        *names,
    ):
        write(output / name, (root / name).read_bytes())
    save_json(output / "scores.json", summaries)


def main():
    command = argparse.ArgumentParser(description=__doc__)
    tasks = command.add_subparsers(dest="action", required=True)
    for name in ("blind", "privileged", "score"):
        p = tasks.add_parser(name)
        p.add_argument("root", type=Path)
        if name == "blind":
            p.add_argument("--cache", type=Path, required=True)
        if name == "score":
            p.add_argument("--out", type=Path, default=REPORT)
    args = command.parse_args()
    if args.action == "blind":
        blind(args.root, args.cache)
    elif args.action == "privileged":
        privileged(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
