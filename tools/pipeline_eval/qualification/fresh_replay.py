"""Freeze and run stock and genuine fifth-center on new complete roof recordings."""

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from .. import corpus, iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES
from ..variants import v5_lean
from ..variants.iq_stream import _read_prefix
from . import capture_release, whole_center_union_raw, whole_fftw_raw
from . import differential_runtime as runtime
from . import whole_center_union as union
from . import whole_center_union_candidate as activated
from .full_v5_check import BULK, _sha

REPORT = union.SCREEN / "arrival-and-timing/fresh-replay"
WORK = Path("/var/tmp/leo-fresh-replay-20261119")
MODULE = "tools.pipeline_eval.qualification.fresh_replay"
DS29 = BULK / "leo-dev/ds29-20261113/snapshot"
MANIFEST_SHA = "b9b7dfc497f1df45e913e175be9b9471b1e0b49eab601f0aeff640c5c05c61a8"
TRUTH_SHA = "e45b0db0c1e9106a50d746bca5580e6d2911330132303c2a573284254f074f21"
ROOF_SHA = "6a23af641fff9db12cc0ec5710b27f0cd20dc7980b7ac645f46ec778261dab91"
ROOF_PLAN = Path("/home/mouse9911/.cache/accuracy-repair-20261115/one-track-plan.json")
SCIENCE = v5_lean.RUNNER.parents[1] / "plans/science.json"
SCIENCE_SHA = "274b772339b88495142e18e5d00ecd13dd93084e2e6d6287b1598b6e4a61c2f3"
METHOD = "fresh_replay_fifth"
CONTROL = "fresh_replay_stock"
CPUS = {"DS26": [4, 5], "DS29": [6, 7]}


def original_manifest():
    science = whole_iq.read(whole_iq.checked(SCIENCE, SCIENCE_SHA))
    broad = whole_iq.read(whole_iq.checked(ROOF_PLAN, ROOF_SHA))
    if any(science[key] != broad[key] for key in ("source", "native_manifest", "python")):
        raise ValueError("historical DS29 snapshot uses a different v5 deployment")
    if tuple(science["roles"]) != ROLES or Path(broad["cohorts"]["DS29"]["snapshot"]) != DS29:
        raise ValueError("missing original four-policy scientific plan on this snapshot")
    return dict(science, cohorts={"DS29": broad["cohorts"]["DS29"]})


def excluded():
    sources = union.history()
    for path in (
        union.REPORT / "source-lock.json",
        union.REPORT.with_name("fifth-crossover") / "source-lock.json",
        union.SCREEN / "track-recovery/wide-roster/roster-lock.json",
    ):
        doc = whole_iq.read(path)
        cases = sorted(doc["primary"]) if "primary" in doc else union.exact_wide_iq.scheduled(doc)
        sources[str(path.relative_to(union.SCREEN))] = dict(cases=cases, sha256=_sha(path))
    cases = {ident for row in sources.values() for ident in row.get("cases", [])}
    return cases, sources


