"""Optionally export the existing DS30-0218 selected owner residuals after publication."""

import argparse
from contextlib import contextmanager, nullcontext
from math import isfinite
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import masked_cfo_0218 as held  # noqa: E402
from masked_cfo_saved import clock, elapsed, saved  # noqa: E402


ARMS = ("c0", "fitted_c")
FIELDS = ("measured_cfo_hz", "residual_hz", "prediction_hz")
PRESENTATION = "src/leo/presentation/localization_v3.py"
PRESENTATION_SHA256 = "5dd6dbc63a4078e4b7fffcf10237d4f92429a1ea07d585eb3a49d0eca02cae2b"


@contextmanager
def observe_packet(position, captured):
    original = position.selected_packet

    def selected(*args, **kwargs):
        packet = original(*args, **kwargs)
        captured.append(packet["rows"])
        return packet

    with patch.object(position, "selected_packet", selected):
        yield


@contextmanager
def observe_worker(captured):
    ordinary_worker = saved.worker

    def worker(*args, observation_scope=None, **kwargs):
        @contextmanager
        def scope(native):
            # The ordinary worker has now verified and imported the installed runtime.
            from tools import algo08_position

            underlying = nullcontext() if observation_scope is None else observation_scope(native)
            with observe_packet(algo08_position, captured), underlying:
                yield

        return ordinary_worker(*args, observation_scope=scope, **kwargs)

    with patch.object(saved, "worker", worker):
        yield


def selected_rows(captured, evidence, decision):
    owners = evidence["owner_rows"]
    if decision == "withheld" and not captured and owners == {}:
        return {}
    if (decision != "complete" or len(captured) != 1 or set(captured[0]) != set(ARMS)
            or set(owners) != set(ARMS)):
        raise ValueError("Expected one selected packet with both verified arms, or an ordinary withholding")
    output = {}
    for arm in ARMS:
        rows = captured[0][arm]
        identities = [[row["observation_id"], row["norad"], row["role"]] for row in rows]
        if not rows or identities != owners[arm] or len({item[0] for item in identities}) != len(rows):
            raise ValueError("The residual rows differ from the verified ordered owners")
        points = []
        for (oid, norad, role), row in zip(identities, rows, strict=True):
            if role not in ("conditional", "predictive"):
                raise ValueError("Unsupported residual convention for the selected owner role")
            values = {field: float(row[field]) for field in FIELDS}
            if not all(map(isfinite, values.values())) or values["prediction_hz"] != (
                    values["measured_cfo_hz"] - values["residual_hz"]):
                raise ValueError("The selected row does not preserve the finite signed CFO convention")
            points.append(dict(observation_id=oid, norad=norad, role=role, **values))
        output[arm] = points
    return output


def export(root, pin, mode, captured):
    """Bind the retained rows to the already closed standard evidence."""
    started = clock()
    from empty_bootstrap import RELEASE
    from leo.presentation import localization_v3
    from named_history_once import checked
    from tools import algo08_position

    checked(localization_v3, RELEASE/PRESENTATION, PRESENTATION_SHA256)
    if algo08_position.prepare_packet is not localization_v3.prepare_packet:
        raise ValueError("Require the installed signed residual preparation")
    witness_path = root/"masked-cfo-observation-witness.json"
    receipt_path = root/"receipt.json"
    observation_pin, receipt_pin = [saved.identifier(path) for path in (witness_path, receipt_path)]
    scoped = saved.document(witness_path, observation_pin)
    run = saved.document(receipt_path, receipt_pin)
    receipt = run["receipt"]
    if (scoped["stage_plan_sha256"] != pin or run["plan_sha256"] != pin
            or scoped["enabled"] != (mode == "corrected") or scoped["decision"] != receipt["decision"]
            or scoped["original_native_sha256"] != run["input"]):
        raise ValueError("The owner residuals require the closed and verified original replay")
    witness = saved.document(root/"substituted/exact-named-raw-witness.json", run["witness"])
    evidence = witness["evidence"]
    if (evidence["detail"]["input_sha256"] != run["input"]
            or evidence["detail"]["terminal_sha256"] != receipt["terminal_sha256"]):
        raise ValueError("The selected residuals differ from the verified input or terminal")
    rows = selected_rows(captured, evidence, receipt["decision"])
    artifact = dict(schema="leo.research.selected-owner-residuals.v1", role=mode, decision=receipt["decision"],
        plan_sha256=pin, native_sha256=run["input"], terminal_sha256=receipt["terminal_sha256"],
        ordinary_receipt_sha256=receipt_pin, observation_witness_sha256=observation_pin,
        publication_witness_sha256=run["witness"], presentation_source_sha256=PRESENTATION_SHA256,
        observer_source_sha256=saved.identifier(Path(__file__)), rows=rows)
    readback = saved.write(root/"owner-residuals.json", artifact)
    return saved.write(root/"owner-residual-export-clock.json", dict(
        residuals_sha256=readback, after_verified_publication_through_artifact_write=elapsed(started)))


def entry(root, pin, mode, fd):
    plan = saved.document(root/"plan.json", pin)
    if plan["case"] != held.CASE or plan["probe"] or mode not in ("ordinary", "corrected"):
        raise ValueError("The optional observer requires a normal enrolled DS30-0218 replay")
    captured = []
    with observe_worker(captured):
        held.entry(root, pin, held.experiment, mode=mode, fd=fd)
    return export(root, pin, mode, captured)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("ordinary", "corrected"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--lease-fd", type=int, required=True)
    args = parser.parse_args()
    sys.addaudithook(saved.deny_backing)
    if args.root.resolve() != args.root or not args.root.is_relative_to("/dev/shm"):
        parser.error("The saved stage must use a private direct tmpfs path")
    print(entry(args.root, args.pin, args.mode, args.lease_fd))
