"""Run the separately leased DS30-0220 regression challenge on saved inputs."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from three_quarter_saved import worker  # noqa: E402


CASE = "DS30-0220"
PANEL = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PAIR_PIN = "d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755"
DEVELOPMENT = Path("/dev/shm/leo-v3-three-quarter-audit01")
DONORS = (Path("/dev/shm/leo-v3-short-raw-0180-01/tle"), Path("/dev/shm/leo-v3-unseen-saved-0255-result01/tle"))
PROTOCOL = HERE / "three-quarter-challenge-protocol.md"


def prepare(stage):
    import shutil
    import json

    from three_quarter_members import accession, case_data, checked, digest, packet, read, write
    from leo.operations.tle_archive import TleArchiveReader
    from visit_frame_raw_0016 import resident

    folder = PANEL / "cases" / CASE
    pair = read(folder / "pair.json", PAIR_PIN)
    if (not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1
            or stage.parent != Path("/dev/shm") or stage.exists()):
        raise ValueError("Unexpected frozen field pair or nonprivate stage")
    detached = folder / "authority.json"
    authority = read(detached, pair["authority_sha256"])
    core = {row["algorithm"]: row for row in map(json.loads, (PANEL / "rows.jsonl").read_bytes().splitlines())
            if row["case"] == CASE and row["verified_pair"]}
    if set(core) != {"installed", "successor"} or any(row["attempt_result_sha256"] != pair["attempt_result_sha256"][name]
                                                       or row["outcome"] != "complete" for name,row in core.items()):
        raise ValueError("The original common-fix pair changed")
    result, papers = case_data(PANEL, accession()[CASE], core["installed"], core["successor"])
    previous = read(DEVELOPMENT / "audit.json")
    if digest(result) != digest(next(row for row in previous["records"] if row["case"] == CASE)) or papers is None:
        raise ValueError("The frozen strongest support or membership schedule changed")
    members, _, sampled, recipe = papers
    native, published, _ = packet(PANEL, core["successor"])
    session = authority["session_id"]
    inventory = published / "fast-scan-inputs" / (session + ".json")
    offer = PANEL / "offer.json"
    checked(inventory, authority["inventory_sha256"])
    checked(offer, authority["region_sha256"])
    cutoff = authority["causal_cutoff_utc_ns"]
    enrolled = {}
    for donor in DONORS:
        if donor.resolve(strict=True) != donor or donor.stat().st_dev != stage.parent.stat().st_dev:
            raise ValueError("Only the fixed existing physical tmpfs TLE copies are eligible")
        for ref in TleArchiveReader(donor).list_snapshots("space-track"):
            if cutoff-72*3_600_000_000_000 <= ref.collected_utc_ns < cutoff:
                enrolled.setdefault(ref.path.name, ref)
    if len(enrolled) != 50 or digest({name: ref.sha256 for name,ref in enrolled.items()}) != authority["archive_sha256"]:
        raise ValueError("Missing the exact authenticated 50-snapshot causal field archive")
    cache = resident([str(ref.path) for ref in enrolled.values()])
    for ref in enrolled.values():
        checked(ref.path, ref.sha256)
    stage.mkdir(mode=0o700)
    inputs = stage / "inputs"
    inputs.mkdir()
    archives = stage / "tle/archive/space-track"
    archives.mkdir(parents=True)
    for name, ref in enrolled.items():
        os.link(ref.path, archives / name)
    for path, name in ((detached, "authority.json"), (inventory, "inventory.json"), (offer, "offer.json")):
        shutil.copyfile(path, stage / name)
    shutil.copyfile(DEVELOPMENT / "audit.json", inputs / "audit.json")
    shutil.copyfile(DEVELOPMENT / "index-proof.json", inputs / "index-proof.json")
    write(stage / "native.json", native)
    for name, data in (("members", members), ("native", sampled), ("recipe", recipe)):
        write(inputs / f"{CASE}-{name}.json", data)
    write(stage / "challenge.json", dict(case=CASE, prospective_unscored="DS30-0144", pair_sha256=PAIR_PIN,
          protocol_sha256=sha256(checked(PROTOCOL)).hexdigest(), authority_sha256=pair["authority_sha256"],
          archive_sha256=authority["archive_sha256"], files={name:str(ref.path) for name,ref in enrolled.items()},
          cache=cache, waveform_reads=0, member_plan_sha256=digest(members), source_sha256=sha256(checked(Path(__file__))).hexdigest()))


def validate(inputs, authority, ordinary, sampled, recipe, members):
    from three_quarter_members import checked, digest, read

    frozen = read(inputs.parent / "challenge.json")
    scope = next(row for row in read(inputs / "audit.json")["records"] if row["case"] == CASE)
    if (frozen["case"] != CASE or frozen["pair_sha256"] != PAIR_PIN
            or frozen["archive_sha256"] != authority["archive_sha256"]
            or frozen["protocol_sha256"] != sha256(checked(PROTOCOL)).hexdigest()
            or frozen["source_sha256"] != sha256(checked(Path(__file__))).hexdigest()
            or digest(ordinary) != scope["historical_final_native_sha256"]
            or digest(sampled) != scope["proposed_native_sha256"] or digest(recipe) != scope["receiver_recipe_sha256"]
            or digest(members) != scope["members_sha256"] or digest(members) != frozen["member_plan_sha256"]):
        raise ValueError("The frozen regression challenge or paid support changed")
    return scope


def run(stage, output, mode, *, probe=False):
    import json

    with (stage / "challenge.json").open() as stream:
        frozen = json.load(stream)
    worker(stage / "inputs", output, probe=probe, case=CASE, stage=stage, ordinary=mode == "ordinary",
           authority_pin=frozen["authority_sha256"], validate=validate)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "ordinary", "sampled"))
    cli.add_argument("stage", type=Path)
    cli.add_argument("output", type=Path, nargs="?")
    cli.add_argument("--probe", action="store_true")
    args = cli.parse_args()
    if args.action == "prepare":
        prepare(args.stage)
    else:
        run(args.stage, args.output, args.action, probe=args.probe)
