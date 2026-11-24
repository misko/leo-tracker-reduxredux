"""Price first-use decoded-block authentication fusion from sealed original clocks."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


MEASURES = Path(__file__).resolve().parent / "measurements"
CASES = ("DS30-0016", "DS30-0107")
PINS = {
    "integrated-original": "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff",
    "raw-denominator-audit": "a9509fb5125a5635963fcc40b7bc2afbaace98768153fb4a0b3a07c4f9374645",
    "integrated-packed-member-0016": "1bbee8a046f5b2456dd96303bd9af6d3e0c6090169496bbb1cb0ffb2fddded65",
}
MODES = ("full", "short_primary")
APERTURE_BYTES = dict(full=1_600_000, short_primary=640_000)


def recorded(name):
    body = (MEASURES / f"{name}.json.gz").read_bytes()
    if sha256(body).hexdigest() != PINS[name]:
        raise ValueError(f"Clock receipt pin fails for {name}")
    return json.loads(gzip.decompress(body))


def seconds(nanos):
    return nanos / 1e9


def phases(storage, native, acquisition):
    members = storage["members"]
    if (storage["authority_mode"] != "verified-once" or not members
            or any(row.get("hash_prefix") is not False or row["complete_encoded_auth"]["input_blocks"] for row in members)
            or native["native_calls"] != {key: 2*native["visits"][key] for key in MODES}):
        raise ValueError("Require original no-map verification and both independently evaluated radios")
    direct_bytes = sum(row["decoded"] for row in members)
    detector_bytes = sum(native["visits"][mode] * APERTURE_BYTES[mode] for mode in MODES)
    if not 0 < detector_bytes <= direct_bytes:
        raise ValueError("Detector schedule exceeds original encoded support")

    timing = {}
    for clock, unit in (("wall", "elapsed_s"), ("cpu", "cpu_s")):
        raw = acquisition[unit]
        native_modes = {mode: seconds(native[f"native_{clock}_ns"][mode]) for mode in MODES}
        outside = raw - sum(native_modes.values())
        h = seconds(sum(row[f"hash_{clock}_ns"] for row in members))
        decode = seconds(sum(row[f"native_read_{clock}_ns"] for row in members))
        encoded_main = seconds(sum(row["complete_encoded_auth"][f"{clock}_ns"] for row in members))
        if outside < h + decode + encoded_main:
            raise ValueError("The original stage clocks do not form the expected partition")
        timing[unit] = dict(acquisition=raw, native=native_modes, outside_native=outside, decoded_sha=h,
                            decoder_including_checksum=decode, encoded_main=encoded_main,
                            other_outside_native=outside-h-decode-encoded_main)

    # Each complete member SHA hashes all its 64-byte blocks. Each
    # window can leave at most 63 bytes for SHA padding and buffering.
    payload_lower = sum(row["decoded"]//64 + max(0, (row["decoded"] - 63*row["windows"] + 63)//64)
                        for row in members)
    return dict(timing=timing, encoded_bytes=sum(row["encoded"] for row in members), decoded_bytes=direct_bytes,
                member_count=len(members), issued=sum(row["windows"] for row in members), visits=native["visits"],
                factors=native["factors"], demanded_aperture_bytes=detector_bytes, sha_payload_blocks_lower=payload_lower,
                duplicate_first_window_full_sha_blocks_upper=sum(row["largest_sample_window_bytes"]//64 for row in members))


def optimistic_credits(cases, current, installed):
    """Remove component wall clocks once, while holding all other observed intervals fixed."""
    target = installed/2
    empty = {
        "decoded_sha": sum(row["decoded_sha"] for row in cases),
        "decoder_and_decoded_sha": sum(row["decoded_sha"] + row["decoder_including_checksum"] for row in cases),
        "all_outside_native": sum(row["outside_native"] for row in cases),
        "all_native": sum(sum(row["native"].values()) for row in cases),
        "all_short_native": sum(row["native"]["short_primary"] for row in cases),
    }
    empty["half_decoder_sha_and_native"] = (empty["decoder_and_decoded_sha"] + empty["all_native"])/2
    return {name: dict(credit_s=value, elapsed_floor_s=current-value, remaining_to_half_s=current-value-target,
                       total_speedup=installed/(current-value)) for name, value in empty.items()}


def reduce():
    approved = recorded("integrated-original")
    raw = recorded("raw-denominator-audit")
    stock = {case: max((row for row in raw["observations"] if row["case"] == case and row["stratum"] == "private-tmpfs"),
                       key=lambda row: row["start_unix_ns"])["clock"]["elapsed_s"] for case in CASES}
    prefix = recorded("integrated-packed-member-0016")
    ordinary = prefix["proof"]["ordinary"]
    scoped = phases(ordinary["storage"], ordinary["receiver"]["native"], ordinary["phases"]["authenticated_raw_acquisition"])
    if (prefix["waveform_backing_bytes"] or scoped["issued"] != 64 or scoped["member_count"] != 1
            or scoped["encoded_bytes"] != prefix["rules"]["scope"]["bytes"]):
        raise ValueError("The archived physical comparison changed its authenticated first member")

    results = {}
    for order, pair in approved["runs"].items():
        partition = {}
        for case in CASES:
            doc = pair[case]["result"]["document"]
            receiver, source = doc["receiver"], doc["acquisition"]
            native = receiver["receiver_audit"]["native"]
            if (not doc["qualified"] or doc["process"]["exit_code"]
                    or source["history_sha256"] != ordinary["storage"]["history_sha256"]
                    or native["installed_sha256"] != ordinary["receiver"]["native"]["installed_sha256"]
                    or native["short_primary_sha256"] != ordinary["receiver"]["native"]["short_primary_sha256"]
                    or source["acceleration"]["artifacts"]["hasher"] != ordinary["storage"]["acceleration"]["artifacts"]["hasher"]):
                raise ValueError("Original prefix and integration require the same deployed numerical and decoded input kernels")
            partition[case] = phases(source, native, receiver["phases"]["authenticated_raw_acquisition"]) | dict(
                native_sha256=doc["rebound_request"]["native"], process=doc["process"]["elapsed_s"],
                prefetch_worker_cpu_s=seconds(receiver["prefetch"]["worker_cpu_ns"]))
        current = sum(run["process"] for run in partition.values())
        duplicate = sum(recording["duplicate_first_window_full_sha_blocks_upper"] for recording in partition.values())
        count = sum(recording["sha_payload_blocks_lower"] for recording in partition.values())
        results[order] = dict(recordings=partition, current_total_s=current, gap_s=current-sum(stock.values())/2,
                              first_window_sha_payload_block_reuse_ceiling=duplicate/count,
                              optimistic=optimistic_credits([run["timing"]["elapsed_s"] for run in partition.values()],
                                                            current, sum(stock.values())))

    return dict(sources_sha256=PINS, integrated_source=approved["as_run_commit"], stock_s=stock, cases=CASES,
                original_first_member=scoped | dict(original_member_sha256=ordinary["storage"]["members"][0]["member_sha256"],
                                                    signed_native_sha256=prefix["signed_probe_sha256"]),
                scenarios=results, new_waveform_bytes=0, new_benchmark_children=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    report = reduce()
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