def archive_ok(case):
    # Only metadata and physical member lengths are probed before selection.
    capture = capture_release.read_capture(case)
    files = []
    for segment in case["recording"]["segments"]:
        manifest = BULK / segment["path"]
        opened = json.loads(_read_prefix(manifest, 65536))
        for chunk in opened["chunks"]:
            for file, size in (
                ("payload_relative_path", "compressed_bytes"),
                ("index_relative_path", "index_bytes"),
            ):
                path = (manifest.parent / chunk[file]).resolve()
                if not path.is_relative_to(manifest.parent.resolve()):
                    raise ValueError("archive chunk escapes its signed segment")
                files.append((str(path), chunk[size]))
    verify = (
        "import json,os,stat,sys\n"
        "for p,n in json.load(sys.stdin):\n"
        " s=os.stat(p,follow_symlinks=False)\n"
        " if not stat.S_ISREG(s.st_mode) or s.st_size!=n or not os.access(p,os.R_OK):\n"
        "  raise ValueError(p)\n"
    )
    status = subprocess.run(
        ["sudo", "-n", "-u", "leo", "--", sys.executable, "-B", "-c", verify],
        input=json.dumps(files),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if status.returncode:
        raise ValueError(
            "declared waveform chunk or index is missing or truncated: " + status.stderr[-500:]
        )
    return capture, len(files)


def shortlist(rows, rejected, ledger, group):
    for _, ident, case in sorted(rows, key=lambda row: (row[0], row[1])):
        entry = ledger[ident]
        try:
            seal, files = archive_ok(case)
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            entry.update(state="archive unavailable", reason=str(error))
            rejected.append(ident)
            continue
        entry.update(state="selected", checked_files=files, capture=seal)
        return case, seal
    raise ValueError(f"no new eligible complete {group} recording")


def ds26_roster(exclusions):
    ids, digests = corpus._selection("ds26-common127")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", digests))
    role_arms = {
        (row["id"], row["method"], row["arm"])
        for row in csv.DictReader(io.StringIO(corpus._read_frozen("scores.csv", digests).decode()))
        if row["status"] == "fix" and row["latitude_deg"] and row["longitude_deg"]
    }
    ranked, ledger = [], {}
    for ident in ids:
        case = inputs[ident]
        segment = (case.get("recording") or {}).get("segments", [])
        digest = segment[0]["sha256"] if segment else None
        if ident in exclusions:
            state = "earlier whole-IQ roster"
        elif not segment or case.get("unavailable"):
            state = "case lacks frozen complete recording"
        elif any((ident, role, arm) not in role_arms for role in ROLES for arm in ARMS):
            state = "original reference arm unavailable"
        else:
            state = "metadata eligible"
            ranked.append((digest, ident, case))
        ledger[ident] = dict(state=state, first_manifest_sha256=digest)
    return ranked, ledger


def ds29_roster(exclusions):
    manifest = whole_iq.read(whole_iq.checked(DS29 / "dataset-manifest.json", MANIFEST_SHA))
    science = original_manifest()
    inventory = whole_iq.read(DS29 / "inventory.json")
    site = whole_iq.read(whole_iq.checked(DS29 / "site-audit.json", inventory["site_audit_sha256"]))
    if inventory["dataset_manifest_sha256"] != "sha256:" + MANIFEST_SHA:
        raise ValueError("DS29 site inventory does not bind the frozen dataset")
    allowed = {r["dataset_label"] for r in site["members"] if r["authority_eligible"]}
    old = {r["dataset_label"]: r for r in science["cohorts"]["DS29"]["members"]}
    if old != {r["dataset_label"]: r for r in inventory["members"]}:
        raise ValueError("original v5 plan differs from frozen DS29 inventory")
    ranked, ledger = [], {}
    for member in manifest["members"]:
        ident = member["dataset_label"]
        ref = old[ident]
        raw = member["raw_recording"]["segments"]
        digest = raw[0]["sha256"].removeprefix("sha256:") if raw else None
        state = "metadata eligible"
        if ident in exclusions:
            state = "earlier whole-IQ roster"
        elif ident not in allowed:
            state = "outside documented operator roof authority"
        elif not raw or ref["availability"] != "available" or not ref.get("causal_snapshots"):
            state = "no complete archived original native or causal input"
        else:
            case = dict(
                id=ident,
                run_id=ref["run_id"],
                session_id=ref["session_id"],
                recording=dict(
                    segments=[
                        dict(
                            path=str(Path(s["path"]).relative_to(BULK)),
                            sha256=s["sha256"].removeprefix("sha256:"),
                        )
                        for s in raw
                    ],
                    window_count=member["window_count"],
                ),
            )
            try:
                capture_release.producer(
                    case,
                    dict(edge="upper", input_manifest_sha256=ref["source_sha256"]),
                )
            except ValueError:
                state = "capture producer unavailable"
            else:
                ranked.append((digest, ident, case))
        ledger[ident] = dict(state=state, first_manifest_sha256=digest)
    return ranked, ledger


def original_requests(work, case):
    manifest = original_manifest()
    manifest["output"] = str(work)
    with patch.object(sys, "path", [str(v5_lean.RUNNER), *sys.path]):
        import evaluate_accuracy_repair as published

    if Path(published.__file__).parent != v5_lean.RUNNER:
        raise ValueError("historical v5 request builder differs")
    whole_iq.checked(Path(published.__file__), v5_lean.RUNNER_SHA256)
    assignment = dict(case=case["id"], dataset="DS29", repetition=0)
    requests = {}
    for role in ROLES:
        request = published.worker_request(manifest, assignment, role)
        published.check_scientific_inputs(request)
        out = work / "original-requests" / f"{role}.json"
        save_json(out, request)
        requests[role] = dict(path=str(out), sha256=_sha(out))
    request = whole_iq.read(Path(requests["baseline"]["path"]))
    job = request["job"]
    path = Path(job["native_input"]["path"])
    latest = max(request["causal_snapshots"], key=lambda name: int(name.split("-")[0]))
    (catalog,) = Path(job["tle_root"]).rglob(latest)
    selected = dict(
        case,
        panel="DS29",
        regions=[dict(id="original", center=job["search_center"])],
        native=dict(path=str(path.relative_to(BULK)), sha256=job["native_input"]["sha256"][7:]),
        request=dict(path=requests["baseline"]["path"], sha256=requests["baseline"]["sha256"]),
        catalog=dict(path=str(catalog.relative_to(BULK)), sha256=_sha(catalog)),
    )
    return selected, request, requests


def freeze(work):
    dest = REPORT / "source-lock.json"
    if dest.exists():
        raise FileExistsError(dest)
    work.mkdir(parents=True, exist_ok=False)
    omitted, history = excluded()
    plans, roster = {}, {}
    requests = {}
    for group, provider in (("DS26", ds26_roster), ("DS29", ds29_roster)):
        ranked, ledger = provider(omitted)
        skipped = []
        case, capture = shortlist(ranked, skipped, ledger, group)
        if group == "DS29":
            case, request, requests = original_requests(work, case)
        else:
            case, request = whole_iq.binding(case["id"])
        ident = case["id"]
        plans[ident] = dict(
            id=ident,
            cpus=CPUS[group],
            cohort="fresh saved IQ",
            case=case,
            first="control" if group == "DS26" else "candidate",
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            tile=case["regions"][0],
            clock_authority=capture["input_manifest_sha256"],
            recording=case["recording"],
            orbit_snapshots=request["causal_snapshots"],
        )
        roster[group] = dict(
            cases=ledger,
            ranked=[ident for _, ident, _ in sorted(ranked)],
            rejected_on_archive=skipped,
            selected=ident,
        )
        print(group, ident, capture["edge"], case["recording"]["window_count"], flush=True)
    save_json(
        REPORT / "selection.json", dict(roster=roster, earlier=history, excluded=sorted(omitted))
    )
    base, active = activated.candidate_lock(union.WORK)
    target = work / "runtime"
    target.mkdir()
    assets = {}
    for role, source in [("control", base["detectors"]["control"]), *active["assets"].items()]:
        path = Path(source["path"])
        assets[role] = activated.copy_checked(path, target / path.name, source["sha256"])
    programs = (
        base["programs"]
        | active["sources"]
        | {
            str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__)),
        }
    )
    pins = dict(
        cases=plans,
        original_requests=requests,
        programs=programs,
        receiver=base["receiver"],
        receiver_files=base["receiver_files"],
        native_sources=base["native_sources"],
        detectors=assets,
        memory_max=base["memory_max"],
        swap_max=0,
        limit_s=450,
        stock_source_sha256=_sha(union.REPORT / "source-lock.json"),
        activated_source_sha256=_sha(union.REPORT / activated.PIN),
        selection_sha256=_sha(REPORT / "selection.json"),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        ds29_source={
            name: _sha(DS29 / name)
            for name in ("dataset-manifest.json", "inventory.json", "site-audit.json")
        },
    )
    save_json(work / "source-lock.json", pins)
    save_json(dest, pins)


