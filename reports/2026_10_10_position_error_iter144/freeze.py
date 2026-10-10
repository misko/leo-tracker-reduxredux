"""Reviewed closure preparation only; never reconstruct inputs or query catalogues."""

import hashlib
import json

from runner import DESIGN_BUDGET_BYTES, HERE, ROOT, sha


def protocol():
    original_path = HERE.parent / "2026_10_10_position_error_iter135/protocol.json"
    if sha(original_path) != "c08146f238fbad30b5fa0ea2a7acf8c065b597aea7f28ebb0467216a202d629a":
        raise ValueError("Published135 authority changed")
    original = json.loads(original_path.read_text())
    sources = dict(original["sources"])
    for name in (
        "runner.py",
        "freeze.py",
        "catalogue_policy.py",
        "projection.py",
        "streamed_projection.py",
        "test_runner.py",
        "test_policy_projection.py",
        "test_streamed_projection.py",
        "PLAN.md",
    ):
        path = HERE / name
        sources[str(path.relative_to(ROOT))] = sha(path)
    adapter = HERE.parent / "2026_10_09_position_error_iter111/adapter.py"
    sources[str(adapter.relative_to(ROOT))] = sha(adapter)
    for path, expected in sources.items():
        if sha(ROOT / path) != expected:
            raise ValueError("Physical source closure changed")
    inputs = dict(original["inputs"])
    if len(original["members"]) != 12 or len({m["label"] for m in original["members"]}) != 12:
        raise ValueError("Exact135twelve required")
    members, pending, provenance = [], {}, []
    directory = HERE / "endpoints"
    for member in original["members"]:
        source = original_path.parent / "results" / (member["label"] + ".json")
        result = json.loads(source.read_text())
        if result["label"] != member["label"] or result["protocol_sha256"] != sha(original_path):
            raise ValueError("Foreign135 saved endpoints")
        endpoints = {}
        for arm in ("fitted-c", "zero-c"):
            attempt = result["attempts"]["timestamp"][arm]
            if result["status"] == "model-integrity-failed" or not attempt["qualified"]:
                raise ValueError("Qualified135timestamp endpoints required")
            endpoints[arm] = {
                k: attempt["fit"][k]
                for k in ("vector", "clock_coefficients", "objective", "converged")
            }
        path = directory / (member["label"] + ".json")
        if path.exists():
            raise ValueError("Endpoint projection exists; no overwrite")
        data = (
            json.dumps(dict(label=member["label"], endpoints=endpoints), indent=2, allow_nan=False)
            + "\n"
        ).encode()
        pending[path] = data
        provenance.append(
            dict(
                label=member["label"],
                source_path=str(source.relative_to(ROOT)),
                source_sha256=sha(source),
            )
        )
        relative = str(path.relative_to(ROOT))
        inputs[relative] = hashlib.sha256(data).hexdigest()
        members.append(
            dict(
                label=member["label"], case_binding=member["case_binding"], endpoints_path=relative
            )
        )
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("Exact135twelve required")
    provenance_path = HERE / "ENDPOINT_PREPARATION_PROVENANCE.json"
    if provenance_path.exists() or (HERE / "protocol.json").exists():
        raise ValueError("Preparation artifact exists; no overwrite")
    for path, expected in original["inputs"].items():
        if sha(ROOT / path) != expected:
            raise ValueError("Inherited clean input changed")
    # All membership, source, endpoint and input validation precedes any write.
    directory.mkdir(exist_ok=True)
    for path, data in pending.items():
        with path.open("xb") as stream:
            stream.write(data)
    with provenance_path.open("x") as stream:
        json.dump(dict(members=provenance), stream, indent=2)
        stream.write("\n")
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        maximum_workers=1,
        ordinary_endpoint_calls_per_member=2,
        optimizer_calls=0,
        earlier_distinct_payload_cap=10,
        earlier_window_hours=24,
        design_budget_bytes=DESIGN_BUDGET_BYTES,
        threads=1,
        scope="Prediction-space catalogue sensitivity only; no position change or reference port",
    )


if __name__ == "__main__":
    prepared = protocol()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(prepared, stream, indent=2, allow_nan=False)
        stream.write("\n")
