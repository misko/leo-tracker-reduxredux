"""Bind the fixed-owner repair once to the authenticated full-short measurement packet."""

from hashlib import sha256
from time import perf_counter, process_time

from aperture_trial import read, write
from local_future_inputs import selection
from local_future_pins import checked_dependencies


POLICY = "forward-owned short factors with fixed-role future attachment v1"
TRACKS_SHA256 = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"


class LocalFuturePolicy:
    def __init__(self, ingress):
        self.ingress = ingress
        self.dependencies = checked_dependencies()
        self.native = None
        self.prepare_calls = 0

    def bind(self, native, assets):
        from leo.contracts.digests import canonical_digest

        if self.native is not None:
            raise ValueError("The local solver policy already selected this recording")
        if sha256((assets / "tracks.json").read_bytes()).hexdigest() != TRACKS_SHA256:
            raise ValueError("The local solver policy requires the pinned installed track asset")
        cpu, wall = process_time(), perf_counter()
        self.forward, self.future = selection(native)
        self.native = native
        self.native_sha256 = canonical_digest(native)
        self.forward_sha256 = canonical_digest(self.forward)
        self.selection = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)

    def prepare(self, original, native, *args, **kwargs):
        if self.native is None or self.native is not native:
            raise ValueError("The solver preparation does not bind the selected full-short packet")
        self.prepare_calls += 1
        return original(self.forward, *args, **kwargs)

    def repair(self, prepared, signed, measured):
        from local_future_repair import attach

        return attach(prepared, signed, measured, self.future)

    def seal(self, output, report):
        from leo.contracts.digests import canonical_digest
        from leo.storage.fast_scan import FastScanStore

        receipt = report["receipt"]
        workspace = FastScanStore(output).automatic_workspace(receipt["run_id"], create=False)
        terminal = read(workspace / "terminal.json")
        if (self.native is None or canonical_digest(terminal) != receipt["terminal_sha256"]
                or terminal["native_sha256"] != self.native_sha256):
            raise ValueError("Published terminal does not bind the full-short detector and local solver policy")
        route = report["route_details"] or {}
        if "local_future_repair" in route:
            status = route["local_future_repair"]["decision"]
        elif report["solve"].get("empty_receiver_withhold"):
            status = "no_probes"
        elif any(point.get("skipped_empty_graph") for point in report.get("early_regional", ())):
            status = "empty_graph"
        else:
            status = "forward_" + report["route"]
        policy_sha = canonical_digest([POLICY, self.dependencies, TRACKS_SHA256])
        write(output / "local-future-policy.json", dict(policy=POLICY, policy_sha256=policy_sha, ingress=self.ingress,
              status=status, native_sha256=self.native_sha256, forward_sha256=self.forward_sha256,
              original_receiver_sha256=self.native["provenance"]["detector_sha256"],
              terminal_sha256=receipt["terminal_sha256"], tracks_sha256=TRACKS_SHA256,
              future_ids=[row["observation_id"] for row in self.future], selection=self.selection,
              selection_passes=dict(forward=1, reverse=1), solver_preparations=self.prepare_calls,
              implementation=self.dependencies))
        return policy_sha