def source(work):
    report = REPORT / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(work / report.name, _sha(report)))
    whole_iq.checked(REPORT / "selection.json", plan["selection_sha256"])
    whole_iq.checked(REPORT / "PROTOCOL.md", plan["protocol_sha256"])
    for name, digest in plan["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    for entry in plan["detectors"].values():
        whole_iq.checked(Path(entry["path"]), entry["sha256"])
    return plan


def local_case(plan, ident):
    row = plan["cases"][ident]["case"]
    whole_iq.checked(BULK / row["request"]["path"], row["request"]["sha256"])
    return row


def patched_case(plan):
    return patch.multiple(whole_iq, _load_case=lambda ident: local_case(plan, ident))


def hinted(plan):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=plan["detectors"]["candidate"]["sha256"],
        differential_runtime_raw=whole_center_union_raw,
        source_identity=lambda: dict(plan["programs"]),
    )


def run(work, ident):
    plan = source(work)
    first = plan["cases"][ident]["first"]
    with patched_case(plan):
        for role in (first, "candidate" if first == "control" else "control"):
            if role == "candidate":
                with hinted(plan):
                    union.service(work, ident, role, plan, evaluator=runtime.evaluate)
            else:
                with (
                    patch.object(whole_iq, "MODULE", MODULE),
                    patch.object(iq_service, "MODULE", MODULE),
                ):
                    union.service(work, ident, role, plan, evaluator=whole_iq.evaluate)


def worker(path):
    plan = source(path.parents[1])
    with (
        patched_case(plan),
        patch.object(
            whole_iq.recording,
            "_load_case",
            lambda ident: local_case(plan, ident),
        ),
    ):
        if path.name == "candidate":
            whole_fftw_raw.library(Path(plan["detectors"]["candidate"]["path"]))
            with hinted(plan):
                runtime.worker(path)
        else:
            whole_iq.worker(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "worker", "run"))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.work)
    elif args.mode == "worker":
        worker(args.attempt)
    elif args.case:
        run(args.work, args.case)
    else:
        parser.error("a paired run requires --case")
