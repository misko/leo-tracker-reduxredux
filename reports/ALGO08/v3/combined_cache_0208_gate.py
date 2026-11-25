"""Wait for one official pair and census its pages before dropping privilege."""

import argparse
import json
import os
import pwd
import stat
import subprocess
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep, time_ns

CASE = "DS30-0208"
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PYTHON = "/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python"
RELEASE_SRC = "/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src"


def digest(body):
    return sha256(body).hexdigest()


def document(path, pin):
    body = path.read_bytes()
    if digest(body) != pin.removeprefix("sha256:"):
        raise ValueError(f"The enrolled identity changed: {path.name}")
    return json.loads(body)


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return digest(path.read_bytes())


def official_pair(root, body, book):
    pair = json.loads(body)
    if not pair["verified_pair"] or pair["state"] != "observed_pair":
        raise ValueError("The enrolled official original pair did not verify")
    generation = pair["generation"]
    if type(generation) is not int or generation < 1:
        raise ValueError("Invalid official generation")
    authority = document(root / "authority.json", pair["authority_sha256"])
    if (
        any(authority[key] != value for key, value in book["expected"].items())
        or authority["region_sha256"] != book["offer_sha256"]
    ):
        raise ValueError("The official pair differs from the prospective original/causal binding")
    for role in ("installed", "successor"):
        result = document(
            root / role / f"attempt-{generation:06d}" / "result.json",
            pair["attempt_result_sha256"][role],
        )
        if (
            result["raw_identity"] != authority
            or result["authority_sha256"] != pair["authority_sha256"]
        ):
            raise ValueError("One selected official raw receipt failed original custody")
    return authority


def missing_pages(roster, observed):
    expected = {row["path"]: row["size"] for row in roster}
    actual = {entry["file"]: entry["size"] for entry in observed}
    if len(observed) != len(expected) or actual != expected:
        raise ValueError("The privileged page census differs from the signed source roster")
    return [row for row in observed if row["res"] < row["size"]]


def observe(root, book):
    deadline = monotonic() + 84_600
    pair_file = root / "pair.json"
    while not pair_file.is_file() and monotonic() < deadline:
        sleep(0.5)
    if not pair_file.is_file():
        return dict(state="expired_before_official_verification")
    body = pair_file.read_bytes()
    authority = official_pair(root, body, book)
    paths = [row["path"] for row in book["files"]]
    for row in book["files"]:
        path = Path(row["path"])
        info = path.lstat()
        if (
            path.resolve(strict=True) != path
            or not stat.S_ISREG(info.st_mode)
            or info.st_size != row["size"]
            or info.st_dev != os.makedev(252, 5)
        ):
            raise ValueError("A census path differs from its sealed physical extent")
    result = subprocess.run(
        ["/usr/bin/fincore", "--bytes", "--json", "-o", "FILE,RES,SIZE", *paths],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr.strip():
        raise ValueError("Privileged page census was ambiguous: " + result.stderr.strip())
    observed = json.loads(result.stdout)["fincore"]
    missing = missing_pages(book["files"], observed)
    return dict(
        state="admit_cache_copy" if not missing else "refused_missing_source_pages",
        all_pages_resident=not missing,
        missing=missing,
        missing_file_bytes=sum(row["size"] - row["res"] for row in missing),
        resident_roster_sha256=digest(json.dumps(observed, sort_keys=True).encode()),
        cache_observations=observed,
        pair_sha256=digest(body),
        authority=authority,
        observed_unix_ns=time_ns(),
        source_payload_bytes_read=0,
    )


def arm(args):
    if os.geteuid() or os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Run the privileged metadata-only gate on low-priority CPU 3")
    if args.book.stat().st_uid or args.book.stat().st_mode & 0o022:
        raise ValueError("The gate needs a root-owned immutable enrollment document")
    book = document(args.book, args.book_pin)
    if book["case"] != CASE or book["rank"] != 96 or len(book["files"]) != 164:
        raise ValueError("Only the prospectively assigned original can arm")
    document(CAMPAIGN / "plan.json", book["official_plan_sha256"])
    parent = args.book.parent
    write(
        parent / "armed.json",
        dict(
            case=CASE,
            plan_sha256=args.book_pin,
            state="waiting_for_official_verified_pair",
            started_unix_ns=time_ns(),
        ),
    )
    try:
        answer = observe(CAMPAIGN / "cases" / CASE, book)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        answer = dict(state="refused", reason=str(error), source_payload_bytes_read=0)
    gate = parent / "decision.json"
    pin = write(gate, answer)
    if answer["state"] != "admit_cache_copy":
        return
    if digest(args.actor.read_bytes()) != args.actor_pin:
        raise ValueError("The enrolled copy worker changed before privilege drop")
    driver = subprocess.check_output(
        [
            "/usr/bin/systemctl",
            "show",
            "-p",
            "MainPID",
            "--value",
            "leo-ds30-paired-evaluation-20261124.service",
        ],
        text=True,
    ).strip()
    account = pwd.getpwnam("leo")
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.execve(
        PYTHON,
        [
            PYTHON,
            "-B",
            str(args.actor),
            "capture",
            "--book",
            str(args.book),
            "--book-pin",
            args.book_pin,
            "--gate",
            str(gate),
            "--gate-pin",
            pin,
            "--driver-pid",
            driver,
        ],
        dict(
            PATH="/usr/bin:/bin",
            PYTHONPATH=RELEASE_SRC,
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--book", type=Path, required=True)
    cli.add_argument("--book-pin", required=True)
    cli.add_argument("--actor", type=Path, required=True)
    cli.add_argument("--actor-pin", required=True)
    arm(cli.parse_args())
