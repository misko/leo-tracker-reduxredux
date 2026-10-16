"""Join reference error to sealed development inference, never select by error."""

import argparse
import json
from pathlib import Path

import numpy as np
from ds20_channel_corpus import digest
from ds21_common import OUTPUT, immutable

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior


def selected_states(terminal):
    """Normalize selected states only; never search attempts using the reference."""
    if "rows" in terminal:
        for row in terminal["rows"]:
            winner = row.get("winner")
            yield row["view"], row["rf_arm"], None if winner is None else winner["theta"][:2]
        return
    result = terminal.get("results", terminal.get("result", {}))
    if "selected" in result:
        result = {"all": result}
    for view, row in result.items():
        for arm, selected in row["selected"].items():
            fit = selected.get("fit")
            yield view, arm, None if fit is None else fit["vector"][:2]


def reference():
    # Import is deliberately below the terminal/protocol/development guards.
    from leo.cli.regional_position import REFERENCE

    return REFERENCE


def distance_km(point, expected):
    lat, lon, a, b = np.radians([*point, *expected])
    value = np.sin((lat - a) / 2) ** 2 + np.cos(lat) * np.cos(a) * np.sin((lon - b) / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(value, 0, 1))))


def evaluate(directory, *, output=OUTPUT):
    terminal_path = directory / "terminal.json"
    protocol_path = directory / "protocol.json"
    terminal = json.loads(terminal_path.read_bytes())
    protocol = json.loads(protocol_path.read_bytes())
    if terminal["protocol_sha256"] != digest(protocol_path):
        raise ValueError("Inference terminal/protocol seal differs")
    label = protocol.get("label", terminal.get("label"))
    membership = json.loads((output / "membership.json").read_bytes())
    member = next(m for m in membership["members"] if m["label"] == label)
    if member["role"] != "development":
        raise ValueError("Locked evaluation needs a frozen model release")
    states = list(selected_states(terminal))
    expected = reference()
    prior = RegionalPrior(**membership["prior"])
    rows = []
    for view, arm, point in states:
        row = dict(view=view, arm=arm, state="unavailable")
        if point is not None:
            if len(point) != 2 or not np.isfinite(point).all():
                raise ValueError("Invalid selected geographic state")
            location = coordinates(prior, point)
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                coordinates_deg=list(location),
                error_km=error,
                below_1km=error < 1.0,
            )
        rows.append(row)
    model_name = directory.parent.name
    if model_name == "local":
        model_name = directory.parent.parent.name
    result = dict(
        label=label,
        role=member["role"],
        model=model_name,
        terminal_sha256=digest(terminal_path),
        protocol_sha256=digest(protocol_path),
        membership_sha256=digest(output / "membership.json"),
        rows=rows,
        reference_evidence="Configured baseline receiver reference; evaluation only",
        reference_source_sha256=digest(
            Path(__file__).resolve().parents[1] / "src/leo/cli/regional_position.py"
        ),
        limitation="Reference is configured station location, not independently surveyed here",
        reference_usage="Only after terminal/protocol verification; never inference/selection",
    )
    destination = output / "development-errors" / (model_name + "-" + label + ".json")
    immutable(destination, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.directory)), flush=True)
