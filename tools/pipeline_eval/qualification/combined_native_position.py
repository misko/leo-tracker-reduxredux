"""Run the fresh compact solve with the public request digest field."""

import argparse
from unittest.mock import patch

from ..__main__ import local_output
from . import combined_native_pace as live
from . import combined_native_results as results
from . import support_cross_trial as receiver


def typed_request(row):
    digest = row["request_sha256"]
    if row.get("prepared_request_sha256", digest) != digest:
        raise ValueError("compact request digest fields disagree")
    return row | {"prepared_request_sha256": digest}


def run(work):
    if (live.PACED / "position-lock.json").exists():
        results.endpoint()
        return
    if (live.PACED / "position-input-lock.json").exists():
        results.finish_staged(work)
    else:
        solve = receiver.service

        def bind(folder, entry):
            return solve(folder, typed_request(entry))

        with patch.object(receiver, "service", bind):
            live.fit(work)
    results.endpoint()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
