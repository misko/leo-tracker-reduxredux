"""Freeze disjoint detector calibration and prepare blind complete compact fits."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from . import cascade_audit_trial as cascade
from . import fast_calibration_model as model
from . import one_lane_roster as roster
from . import support_cross_trial as compact
from . import two_rate_holdout_trial as paired
from .full_v5_check import BULK, _sha
from .phase_support_results import pack

REPORT = cascade.fixed.SCREEN / "original-schedule/fast-calibration"
WORK = Path("/var/tmp/leo-fast-calibration-20261120")
SALT = "fast-calibration-recording-split-v1"
EDGES = ("lower", "upper")


def ranking(ident, meta):
    return sha256(encoded([SALT, ident, meta["manifest"]])).digest()


def split(metadata):
    dev, held, reverse = {}, {}, []
    for edge in EDGES:
        ordered = sorted(
            [ident for ident, data in metadata.items() if data["edge"] == edge],
            key=lambda ident: ranking(ident, metadata[ident]),
        )
        if len(ordered) < 7:
            raise ValueError(f"not enough disjoint {edge} recordings for calibration")
        held[edge], dev[edge] = ordered[:3], ordered[3:7]
        reverse.append(ordered[0])
    return dict(development=dev, held=held, reverse=reverse)


def fast(ident, archives, binds, extensions):
    case, request = roster.bind(ident, extensions)
    bound = dict(
        zip(
            cascade.fixed.BINDINGS,
            (
                case["native"]["sha256"],
                case["request"]["sha256"],
                case["catalog"]["sha256"],
                case["regions"][0],
            ),
            strict=True,
        )
    )
    if bound != binds[ident]:
        raise ValueError("fast factors do not bind the original matched request")
    doc = roster.stock_document(archives[ident])
    prov = doc["provenance"]
    if (
        doc["provenance"]["detector_sha256"] != "sha256:" + roster.STOCK_SHA
        or doc["source"]["session_id"] != case["session_id"]
        or prov["window_count"] != case["recording"]["window_count"]
        or prov["processed_windows"] + len(prov["excluded_windows"]) != prov["window_count"]
        or len(doc["source"]["probes"]) != 2 * prov["processed_windows"]
    ):
        raise ValueError("a fast archive is not the full authentic four-region capture")
    return case, request, doc


def original(case):
    bound = case["native"]
    path = whole_iq.checked(BULK / bound["path"], bound["sha256"])
    return whole_iq.read(path)


def source_paths():
    return {str(p): _sha(p) for p in (Path(__file__), Path(model.__file__), REPORT / "PROTOCOL.md")}


def freeze(work):
    if work.exists() or (REPORT / "model-lock.json").exists():
        raise FileExistsError("use a previously unused calibration scope")
    work.mkdir(mode=0o755)
    groups, archives, bindings, extensions, release = roster.inventory()
    metadata = {}
    for ident in groups["reconstructed"]:
        doc = roster.stock_document(archives[ident])
        edge = doc["source"]["probes"][0]["edge"]
        manifest = doc["source"]["input_manifest_sha256"]
        metadata[ident] = dict(edge=edge, manifest=manifest)
    if len({x["manifest"] for x in metadata.values()}) != len(metadata):
        raise ValueError("development and held must have distinct physical capture manifests")
    panel = split(metadata)
    save_json(
        REPORT / "cohort-lock.json",
        dict(panel=panel, metadata_only_selection=metadata, salt=SALT, sources=source_paths()),
    )
    development = [i for edge in EDGES for i in panel["development"][edge]]
    train, census = {}, {}
    for ident in development:
        case, _, doc = fast(ident, archives, bindings, extensions)
        train[ident], census[ident] = model.pairs(ident, doc, original(case))
        print("development", ident, len(train[ident]), "literal winners", flush=True)
    selected, models, folds, loss = model.choose(train)
    rows = [r for group in train.values() for r in group]
    pack(REPORT / "training-pairs.jsonl.gz", rows)
    frozen = dict(
        panel=panel,
        source_paths=source_paths(),
        cohort_sha256=_sha(REPORT / "cohort-lock.json"),
        models=models,
        selected=selected,
        cross_validation_median_abs_hz=folds,
        mean_cv_median_abs_hz=loss,
        counts=census,
        training_pairs_sha256=_sha(REPORT / "training-pairs.jsonl.gz"),
        sources={i: dict(fast=archives[i], binding=bindings[i]) for i in development},
        stock_release=release,
    )
    save_json(REPORT / "model-lock.json", frozen)
    save_json(work / "model-lock.json", frozen)
    print("frozen", selected, models[selected], "blind hold", panel["held"], flush=True)


def frozen_model(work):
    freeze_path = REPORT / "model-lock.json"
    doc = whole_iq.read(whole_iq.checked(work / freeze_path.name, _sha(freeze_path)))
    for path, digest in doc["source_paths"].items():
        whole_iq.checked(Path(path), digest)
    whole_iq.checked(REPORT / "cohort-lock.json", doc["cohort_sha256"])
    whole_iq.checked(REPORT / "training-pairs.jsonl.gz", doc["training_pairs_sha256"])
    return doc


def prepare(work):
    rule = frozen_model(work)
    groups, archives, bindings, extensions, release = roster.inventory()
    if rule["stock_release"] != release:
        raise ValueError("deployed compact release changed after calibration")
    roster.check_release(release)
    optimum = rule["models"][rule["selected"]]
    outputs, inputs = [], {}
    # Interleave the two physical edges before optional sign jobs.
    held = [
        i
        for pair in zip(*(rule["panel"]["held"][edge] for edge in EDGES), strict=True)
        for i in pair
    ]
    for ident in held:
        case, request, old = fast(ident, archives, bindings, extensions)
        inputs[ident] = dict(archive=archives[ident], binding=bindings[ident])
        for policy, sign in (("corrected", 1), ("reverse", -1)):
            if policy == "reverse" and ident not in rule["panel"]["reverse"]:
                continue
            before = process_time_ns()
            doc, n = model.apply(old, optimum, sign)
            cpu_ns = process_time_ns() - before
            lineage = whole_iq.recording.digest(
                [SALT, _sha(REPORT / "model-lock.json"), sign, archives[ident]["native_sha256"]]
            )
            doc["source"]["analysis_manifest_sha256"] = lineage
            doc["provenance"] = dict(
                doc["provenance"],
                scope="Fast-only complete four-region factors with frozen CFO correction",
                run_id="fast-cal-" + lineage[7:32],
            )
            doc["provenance"].pop("detector_sha256")
            row = paired.prepare(
                work,
                ident,
                case,
                request,
                encoded(doc) + b"\n",
                bindings[ident],
                release,
                policy,
                calibration_cpu_ns=cpu_ns,
                changed_candidates=n,
            )
            row["method"] = "fast_calibration_" + policy
            outputs.append(row)
        print(ident, "fast-only output prepared", flush=True)
    outputs.sort(key=lambda r: r["condition"] != "corrected")
    seal = dict(
        cases=held,
        inputs=inputs,
        jobs=outputs,
        release=release,
        model_sha256=_sha(REPORT / "model-lock.json"),
    )
    for p in (work / "prediction-plan.json", REPORT / "prediction-plan.json"):
        save_json(p, seal)


def plan(work):
    frozen_model(work)
    p = work / "prediction-plan.json"
    value = whole_iq.read(whole_iq.checked(p, _sha(REPORT / p.name)))
    if value["model_sha256"] != _sha(REPORT / "model-lock.json"):
        raise ValueError("held workload used a different calibration model")
    return value


def run(work, cpus, mode, only=None):
    value = plan(work)
    roster.check_release(value["release"])
    jobs = [
        r for r in value["jobs"] if r["condition"] == mode and (only is None or r["id"] in only)
    ]
    if not jobs or len(cpus) != len(set(cpus)):
        raise ValueError("choose nonempty jobs and distinct authorized CPU assignments")
    if only is not None and {r["id"] for r in jobs} != set(only):
        raise ValueError("requested case not bound to this fit branch")

    def assigned(index_cpu):
        index, cpu = index_cpu
        for row in jobs[index :: len(cpus)]:
            path = work / row["id"] / mode / "fit.json"
            if path.exists():
                continue
            result = compact.service(work, dict(row, cpu=cpu))
            save_json(path, result)
            print(row["id"], mode, cpu, result["terminal"], flush=True)

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        list(pool.map(assigned, enumerate(cpus)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "prepare", "run"))
    p.add_argument("work", type=local_output, nargs="?", default=WORK)
    p.add_argument("--cpus", type=int, nargs="+")
    p.add_argument("--only", nargs="+")
    p.add_argument("--mode", choices=("corrected", "reverse"), default="corrected")
    args = p.parse_args()
    if args.action == "run":
        if not args.cpus:
            p.error("run needs an explicitly authorized CPU list")
        run(args.work, args.cpus, args.mode, args.only)
    else:
        dict(freeze=freeze, prepare=prepare)[args.action](args.work)
