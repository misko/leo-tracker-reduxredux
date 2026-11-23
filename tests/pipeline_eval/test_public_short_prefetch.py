from copy import deepcopy
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.public_short_prefetch import validate, verify_residency


def test_residency_checks_exact_page_extent_for_each_source_file():
    stats = {"observed_members": 1, "observed_file_pages": 2, "cached_pages": 2, "unavailable": {}}
    assert verify_residency(stats, 4097, 4096) == 2
    with pytest.raises(ValueError, match="resident"):
        verify_residency(stats | {"cached_pages": 1}, 4097, 4096)


def reference():
    chunks = [SimpleNamespace(index_relative_path=f"{n}.jsonl", index_bytes=2, index_sha256=f"idx-{n}",
                              payload_relative_path=f"{n}.zst", compressed_bytes=n+1, compressed_sha256=f"zstd-{n}",
                              uncompressed_sha256=f"raw-{n}") for n in range(3)]
    record = dict(source={"probes": list(range(2400))}, clock_anchor={"counter": 1}, delivery_clocks=list(range(1200)))
    packet = dict(source={"probes": record["source"]["probes"][:384]}, clock_anchor=record["clock_anchor"],
                  delivery_clocks=record["delivery_clocks"][:192])
    members = [item for n in range(3) for item in ((f"{n}.jsonl", 2, f"idx-{n}"), (f"{n}.zst", n+1, f"zstd-{n}"))]
    row = dict(checked={"verified_members": list(map(list, members)),
                        "decoded_members": [f"raw-{n}" for n in range(3)], "calls": {"decoded_sha": 195}},
               native={"native_calls": {"full": 48, "short_primary": 336}}, ingress="prefetch",
               overlap={"submitted": 2, "hits": 2, "fallback": 0, "hit_bytes": 5}, worker_cpus=[2])
    return row, chunks, packet, record


def test_prefetch_must_reproduce_original_probes_and_every_digest_level():
    row, chunks, packet, record = reference()
    validate(row, chunks, packet, record)
    wrong = deepcopy(row)
    wrong["checked"]["decoded_members"][0] = "different"
    with pytest.raises(ValueError, match="verified members"):
        validate(wrong, chunks, packet, record)
    packet["source"]["probes"][15] = "different"
    with pytest.raises(ValueError, match="waveform"):
        validate(row, chunks, packet, record)


def test_worker_must_stay_on_the_single_acquisition_core():
    row, chunks, packet, record = reference()
    with pytest.raises(ValueError, match="read-ahead"):
        validate(dict(row, worker_cpus=[2, 3]), chunks, packet, record)
