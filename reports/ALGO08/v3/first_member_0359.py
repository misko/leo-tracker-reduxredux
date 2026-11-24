"""Passively check only the first signed original DS30-0359 member."""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
from time import time_ns

from reports.ALGO08.v3.first_member_0419 import (
    CACHE, CACHE_PIN, SPOOL, bound_index, metadata, payload_cache, select_first,
)
from tools.pipeline_eval.qualification.cache_residency import load_query


CASE = "DS30-0359"
READY = Path("/dev/shm/leo-v3-combined-0359-blind01-ready")
REQUEST_PIN = "887417b3a777a73b91fead0a281cb793ceb57f4d3cd01fcb7cd01b05bfa74432"
INVENTORY_PIN = "8b83a568e5dfd8bc43cfd580ec042d1860ac194983f147549634ea8140021e6b"
LOCAL_ROOTS = (Path("/dev/shm"), Path("/tmp"), READY,
               Path("/dev/shm/leo-v3-combined-0359-blind01"), Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE)


def local_observation(recording, segment, signed, member, *, roots=LOCAL_ROOTS, spool=SPOOL):
    """Check only exact enrolled names, with no recursion or payload access."""
    original_device = recording.stat().st_dev
    rows = []
    for parent in (*roots, spool):
        path = parent / recording.name
        row = dict(path=str(path), status="absent")
        try:
            info = path.lstat()
            row.update(status="unverified", device=info.st_dev, target=str(path.resolve(strict=True)))
            if stat.S_ISLNK(info.st_mode) or row["target"] != str(path):
                row["status"] = "original_alias" if row["target"] == str(recording) else "unadmitted_alias"
            elif not stat.S_ISDIR(info.st_mode) or info.st_dev == original_device:
                row["status"] = "not_independent_directory"
            else:
                item = path / segment.name
                if item.resolve(strict=True) != item:
                    raise ValueError("Local segment alias")
                checked, _ = bound_index(item, signed)
                content = (item / member["payload_relative_path"]).lstat()
                if (checked != member or not stat.S_ISREG(content.st_mode) or content.st_dev != info.st_dev
                        or content.st_size != member["compressed_bytes"]):
                    raise ValueError("Local extent does not match the signed first member")
                row["status"] = "local_first_member_metadata_match"
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            row.update(status="unverified", error=str(error))
        rows.append(row)
    return rows


def run(output):
    started = time_ns()
    request = json.loads(metadata(READY / "request.json", REQUEST_PIN, 96_000))
    inventory = json.loads(metadata(READY / "inventory.json", INVENTORY_PIN, 96_000))
    segment, signed = select_first(request, inventory, case=CASE, inventory_pin=INVENTORY_PIN)
    if segment.resolve(strict=True) != segment:
        raise ValueError("Unexpected alias in the original signed segment path")
    member, rows = bound_index(segment, signed)
    payload = segment / member["payload_relative_path"]
    owner = payload.lstat().st_uid
    if os.geteuid() != owner:
        raise ValueError("Run the passive residency observation as the original file owner")
    metadata(CACHE, CACHE_PIN, 80_000)
    cache = payload_cache(payload, member["compressed_bytes"], load_query(CACHE), os.sysconf("SC_PAGE_SIZE"))
    mount = json.loads(subprocess.check_output(["findmnt", "--json", "-o", "SOURCE,FSTYPE,TARGET,MAJ:MIN",
                                               "-T", str(payload)]))["filesystems"]
    local = local_observation(segment.parent, segment, signed, member)
    resident = cache["cached_pages"] == cache["file_pages"]
    candidate = any(entry["status"] == "local_first_member_metadata_match" for entry in local)
    disposition = "review_candidate" if resident or candidate else "deferred"
    result = dict(case=CASE, request_sha256=REQUEST_PIN, inventory_sha256=INVENTORY_PIN,
                  session=request["session"], recording=request["recording"], issued=request["issued"],
                  raw_authority=request["raw_authority"], signed_segment_count=len(inventory["segments"]),
                  first_segment=signed, first_member=member, signed_rows=len(rows), cache=cache,
                  cache_observer_sha256=CACHE_PIN, owner_uid=owner, observation_uid=os.geteuid(), mount=mount,
                  first_member_fully_resident=resident, named_local_observations=local, disposition=disposition,
                  payload_bytes_read=0, waveform_bytes_copied=0, measured_children=0,
                  started_unix_ns=started, ended_unix_ns=time_ns())
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipt", type=Path)
    run(cli.parse_args().receipt)
