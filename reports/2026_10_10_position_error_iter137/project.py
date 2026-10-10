"""Stream published pretty-JSON receipts into inference-only selected states."""

import hashlib
import json
import re

TOP = re.compile(rb'^  "([^"\\]+)": ')
KEEP = {"protocol_sha256", "label", "phase", "status", "input_binding", "operational"}


def read_selected(path):
    """Retain bounded top-level fields; scan every byte for provenance SHA.

    The producer's two-space pretty-JSON format is an explicit admission
    condition. Nested keys never qualify as top-level fields. Reference-bearing
    fields outside the whitelist are neither parsed nor returned.
    """
    digest = hashlib.sha256()
    parts = {}
    current = None
    with open(path, "rb") as stream:
        for line in stream:
            digest.update(line)
            match = TOP.match(line)
            if match:
                current = match[1].decode()
                if current in KEEP:
                    if current in parts:
                        raise ValueError("Duplicate selected top-level key")
                    parts[current] = []
            if current in KEEP:
                parts[current].append(line)
    values = {}
    for key, lines in parts.items():
        text = b"".join(lines).decode().rstrip()
        if key == current:
            # Final top-level field also contains the root closing brace.
            text = text.rsplit("\n}", 1)[0]
        values[key] = json.loads("{" + text.rstrip(",") + "}")[key]
    if set(values) != KEEP or values["status"] != "complete":
        raise ValueError("Incomplete selected-state source")
    operational = {}
    for arm in ("fitted-c", "zero-c"):
        row = values["operational"][arm]
        fit = row["fit"]
        operational[arm] = {
            "selection": {
                k: row.get(k)
                for k in (
                    "basin",
                    "method",
                    "arm",
                    "start",
                    "region_source",
                    "accepted_stage",
                    "satellites",
                    "calibration_penalty",
                )
            },
            "fit": {
                k: fit.get(k)
                for k in (
                    "vector",
                    "clock_coefficients",
                    "objective",
                    "converged",
                    "joint_state",
                    "convergence_reason",
                )
            },
        }
        state = operational[arm]["fit"]["joint_state"]
        if state is not None:
            operational[arm]["fit"]["joint_state"] = {
                k: state[k]
                for k in (
                    "stage",
                    "vector",
                    "clock_coefficients",
                    "clock_nodes_s",
                    "clock_knots_hz",
                    "receiver_baseline_hz",
                    "rf_time_coefficients",
                    "satellite_centers_s",
                    "satellite_offsets_hz",
                    "satellite_slopes_hz_s",
                    "likelihood_nll",
                    "timing_penalty",
                    "nuisance_penalty",
                    "total_objective",
                )
                if k in state
            }
    return {
        **{k: values[k] for k in KEEP - {"operational"}},
        "operational": operational,
        "preparation_source_sha256": digest.hexdigest(),
    }
