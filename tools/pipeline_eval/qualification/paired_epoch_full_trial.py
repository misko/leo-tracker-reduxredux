"""Score two full reserve IQ recordings with shared versus own-channel epoch proposals."""

import argparse
import gzip
import json
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km
from . import whole_band_results as base
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = base.REPORT.with_name("paired-epochs-full")
CASES = ("DS26-0122", "DS29-0247")
UNION = "shared_epoch_full_iq"
DIGEST = "d94af0e2b863c10c7de282f96d39b056b83860a235179dff86b500d0e0866eb6"
LIBRARY = Path("/srv/bulk/leo-dev/20261119-paired-epochs/out/libleo-adaptive-detector.so")


def lock(parent, library):
    published = base.REPORT / "source-lock.json"
    whole_iq.checked(parent / "study.json", _sha(published))
    plan = whole_iq.read(published)
    whole_iq.checked(library, DIGEST)
    build = REPORT.with_name("paired-epochs") / "build.json"
    artifact = whole_iq.read(build)
    if (
        artifact["sha256"] != DIGEST
        or artifact["wide_sha256"] != plan["detectors"]["wide"]["sha256"]
    ):
        raise ValueError("dual-channel candidate differs from its real compiled release")
    return dict(
        plan,
        cases={k: plan["cases"][k] for k in CASES},
        detectors=dict(union=dict(path=str(library), sha256=DIGEST)),
        parent_sha256=_sha(published),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        build_sha256=_sha(build),
    )


def run(parent, work, case):
    pins = whole_iq.read(work / "study.json")
    if pins != lock(parent, Path(pins["detectors"]["union"]["path"])):
        raise ValueError("predeclared union inputs changed")
    if not all((parent / case / arm / "service.json").is_file() for arm in ("wide", "narrow")):
        raise ValueError("same-core frequency range trial still in progress")
    detector = pins["detectors"]["union"]
    (work / case).mkdir(exist_ok=False)
    try:
        whole_iq.evaluate(
            case,
            Path(detector["path"]),
            detector["sha256"],
            parent / "receiver",
            work / case / "union",
            pins["cases"][case]["cpus"],
            pins["limit_s"],
        )
    except (RuntimeError, OSError, ValueError) as error:
        save_json(work / case / "union-failure.json", dict(error=str(error)))
        raise


def seal(work):
    pins = whole_iq.read(REPORT / "source-lock.json")
    if pins != whole_iq.read(work / "study.json"):
        raise ValueError("recording or detector selection differs from prelaunch seal")
    authority = base.REPORT / "prediction-lock.json"
    parent_lock = whole_iq.read(authority)
    for name in ("positions.jsonl.gz", "resources.json", "source-lock.json"):
        whole_iq.checked(base.REPORT / name, parent_lock["files"][name])
    parent_rows = list(
        map(
            json.loads,
            gzip.decompress((base.REPORT / "positions.jsonl.gz").read_bytes()).splitlines(),
        )
    )
    controls = {
        r["id"]: r for r in parent_rows if r["id"] in CASES and r["method"] == base.METHOD["wide"]
    }
    parent_resources = whole_iq.read(base.REPORT / "resources.json")
    rows, stats, files = [], {}, []
    for case in CASES:
        row, measured, native = base.attempt(work, case, "union", pins, method=UNION)
        prior = parent_resources[case]["wide"]
        if native is not None and "raw_authority" in prior:
            base.pair_geometry(measured, prior)
        if native is not None:
            f = REPORT / "native" / (case + ".json.gz")
            write(f, gzip.compress(native.read_bytes(), compresslevel=6, mtime=0))
            files.append(str(f.relative_to(REPORT)))
        rows.extend((row, controls[case]))
        stats[case] = {"union": measured, "wide": prior}
    pack(REPORT / "positions.jsonl.gz", rows)
    save_json(REPORT / "resources.json", stats)
    files.extend(("positions.jsonl.gz", "resources.json", "source-lock.json"))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            parent_sha256=_sha(authority),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


def score():
    pins = whole_iq.read(REPORT / "prediction-lock.json")
    for k, digest in pins["files"].items():
        whole_iq.checked(REPORT / k, digest)
    _, refs = held_references(None, CASES)
    truth = {r["id"]: r for r in refs}
    rows = list(
        map(json.loads, gzip.decompress((REPORT / "positions.jsonl.gz").read_bytes()).splitlines())
    )
    stats = whole_iq.read(REPORT / "resources.json")
    scores = []
    for row in rows:
        ident = row["id"]
        reference = truth[ident]
        branch = "union" if row["method"] == UNION else "wide"
        for arm in ARMS:
            value = row["result"]["arms"][arm]
            error = (
                distance_km(reference["truth"], value["latlon"])
                if value["latlon"] is not None
                else None
            )
            v5 = reference["reference"]["baseline"][arm]["error_km"]
            scores.append(
                dict(
                    id=ident,
                    branch=branch,
                    arm=arm,
                    status=row["result"]["status"],
                    error_km=error,
                    original_v5_km=v5,
                    within_10pct=error is not None and error <= 1.1 * v5,
                    conditional_rms_hz=value.get("rf_rms_hz"),
                    wall_s=stats[ident][branch].get("wall_s"),
                    cpu_s=stats[ident][branch].get("cpu_s"),
                )
            )
    csv_file(REPORT / "scores.csv", scores)
    files = ("positions.jsonl.gz", "prediction-lock.json", "resources.json", "scores.csv")
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CASES), files={n: _sha(REPORT / n) for n in files}),
    )
    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="paired-epochs-full",
                    method=UNION,
                    scope="roof",
                    cases=list(CASES),
                    title="Sharing pilot start proposals across simultaneous receivers",
                    caption=(
                        "Two complete reserve IQ recordings. Each wideband detector scores the two "
                        "channels independently. The candidate also tests pilot start times "
                        "proposed by the second receiver."
                    ),
                    seal="figure-lock.json",
                    provenance=["resources.json", "scores.csv", "prediction-lock.json"],
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file="positions.jsonl.gz",
                            value=value,
                            native_authority="ordinary",
                            native_field="paired_ordinary_sha256",
                            **(
                                {
                                    "match": [
                                        "tile",
                                        "catalog_sha256",
                                        "original_request_sha256",
                                        "mode",
                                    ]
                                }
                                if key == "stock"
                                else {}
                            ),
                        )
                        for key, label, value in (
                            ("one", "Both channels propose", UNION),
                            ("stock", "Each channel proposes", base.METHOD["wide"]),
                        )
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("bind", "run", "seal", "score"))
    p.add_argument("parent", type=local_output)
    p.add_argument("work", type=local_output)
    p.add_argument("--case", choices=CASES)
    p.add_argument("--library", type=Path, default=LIBRARY)
    args = p.parse_args()
    if args.action == "bind":
        pins = lock(args.parent, args.library.resolve())
        args.work.mkdir(exist_ok=False, parents=True)
        save_json(args.work / "study.json", pins)
    elif args.action == "run" and args.case:
        run(args.parent, args.work, args.case)
    elif args.action == "seal":
        seal(args.work)
    elif args.action == "score":
        score()
    else:
        p.error("run needs --case")
