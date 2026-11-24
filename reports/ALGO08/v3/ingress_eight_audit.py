"""Attribute the complete released 20/8 ms reader on one signed resident member."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from .dense_ingress_attribution import attributed_ingress, line_rows
from . import independent_8ms_0169 as prior
from . import receiver_ceiling_0169 as measured
from .signed_ingress_reuse import AcquisitionCosts


HERE = Path(__file__).resolve().parent
REFERENCE = Path("/dev/shm/leo-independent-8ms-0169-result02/measured8.json")
PIN = "0c6055720b8f4d0a50c7e446165256f0a1431a6d9a7734358e7f2a41f0c12c19"
PROTOCOL = HERE/"ingress-eight-audit-protocol.md"
NATIVE = ("full", "short_primary")


class Costs(AcquisitionCosts):
    def time(self, stage, operation, *args, **kwargs):
        if stage == "decoded_sha":
            stage = {"window": "window_and_member_sha", "digest": "member_sha_finalize"}[operation.__name__]
        return super().time(stage, operation, *args, **kwargs)


class WindowView:
    """Observe the installed frombuffer operation without changing its array."""

    def __init__(self, numpy, costs):
        self.numpy, self.costs = numpy, costs
        self.input_bytes = self.owned = self.copied = 0

    def __getattr__(self, name):
        return getattr(self.numpy, name)

    def frombuffer(self, raw, *args, **kwargs):
        result = self.costs.time("decoded_view", self.numpy.frombuffer, raw, *args, **kwargs)
        self.input_bytes += len(raw)
        self.owned += result.base is raw and type(raw) is bytes
        self.copied += result.flags.owndata
        return result


def split(row, costs):
    """Subtract the only two enclosing intervals before pricing the residual."""
    result = {}
    for timer, total in (("cpu_ns", "acquire_cpu_ns"), ("wall_ns", "acquire_wall_ns")):
        stages = dict(costs[timer])
        stages["compressed_sha_and_framing"] = stages.pop("compressed_verified") - stages["compressed_descriptor"]
        hot = row["native_" + timer]
        stages.update({f"native_{mode}": hot[mode] for mode in NATIVE})
        stages["other_callback"] = stages.pop("callback") - sum(hot.values())
        stages["unassigned"] = row[total] - sum(stages.values())
        if min(stages.values()) < 0:
            raise ValueError("Acquisition observer measured overlapping stages")
        result[timer] = stages
    return result


def byte_budget(row, member):
    calls = row["native_schedule"]["native_calls"]
    if calls != {"full": 16, "short_primary": 86} or member["uncompressed_bytes"] != 102_400_000:
        raise ValueError("This byte budget requires the signed one-member schedule")
    consumer = calls["full"] // 2 * 200_000 * 8 + calls["short_primary"] // 2 * 80_000 * 8
    return dict(physical_reads=member["compressed_bytes"], detector_apertures=consumer,
                required_decoded=member["uncompressed_bytes"], out_of_detector=member["uncompressed_bytes"]-consumer)


def worker(output):
    from leo.storage import short_window
    from leo.contracts.digests import canonical_digest
    from .full_short_run import checked_recipe

    scope = prior.read(prior.STAGED/"scope.json")
    archived = prior.read(REFERENCE, expected=PIN)
    resident_before = prior.residency(scope)
    cold = measured.cold
    spec = json.loads(cold.verified(cold.PAYLOAD/"spec.json", cold.SPEC_SHA))
    frozen = cold.frozen_function
    buffer = frozen(spec, "receiver_ingress.py", "compressed_input_buffer")
    costs = Costs()
    view = WindowView(short_window.np, costs)
    reader = short_window.ShortWindowReader
    old_init = reader.__init__
    engine = measured.MixedApertureDetector
    old_factory = engine.detector

    def manifest(*args, **kwargs):
        return costs.time("manifest_and_identity", old_init, *args, **kwargs)

    @contextmanager
    def detector(*args, **kwargs):
        start = process_time_ns(), perf_counter_ns()
        with old_factory(*args, **kwargs) as original:
            costs.cpu_ns["detector_context_enter"] += process_time_ns()-start[0]
            costs.wall_ns["detector_context_enter"] += perf_counter_ns()-start[1]
            costs.calls["detector_context_enter"] += 1
            yield lambda window: costs.time("callback", original, window)

    def reuse_current_buffer(specification, source, name):
        # The measured binding enters this exact released buffer once around
        # acquire. Leave its scoped descriptor live during the original call.
        if (source, name) == ("receiver_ingress.py", "compressed_input_buffer"):
            return nullcontext
        return frozen(specification, source, name)

    recipe = checked_recipe(eight_ms=True)
    with (patch.object(short_window, "np", view),
          attributed_ingress(buffer, costs, line_rows),
          patch.object(cold, "frozen_function", reuse_current_buffer),
          patch.object(reader, "__init__", manifest),
          patch.object(engine, "detector", detector),
          patch.object(measured, "ORIGINAL", prior.EIGHT.parent),
          patch.object(measured, "SHORT_SHA", prior.EIGHT_SHA),
          patch.object(measured, "recipe", lambda _: recipe)):
        row = measured.acquire(prior.STAGED, "full-short")
    resident_after = prior.residency(scope)
    for key in ("packet", "trace", "iq", "original_member_reads"):
        if canonical_digest(row[key]) != canonical_digest(archived[key]):
            raise ValueError(f"Measured provenance changed versus genuine 20/8 ms control: {key}")
    evidence = costs.receipt()
    member = scope["member"]
    expected = {"manifest_and_identity": 1, "compressed_descriptor": 1, "compressed_verified": 1,
                "index_verified": 1, "index_model": 1, "zstd_read": 65,
                "window_and_member_sha": 64, "member_sha_finalize": 1,
                "retune_json": 64, "support_gate": 64, "callback": 51,
                "iq_authority": 1, "detection_authority": 1, "decoded_view": 64}
    if (any(evidence["calls"].get(k) != v for k, v in expected.items())
            or evidence["verified_members"] != row["original_member_reads"]
            or evidence["decoded_members"] != [member["uncompressed_sha256"]]
            or (view.input_bytes, view.owned, view.copied) != (member["uncompressed_bytes"], 64, 0)):
        raise ValueError("The measured reader lost an original verification or changed byte ownership")
    shadow = dict(acquisition={key: row[key] for key in row if key not in ("packet", "trace")}, work=evidence,
                  disjoint=split(row, evidence), member=member, bytes=byte_budget(row, member),
                  equal_packet_sha256=canonical_digest(row["packet"]), equal_trace_sha256=canonical_digest(row["trace"]),
                  resident_before=resident_before, resident_after=resident_after, original_ref_sha256=PIN,
                  comparators={k: archived[k] for k in ("acquire_cpu_ns", "acquire_wall_ns", "native_cpu_ns", "native_wall_ns")},
                  numpy_views=dict(windows=view.owned, copied_payloads=view.copied, source_bytes=view.input_bytes))
    measured.freeze(output, shadow)


def launch(root):
    from . import sparse_cold_input as cold
    from .full_short_cold import check_machine
    from .short_raw_diagnostic import measure
    import os

    machine = check_machine()
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Only fresh tmpfs audit output is authorized")
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the measured protocol and observer before launch")
    prior.residency(prior.read(prior.STAGED/"scope.json"))
    root.mkdir()
    result = root/"profile.json"
    python = cold.RELEASE/"venv/bin/python"
    command = ["/usr/bin/timeout", "--kill-after=2s", "20s", python, "-BPs", "-m", __spec__.name, "worker", result]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
        checkout, HERE, cold.RELEASE/"src", cold.RELEASE, cold.PAYLOAD))))
    measured.freeze(root/"binding.json", dict(machine=machine, command=list(map(str, command)),
                    commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                    sources={path.name: sha256(path.read_bytes()).hexdigest() for path in (
                        Path(__file__), PROTOCOL, HERE/"dense_ingress_attribution.py", HERE/"signed_ingress_reuse.py",
                        HERE/"independent_8ms_0169.py", HERE/"receiver_ceiling_0169.py")},
                    reference_sha256=PIN))
    clock = measure(command, env, root/"profile")
    measured.freeze(root/"clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker}[args.action](args.output)
