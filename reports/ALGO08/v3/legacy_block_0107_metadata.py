"""Verify DS30-0107 signed metadata without opening its waveform payload."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
BENCH = Path("/dev/shm/leo-v3-continued-cfo-0107-pair01")
ARCHIVED = Path("/dev/shm/leo-v3-history-risk-0107-cairo-score02.json")
PRIOR = Path("/dev/shm/leo-v3-history-risk-0107-cairo-result01/admission.json")
PINS = {
    BENCH/"admission.json": "81a5aa37a01356e56619945b194c831314fdf856175c55a1f90492b2585d6260",
    ARCHIVED: "6f6923e6a4be803069581d5a254148c6e322d9e0c4ea4e93de1062dd2bb485e9",
    PRIOR: "fd434a13bc6d12d1bcd14941f3445d78f1652b2e19a2e5359078637ed8ad4e06",
}
ENTRY = Path("/dev/shm/leo-v3-legacy-block-raw-0016")
CODE = ("legacy_block_raw_entry.py", "legacy_block_input.py", "legacy_block_seek.py", "legacy_block_seek.c",
        "exact_named_raw.py", "unified_short_bootstrap.py", "history_cairo_render.py")
ORBIT_INDEX = Path("/dev/shm/leo-v3-portable-orbit-prep-02/dense-orbits.bin")
BODY_PIN = "fc51655ff19185cc382aeed925e466cea7290453256d45f80446aceef6f9e30e"
PRODUCER_PIN = "c1c2f5d911c978ad7673a2a53f05e272806f87c539f2f0a552b7e02916fe9c8b"


def digest(body):
    return sha256(body).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if digest(data) != expected.removeprefix("sha256:"):
        raise ValueError(f"The signed metadata or prior receipt changed: {path}")
    return data


def direct_tmpfs(path):
    if path.resolve(strict=True) != path or path.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError(f"Require already staged direct tmpfs custody: {path}")
    return path


def index_counts(index, member):
    offset = 0
    occurrences = Counter()
    short = []
    for ordinal, row in enumerate(index, member["first_sequence"]):
        count = row["sample_count"]
        if (row["sequence"] != ordinal or row["payload_offset_bytes"] != offset or row["receiver_count"] != 2
                or not 0 <= count <= 200_000 or row["payload_bytes"] != count*8):
            raise ValueError("The original index must retain a complete signed sequence and byte partition")
        offset += row["payload_bytes"]
        occurrences[count] += 1
        if count != 200_000:
            short.append(dict(sequence=ordinal, sample_count=count, bytes=row["payload_bytes"], iq_sha256=row["iq_sha256"]))
    if len(index) != member["window_count"] or offset != member["uncompressed_bytes"]:
        raise ValueError("The signed row roster does not cover the original payload extent")
    return dict(sample_extents=dict(sorted(occurrences.items())), nonfull=short, visits=len(index), decoded_bytes=offset)


def fincore(paths):
    rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,FILE", *paths]))["fincore"]
    if len(rows) != len(paths) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("The recorded original and causal inputs must still be fully resident")
    return dict(bytes=sum(row["size"] for row in rows), files=len(rows), status="fully resident by passive page census")


def metadata(source):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    old, scored, cap = (json.loads(checked(direct_tmpfs(path), key)) for path, key in PINS.items())
    req = scored["admission"]["request"]
    original = Path(req["recording"])
    stage = direct_tmpfs(BENCH/original.name)
    scope = {kind: direct_tmpfs(stage/Path(row["path"]).relative_to(original)) for kind, row in old["members"].items()}
    if set(scope) != {"manifest", "index", "payload"} or any(p.stat().st_size != old["members"][kind]["bytes"] for kind, p in scope.items()):
        raise ValueError("The enrolled one-member original stage changed")
    manifest = json.loads(checked(scope["manifest"], old["members"]["manifest"]["sha256"]))
    lines = [json.loads(line) for line in checked(scope["index"], old["members"]["index"]["sha256"]).splitlines()]
    member, = manifest["chunks"]
    extents = index_counts(lines, member)
    if (not scored["qualified"] or scored["decisions"]["DS30-0107"] != "withheld" or req != cap["request"]
            or req["inventory"] != old["inventory"] or req["session"] != old["session"] or req["authority"] != old["raw_authority"]
            or canonical_digest([req["inventory"], [row["iq_sha256"] for row in lines]]) != req["authority"]
            or member["compressed_sha256"] != old["members"]["payload"]["sha256"]
            or member["compressed_bytes"] != old["members"]["payload"]["bytes"]
            or member["index_sha256"] != old["members"]["index"]["sha256"]
            or extents["sample_extents"] != {0: 1, 136857: 1, 200000: 27}):
        raise ValueError("Expected the complete authenticated 29-visit physical fixture and prior withholding")
    archive = direct_tmpfs(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (archive_identity(archive) != req["archive"] or len(refs) != 51
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The original causal cutoff and archive identity changed")
    checked(direct_tmpfs(Path(req["region"])), req["offer_sha256"])
    producer_path = direct_tmpfs(ORBIT_INDEX.parent/"artifact-bind.json")
    producer = json.loads(checked(producer_path, PRODUCER_PIN))
    checked(direct_tmpfs(ORBIT_INDEX), BODY_PIN)
    overlap = len(set(producer["source"]["body_digests"]) & {ref.sha256 for ref in refs})
    if producer["portable_sha256"] != "sha256:"+BODY_PIN or not 0 < producer["source"]["cutoff_utc_ns"] < req["cutoff_utc_ns"]:
        raise ValueError("Only the same verified earlier portable artifact is eligible")
    revision = subprocess.check_output(["git", "-c", f"safe.directory={source}", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    if any(not (source/"reports/ALGO08/v3"/name).is_file() for name in CODE):
        raise ValueError("No generic original-file worker is available for source inspection")
    return dict(case="DS30-0107", request=req, signed_stage=str(stage), metadata_pins={str(p): pin for p, pin in PINS.items()},
                files={kind: dict(old["members"][kind], stage=str(path)) for kind, path in scope.items()}, geometry=extents,
                resident=dict(input=fincore(list(scope.values())), catalogue=fincore([direct_tmpfs(ref.path) for ref in refs]),
                              index=fincore([ORBIT_INDEX, producer_path])), portable=dict(body_sha256=BODY_PIN,
                    producer_sha256=PRODUCER_PIN, earlier_cutoff=producer["source"]["cutoff_utc_ns"], overlap=overlap,
                    expected_activation="on numerical entry only"), prior_ordinary_command=cap["command"],
                reader_source=dict(revision=revision, files={name: digest((source/"reports/ALGO08/v3"/name).read_bytes()) for name in CODE},
                                   finalized_after_positive_control=True),
                frozen_protocol_sha256=digest((HERE/"legacy-block-raw-0107-protocol.md").read_bytes()),
                waveform_opened_bytes=0, raw_children=0, awaiting_positive_qualification=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--reader-source", type=Path, default=ENTRY)
    args = cli.parse_args()
    result = metadata(args.reader_source)
    with args.output.open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")
