"""Replay one saved fixed native capture through host-adaptive analysis; no RF.

Policy/counters are synthetic and output is isolated. This measures native
analysis/publication cost, not adaptive allocation benefit or sensitivity.
"""

import argparse
import json
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leo.application.adaptive_hop_analysis import HostAdaptiveAnalysisService
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.contracts.digests import canonical_digest
from leo.presentation.adaptive_hop_analysis import render_host_adaptive_hop_overview
from leo.scanner.host_adaptive_analysis import HostAdaptiveAnalysisSource
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.persistent_hop import PersistentHopIqStore
from tests.scanner.host_adaptive_fixtures import host_receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    store = PersistentHopIqStore.open_read_only(args.bulk_root)
    recorded = store.inspect(args.session)
    original = recorded.manifest.receipt
    if original.plan.sample_rate_hz != 10_000_000 or len(original.plan.receiver_ids) != 1:
        raise ValueError("replay requires native single-RX recording")
    retained = len(original.visits)
    receipt = host_receipt(
        receiver=original.plan.receiver_ids[0],
        mode="shadow",
        count=retained + 1,
        session_id="synthetic-native-cadence-replay",
    )
    reader = store.valid_ci16_reader(recorded)

    class Reader:
        session_id = receipt.session_id
        input_manifest_sha256 = canonical_digest(
            {
                "fixed_source": recorded.manifest_sha256,
                "synthetic_receipt": receipt.model_dump(mode="json"),
            }
        )

        def read_visit_ci16(self, index):
            return receipt.visits[index], reader.read_valid_ci16(
                index * 1_200_000,
                1_200_000,
            )

    source_reader = Reader()
    source_reader.receipt = receipt

    class Inputs:
        @contextmanager
        def source(self, session_id):
            if session_id != receipt.session_id:
                raise ValueError("unknown synthetic replay")
            yield HostAdaptiveAnalysisSource(source_reader)

    inputs = Inputs()
    products = AdaptiveHopAnalysisStore(args.output)
    start = time.monotonic()
    report = {
        "source_session": args.session,
        "source_manifest_sha256": recorded.manifest_sha256,
        "synthetic_policy_and_counters": True,
        "hardware_accessed": False,
        "physical_receiver": original.plan.receiver_ids[0],
        "visits": retained,
        "python": sys.executable,
        "probe_stride_ms": 120,
        "maximum_workers": 4,
    }
    try:
        result = HostAdaptiveAnalysisService(inputs=inputs, products=products).analyze_session(
            receipt.session_id,
            probe_stride_ms=120,
            maximum_workers=4,
            maximum_seconds=580,
        )
        report["analysis"] = asdict(result)
        report["analysis_elapsed_seconds"] = time.monotonic() - start
        if result.state != "metrics_complete":
            raise ValueError("saved native analysis did not finish within its budget")
        rendered = AdaptiveHopOverviewService(
            inputs=inputs,
            products=products,
            renderer=render_host_adaptive_hop_overview,
        ).render_session(receipt.session_id, probe_stride_ms=120)
        report["presentation"] = rendered.model_dump(mode="json")
        report["elapsed_seconds"] = time.monotonic() - start
        report["within_600_seconds"] = report["elapsed_seconds"] < 600
        if not report["within_600_seconds"]:
            raise ValueError("saved native analysis exceeded ten-minute cadence")
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - start
        (args.output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
        products.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
