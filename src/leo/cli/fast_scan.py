"""Offline fast-scan ingestion and replay; never opens a radio."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Annotated

import typer


def register_fast_scan_commands(scanner):
    @scanner.command("analyze-fast")
    def analyze_fast(
        recording: Path,
        bulk_root: Annotated[Path, typer.Option(help="Local artifact/publication root.")],
        database_url: Annotated[str, typer.Option(envvar="LEO_DATABASE_URL", hide_input=True)],
        workers: Annotated[int, typer.Option(min=1, max=32)] = 8,
        mode: Annotated[str, typer.Option(help="gated, ungated, or shadow")] = "gated",
        export_tracking_input: Annotated[bool, typer.Option(
            help="Export verified input for the existing shared tracking pipeline.")
        ] = False,
    ):
        """Verify sealed 20ms segments, resume GLRT jobs, and publish a UI report."""
        for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[variable] = "1"
        from leo.contracts.fast_scan import FastScanPolicyV1
        from leo.processing.fast_scan import process_recording

        report = process_recording(
            recording,
            database_url=database_url,
            root=bulk_root,
            policy=FastScanPolicyV1(mode=mode),
            workers=workers,
            export_tracking_input=export_tracking_input,
        )
        typer.echo(json.dumps({k: v for k, v in report.items() if k != "points"}, indent=2))


def process_automatic(recording, *, store, database_url, standard_command, glrt_lock,
                      standard_mode='algo07', standard_reader=None, glrt_workers=8):
    """Resume the existing GLRT queue, then the existing standard CLI pipeline."""
    if type(glrt_workers) is not int or not 1 <= glrt_workers <= 32:
        raise ValueError('GLRT workers must be an integer within 1..32')
    from leo.processing.fast_scan import process_recording

    identifier = recording.name
    try:
        state = store.automatic_status(identifier) or {}
        if not state.get("run_id"):
            with glrt_lock:
                store.update_automatic(identifier, state="glrt", failure=None)
                report = process_recording(recording, database_url=database_url,
                    root=store.root, workers=glrt_workers, export_tracking_input=True)
            state = store.update_automatic(identifier, state="tracking",
                run_id=report["run_id"], session_id=report["session_id"],
                window_count=report["window_count"], counts=report["counts"])
        workspace = store.automatic_workspace(identifier)
        if standard_mode == 'algo07':
            from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
            reader=standard_reader or FastStandardAnalysisStore(store.root)
            result=reader.detail(state['run_id'])
            complete=result['state']=='complete'
            return store.update_automatic(identifier,state='complete' if complete else 'tracking',failure=None,
                standard_algorithm='ALGO07', standard_stages=dict(glrt=True,algo07=complete),
                standard_terminal_sha256=result.get('terminal_sha256'))
        if standard_mode != 'legacy':
            raise ValueError('Explicit standard mode required')
        command = [*standard_command, "standard", "--input",
                   str(store.tracking_input_path(state["run_id"])), "--output", str(store.root),
                   "--receipt-root", str(workspace), "--maximum-seconds", "500", "--full"]
        # Each slice resumes component-owned checkpoints. A timeout/failure is
        # visible; it never becomes a successful analysis just because IQ sealed.
        for attempt in range(12):
            store.update_automatic(identifier, state="tracking", slice=attempt + 1)
            with (workspace / "pipeline.log").open("a") as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=1800, check=False)
            if result.returncode:
                raise RuntimeError(
                    f"standard pipeline exited {result.returncode}; see pipeline log")
            receipt = json.loads((workspace / "adapter-receipt.json").read_bytes())
            if receipt["analysis_complete"]:
                return store.update_automatic(identifier, state="complete", failure=None,
                    standard_stages=receipt.get("standard_stages", {}))
        raise RuntimeError("standard pipeline exceeded 12 checkpoint slices")
    except Exception as error:
        store.update_automatic(identifier, state="failed",
                               failure=f"{type(error).__name__}: {error}")
        raise


def discover_automatic(recording_root, store):
    from leo.storage.continuous_window import list_checkpoints, run_path

    ready = []
    def checkpoint_error(identifier, error):
        previous = store.automatic_status(identifier) or {}
        store.update_automatic(identifier, state=previous.get("state", "recording"),
            discovery_warning=f"Checkpoint is not yet valid: {error}"[:512])

    for checkpoint in list_checkpoints(recording_root, on_error=checkpoint_error):
        previous = store.automatic_status(checkpoint.run_id)
        if previous and previous["state"] in {"glrt", "tracking", "complete", "failed"}:
            if previous["state"] in {"glrt", "tracking"}:
                ready.append(run_path(recording_root, checkpoint.run_id))
            continue
        state = "recording" if checkpoint.state != "stopped" else "queued"
        if checkpoint.state == "failed" or checkpoint.fault:
            state = "failed"
        store.update_automatic(checkpoint.run_id, state=state,
            captured_windows=checkpoint.captured_windows, failure=checkpoint.fault,
            discovery_warning=None,
            edge=checkpoint.configuration["targets"][0].get("edge"))
        if state == "queued":
            terminal = checkpoint.device_terminal or {}
            restoration = checkpoint.host_restoration or {}
            if (checkpoint.captured_windows == 0
                    or checkpoint.durable_windows != checkpoint.captured_windows
                    or terminal.get("state") != 1 or terminal.get("error") != 0
                    or not restoration.get("fastlock_inactive")):
                store.update_automatic(checkpoint.run_id, state="failed",
                                       failure="capture terminal or durability evidence is missing")
            else:
                ready.append(run_path(recording_root, checkpoint.run_id))
    return ready


def watch_automatic(args):
    import fcntl
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_capture_health import checkpoint_health
    from leo.application.reconcile_fast_capture import reconcile
    from leo.acquisition.authority import LocalCaptureAuthority,RadioResource

    store = FastScanStore(args.bulk_root)
    authority=(LocalCaptureAuthority(args.bulk_root/'control',(
        RadioResource(args.capture_serial,args.capture_serial,args.capture_uri),)) if args.capture_serial else None)
    reconciliation_at=0.
    lock_path = store.automatic_workspace("watcher") / "owner.lock"
    with lock_path.open("a") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = {}
        glrt_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=3) as pool:
            while True:
                if authority and time.monotonic()-reconciliation_at>60:
                    roots=[args.recording_root,*args.staging_root]
                    health={r['run_id']:r for root in roots if root.exists() for r in checkpoint_health(root)}
                    print(json.dumps(reconcile(authority,args.capture_serial,health.values(),store)),flush=True)
                    reconciliation_at=time.monotonic()
                for identifier, future in list(active.items()):
                    if future.done():
                        try:
                            future.result()
                        except Exception as error:
                            print(json.dumps({"recording_id": identifier, "failure": str(error)}),
                                  flush=True)
                        del active[identifier]
                for recording in discover_automatic(args.recording_root, store):
                    if recording.name not in active:
                        active[recording.name] = pool.submit(process_automatic, recording,
                            store=store, database_url=os.environ["LEO_DATABASE_URL"],
                            standard_command=[args.standard_python, args.standard_script],
                            glrt_lock=glrt_lock,standard_mode=args.standard_mode,glrt_workers=args.glrt_workers)
                time.sleep(5)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Automatically analyze sealed fast scans; no RF.")
    parser.add_argument("--recording-root", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--standard-python", default='')
    parser.add_argument("--standard-script", default='')
    parser.add_argument('--standard-mode',choices=('algo07','legacy'),default='algo07')
    parser.add_argument('--glrt-workers',type=int,choices=range(1,33),default=8)
    parser.add_argument('--capture-serial');parser.add_argument('--capture-uri',default='ip:192.168.1.20')
    parser.add_argument('--staging-root',type=Path,action='append',default=[])
    watch_automatic(parser.parse_args())
