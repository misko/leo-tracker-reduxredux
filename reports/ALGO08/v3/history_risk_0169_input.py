"""Reuse the original full named worker and causal view preserved for DS30-0169."""

from pathlib import Path

import exact_named_route as exact


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-family-endpoint-0169-results-01")
ENROLLMENT = HERE/"measurements/family-endpoint-transfer-enrollment.json"
ENROLLMENT_SHA256 = "0ce4e6ee4925c114d2723514082548b327ecd144e848adfbc55b5b83bfe12313"
STOCK_WORKER = "family-endpoint-worker.json"
PINS = {
    "request.json": "b8b16a93ef61b8c7daaa5ef327d005e53281972f1c1e72cb0e9bb15a3d09c3c8",
    "launch.json": "20ef7a315e47cb4dd1a30334f5814c3f5964a2cf045f84cc1c83d43e4bfeadf9",
    "inventory.json": "be9e6e39a10a89a298054d08ea51db53b5aec7667ecf9a725373582ac092972d",
    "named-detections.json": "b185302560a9981a5624613ce39d358817c7a21edbb6778168e3d5dd3c8a5ffc",
    "operator-offer.json": "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
    "stock-clock.json": "d85ad10413154ae435f630e583c142809e139d6a221a299dd050013a06a21b6e",
    "stock/joint-research-receipt.json": "39937a183660c0f3fa33c5574d361775dbc0498ce42a595e5fa8e8d9f8146a88",
    f"stock/{STOCK_WORKER}": "2b9ab68494e62150356b2a8636271e09bdf578dca9b68d9aecff0d5d258eef09",
}


def request_view(req, enrollment):
    local = req["local_archive"]
    if (req["case"] != "DS30-0169" or req["enrollment_sha256"] != ENROLLMENT_SHA256
            or any(req[name] != enrollment[name] for name in ("case", "recording", "session", "admitted", "issued"))
            or req["causal_cutoff_utc_ns"] != enrollment["cutoff_utc_ns"] or req["raw_authority"] != enrollment["authority"]
            or local["snapshots_sha256"] != enrollment["original_archive"]["snapshots_sha256"]
            or local["snapshots"] != enrollment["snapshots"] or local["bytes"] != enrollment["archive_bytes"]):
        raise ValueError("The named packet, signed causal view or enrollment changed")
    return dict(req, original_archive=enrollment["original_archive"])


def bind():
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA

    if exact.digest(ENROLLMENT) != ENROLLMENT_SHA256:
        raise ValueError("The original enrollment is unavailable")
    pins = {STAGE/name: value for name, value in PINS.items()}
    producer = ARTIFACT.parent/"artifact-bind.json"
    pins.update({ARTIFACT: ARTIFACT_SHA[7:], producer: PRODUCER_SHA})
    for path, pin in pins.items():
        if exact.digest(exact.resident_path(path)) != pin:
            raise ValueError(f"Original authenticated saved artifact changed: {path}")
    selected = exact.read(ENROLLMENT)["selected"]
    req = request_view(exact.read(STAGE/"request.json"), selected)
    stock = exact.read(STAGE/"stock"/STOCK_WORKER)
    if (req["native_file"] != str(STAGE/"named-detections.json") or req["inventory"] != "sha256:"+PINS["inventory.json"]
            or req["native_sha256"] != PINS["named-detections.json"] or req["offer_file"] != str(STAGE/"operator-offer.json")
            or req["offer_sha256"] != PINS["operator-offer.json"] or req["local_archive"]["root"] != str(STAGE/"tle")
            or stock["receipt"]["terminal_sha256"] != selected["terminal_sha256"] or not stock["no_waveform"]
            or stock["handoffs"] != 1 or exact.read(STAGE/"stock-clock.json")["timing"]["exit_code"] != 0
            or exact.read(producer)["source"]["cutoff_utc_ns"] >= req["causal_cutoff_utc_ns"]):
        raise ValueError("Expected the independently scored named saved publication and earlier index producer")
    sources = {p.name: exact.digest(p) for p in (*exact.SOURCES, Path(__file__), HERE/"history-risk-held-0169-protocol.md")}
    bound = dict(case=req["case"], stage=str(STAGE), request=str(STAGE/"request.json"), archive=str(STAGE/"tle"),
                 inventory=str(STAGE/"inventory.json"), packets={str(path): pin for path, pin in pins.items()},
                 issued=req["issued"], admitted=req["admitted"], sources=sources,
                 portable=[str(ARTIFACT), ARTIFACT_SHA, PRODUCER_SHA])
    return bound, req
