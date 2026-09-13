"""One bounded, explicitly authorized native adaptive canary on radio003a."""

import argparse
import fcntl
import json
import signal
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Timer

from leo.cli.composition import CliSettings, CompositionHooks, LocalAcquisitionBackend
from leo.scanner.host_adaptive import HOST_ADAPTIVE_PROFILE_ID
from leo.scanner.schedule import canonical_scheduled_scanner_operation_key
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore

SERIAL = "104000bac4950008230026001b440a003a"


def write(path, document):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n")
    temporary.replace(path)


def qualify_result(result, receipt, detail, cancel):
    if not result.capture_qualified or receipt.valid_duty_ppm < 950_000:
        raise ValueError("native capture failed duration, continuity, restoration or duty gates")
    if any(
        d.health != "healthy" or d.feedback_disposition not in ("accepted", "source_ended")
        for d in receipt.host_decisions
    ):
        raise ValueError("host feedback has unhealthy or undelivered results")
    if detail.capture.fallback_choices:
        raise ValueError("healthy canary entered policy fallback")
    if cancel.is_set():
        raise ValueError("canary exceeded its bounded deadline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--mode", choices=("shadow", "adaptive"), required=True)
    parser.add_argument("--rx", type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    if Path(__import__("sys").executable).parent.parent != args.release / ".venv":
        raise ValueError("canary must use the explicitly staged release interpreter")
    values = {}
    for path in (Path("/etc/leo/leo.env"), Path("/etc/leo/acquisition.env")):
        for line in path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
    for key in tuple(values):
        if (
            key.startswith("LEO_SCANNER_GLRT_")
            or key == "LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH"
        ):
            del values[key]
    values.update(
        LEO_SCANNER_PROFILE=HOST_ADAPTIVE_PROFILE_ID,
        LEO_SCANNER_HOP_POLICY=args.mode,
        LEO_SCANNER_GLRT_MODE="disabled",
        LEO_SCANNER_INTERVAL_SECONDS="600",
        LEO_SCANNER_ADAPTIVE_SAMPLE_RATES_HZ="10000000",
        LEO_SCANNER_HOST_DECISION_MANIFEST_PATH=str(
            args.release / "runtime/scanner-host-decision/manifest.json"
        ),
        LEO_SCANNER_HOST_DECISION_MANIFEST_SHA256="sha256:09bd961a759bad59d773243a25841a4250f345c6a9c66eb7c0c4afc3e68e1fcf",
        LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH=str(args.release / "runtime/scanner-iiod/iiod"),
        CREDENTIALS_DIRECTORY="/etc/leo/credentials",
    )
    settings = CliSettings.from_environ(values)
    if len(settings.radios) != 1 or settings.radios[0].serial != SERIAL:
        raise ValueError("only the user-selected radio003a is authorized")
    args.output.mkdir(parents=True, exist_ok=False)
    store = AdaptiveHopIqStore(args.output)
    backend = LocalAcquisitionBackend(
        settings, CompositionHooks(adaptive_hop_store_factory=lambda _: store)
    )
    # A historical slot supplies a durable canary identity, not RF UTC. The
    # actual capture start is separately bracketed by the production adapter.
    for index in range(100):
        slot = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=10 * index)
        intent = backend.scheduled_scanner_intent(
            operation_key=canonical_scheduled_scanner_operation_key(slot), scheduled_for=slot
        )
        if intent.configuration.receiver_ids == (args.rx,):
            break
    else:
        raise ValueError("no canary identity selects the requested RX")
    cancel = Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    signal.signal(signal.SIGTERM, lambda *_: cancel.set())
    report = {
        "mode": args.mode,
        "physical_receiver": args.rx,
        "radio_serial": SERIAL,
        "intent": intent.model_dump(mode="json"),
        "started_utc_ns": time.time_ns(),
    }
    with args.ledger.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = json.loads(args.ledger.read_text())
        if ledger["remaining_seconds"] < 310 or any(
            e.get("state") in ("running", "failed") for e in ledger["entries"]
        ):
            raise ValueError("RF budget is insufficient or a previous canary requires review")
        entry = {
            "id": f"host-{args.mode}-rx{args.rx}",
            "state": "running",
            "reserved_seconds": 310,
            "report": str(args.output / "canary.json"),
        }
        if any(e["id"] == entry["id"] for e in ledger["entries"]):
            raise ValueError("this bounded canary was already attempted")
        ledger["entries"].append(entry)
        write(args.ledger, ledger)
        timer = Timer(310, cancel.set)
        timer.daemon = True
        started = time.monotonic()
        timer.start()
        try:
            result = backend.capture_scheduled_scanner(intent, cancel=cancel)
            captured = store.verify(result.published.session_id)
            receipt = captured.manifest.receipt
            detail = AdaptiveHopPresentationStore(args.output).detail_v2(captured.session_id)
            report.update(
                session_id=captured.session_id,
                manifest_sha256=captured.manifest_sha256,
                receipt=receipt.model_dump(mode="json"),
                capture=detail.capture.model_dump(mode="json"),
            )
            qualify_result(result, receipt, detail, cancel)
            report["state"] = entry["state"] = "passed"
            print(
                json.dumps(
                    {
                        "state": "passed",
                        "rx": args.rx,
                        "mode": args.mode,
                        "duty_ppm": receipt.valid_duty_ppm,
                        "host_feedback": detail.capture.host_feedback.model_dump(mode="json"),
                    }
                )
            )
        except BaseException as error:
            report.update(state="failed", error=f"{type(error).__name__}: {error}")
            entry["state"] = "failed"
            raise
        finally:
            timer.cancel()
            elapsed = time.monotonic() - started
            entry["rf_seconds_upper_bound"] = elapsed
            entry["reason"] = (
                "Conservatively charge the entire capture call, including setup and restoration."
            )
            ledger["charged_seconds"] += elapsed
            ledger["remaining_seconds"] = ledger["budget_seconds"] - ledger["charged_seconds"]
            ledger["reserved_next_canaries_seconds"] = max(
                0, ledger["reserved_next_canaries_seconds"] - 300
            )
            report.update(elapsed_seconds=elapsed, finished_utc_ns=time.time_ns())
            write(args.output / "canary.json", report)
            write(args.ledger, ledger)
            store.close()


if __name__ == "__main__":
    main()
