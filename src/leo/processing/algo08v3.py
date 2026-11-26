"""Run and publish the pinned ALGO08v3 release for one sealed recording."""

import fcntl
import json
import shutil
import subprocess
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.algo08v3 import EXECUTION_RELEASE, validate_release
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import ALGO08V2, ALGO08V3
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

DEFAULT_LAUNCHER = Path("/opt/leo-algo08/algo08v3/run")
DEFAULT_PYTHON = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python")
DEFAULT_REGION = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/station/region.json")
DEFAULT_ARCHIVE = Path("/var/lib/leo/tle")


def _receipt(run_id, report, decision):
    validate_release(report.get("execution_release"))
    if (decision["state"] not in ("complete", "withheld") or decision["run_id"] != run_id
            or report["model_version"] != ALGO08V3 or report["run_id"] != run_id
            or report["session_id"] != decision["session_id"]
            or report["terminal_sha256"] != decision["terminal_sha256"]):
        raise ValueError("ALGO08v3 report differs from the terminal publication")
    return dict(run_id=run_id, session_id=report["session_id"], window_count=report["window_count"],
                counts=report["counts"], region=decision["region"], decision=decision["state"],
                terminal_sha256=decision["terminal_sha256"], execution_release=EXECUTION_RELEASE)


def _publish_frozen(stage, run_id, session, inventory_sha, inventory, region, store, standard):
    # The release receipt is written after the frozen producer seals its outputs.
    release = json.loads((stage / "algo08v3-release.json").read_bytes())
    recorded_session = release.pop("session_id")
    decision = release.pop("decision")
    validate_release(release)
    if recorded_session != session or decision not in ("complete", "withheld"):
        raise ValueError("ALGO08v3 execution receipt differs from the requested recording")

    source, frozen = FastScanStore(stage), FastStandardAnalysisStore(stage)
    reports = source.page(limit=2)["items"]
    if len(reports) != 1 or source.source(session, inventory_sha) != inventory:
        raise ValueError("ALGO08v3 execution did not publish the requested source inventory")
    report = source.detail(reports[0]["run_id"])
    old_run = report["run_id"]
    publication = frozen.detail(old_run)
    if (report["model_version"] != ALGO08V2 or report["session_id"] != session
            or report["recording_name"] != inventory["recording_name"]
            or report["window_count"] != inventory["window_count"]
            or publication["model_version"] != ALGO08V2 or publication["run_id"] != old_run
            or publication["state"] != decision or publication["session_id"] != session
            or publication["region"] != region):
        raise ValueError("ALGO08v3 frozen publication differs from its execution receipt")

    # Keep the archived solver's data and digest, while binding the public
    # terminal decision and artifacts to their actual execution release.
    terminal = dict(run_id=run_id, model_version=ALGO08V3, session_id=session, decision=decision,
                    region=region, execution_release=release,
                    source_terminal_sha256=publication["terminal_sha256"])
    binding = {key: publication[key] for key in ("input_sha256", "raw_authority", "orbit_policy")}
    binding.update(session_id=session, region=region, execution_release=release,
                   source_terminal_sha256=terminal["source_terminal_sha256"],
                   terminal_sha256=canonical_digest(terminal))
    store.publish_inventory(session, inventory)
    if decision == "withheld":
        result = standard.withhold(run_id, publication["reason"], **binding)
    else:
        grid, path = frozen.position_grid(old_run), frozen.position_path(old_run)
        if grid is None or path is None:
            raise ValueError("ALGO08v3 frozen publication is missing position evidence")
        path["selected_model"] = ALGO08V3
        for stage_result in path["stages"]:
            if stage_result["model_version"] == ALGO08V2:
                stage_result["model_version"] = ALGO08V3
        pngs = {entry["name"]: frozen.artifact(old_run, entry["name"], entry["sha256"])
                for entry in publication["artifacts"]}
        document = dict(publication, **binding, run_id=run_id, model_version=ALGO08V3,
                        selected_model=ALGO08V3, figures_model=ALGO08V3)
        document.pop("evaluation_reference")
        document.pop("artifacts")
        for arm in document["arms"].values():
            arm.pop("evaluation_error_m", None)
        result = standard.publish(run_id, document, pngs, position_grid=grid, position_path=path)
    report.update(run_id=run_id, model_version=ALGO08V3, execution_release=release,
                  terminal_sha256=binding["terminal_sha256"])
    store.publish(run_id, report)
    return _receipt(run_id, report, result)


def publish_algo08v3(recording, *, store, launcher=DEFAULT_LAUNCHER, launcher_python=DEFAULT_PYTHON,
                     region_file=DEFAULT_REGION, archive=DEFAULT_ARCHIVE, evaluation_reference=None):
    """Import a sealed frozen result under a stable, release-specific run ID."""
    region = Algo08Region.parse(json.loads(region_file.read_bytes())).document()
    session, inventory_sha, inventory = store.inventory(recording, verify_windows=False)
    run_id = "algo08-v3-" + canonical_digest([ALGO08V3, EXECUTION_RELEASE, inventory_sha, region])[7:39]
    workspace = store.automatic_workspace(run_id)
    stage = workspace / "frozen"
    standard = FastStandardAnalysisStore(store.root)
    with (workspace / "owner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if stage.is_symlink():
            raise ValueError("ALGO08v3 work directory must be owned by the publisher")
        try:
            report = store.detail(run_id)
        except FileNotFoundError:
            marker = stage / "algo08v3-release.json"
            try:
                json.loads(marker.read_bytes())
            except (FileNotFoundError, json.JSONDecodeError):
                if stage.exists():
                    shutil.rmtree(stage)
                stage.mkdir(mode=0o700)
                # Pass the same canonical offer bound into the run identifier.
                offer = workspace / "region.json"
                immutable_json(offer, region)
                script = Path(__file__).with_name("algo08v3_launcher.py")
                invocation = subprocess.run(
                    [str(launcher_python), "-IB", str(script), str(launcher), "--recording", str(recording),
                     "--archive", str(archive), "--region", str(offer), "--bulk-root", str(stage)],
                    capture_output=True, text=True, timeout=3600,
                )
                if invocation.returncode:
                    raise RuntimeError("ALGO08v3 launcher failed: " + invocation.stderr[-1500:])
            receipt = _publish_frozen(stage, run_id, session, inventory_sha, inventory, region, store, standard)
        else:
            result = standard.detail(run_id)
            receipt = _receipt(run_id, report, result)
            for entry in result["artifacts"]:
                standard.artifact(run_id, entry["name"], entry["sha256"])
            if receipt["decision"] == "complete" and (
                    standard.position_grid(run_id) is None or standard.position_path(run_id) is None):
                raise ValueError("ALGO08v3 publication is missing position evidence")
        if evaluation_reference is not None and receipt["decision"] == "complete":
            standard.set_evaluation_reference(run_id, *evaluation_reference)
        if stage.exists():
            shutil.rmtree(stage)
        return receipt
