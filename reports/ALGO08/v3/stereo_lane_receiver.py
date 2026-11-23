"""Acquire each paid antenna lane on the frozen alternating short-visit schedule."""

from collections import Counter
from contextlib import ExitStack, contextmanager

from mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath, strongest, verified
from stereo_lane_schedule import StereoSchedule


class StereoLaneReceiver(MixedApertureDetector):
    def __init__(self, short_binary, short_sha256, mode):
        super().__init__(short_binary, short_sha256, full_coverage=True)
        self.mask = StereoSchedule(mode)
        self.mode = mode
        self.omitted_by_radio = Counter()

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        import numpy as np
        from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate

        if method != "cancellation" or edge in self.active:
            raise ValueError("Expected one signed receiver context per pilot edge")
        verified(binary, INSTALLED_SHA)
        verified(self.short_binary, self.short_sha256)
        asset = np.frombuffer(verified(pilot, PILOT_SHA[edge]), dtype="<f4")
        if asset.shape != (133413,):
            raise ValueError("Unexpected pilot length")
        with ExitStack() as resources:
            engines = {}
            for mode, path in (("full", binary), ("short_primary", self.short_binary)):
                engines[mode] = NativePath(path, asset, mode)
                resources.callback(engines[mode].close)
            self.active.add(edge)
            resources.callback(self.active.remove, edge)
            open_scope = True

            def receive(window):
                if not open_scope:
                    raise RuntimeError("The signed receiver context has closed")
                samples = window.samples
                if (tuple(window.receiver_ids) != (0, 1) or window.sample_rate_hz != 10_000_000
                        or samples.shape != (200_000, 2, 2) or samples.dtype != np.dtype("<i2")
                        or not samples.flags.c_contiguous):
                    raise ValueError("Expected the authenticated 20 ms stereo CI16 window")
                target, acquisition = window.target, window.acquisition
                _, mode = self.schedule.visit(edge, target, acquisition)
                rf = float(acquisition["actual_if_center_hz"] + target["lnb_lo_hz"])
                aperture, omitted = self.mask.next((edge, target["channel"], rf))
                if mode != aperture or (mode == "full" and omitted is not None):
                    raise ValueError("Mask and authenticated aperture schedule disagree")
                self.visits[mode] += 1
                # Keep the original operation order for the signed kernel's frequency centre.
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                probes = []
                for lane in window.receiver_ids:
                    candidates = []
                    if lane == omitted:
                        self.omitted_by_radio[lane] += 1
                    else:
                        measured, (cpu, wall) = engines[mode].run(samples, lane, center)
                        self.native_calls[mode] += 1
                        self.native_cpu_ns[mode] += cpu
                        self.native_wall_ns[mode] += wall
                        selected = strongest([factor_candidate(rank, epoch, status="complete", offset=offset,
                                              cfo=hz, exact=exact, control=roll, margin=exact-roll)
                                              for rank, epoch, offset, hz, exact, roll in measured])
                        if selected is not None:
                            candidates.append(selected)
                            self.factors[mode] += 1
                    probes.append(_probe(window, lane, candidates))
                return probes

            try:
                yield receive
            finally:
                open_scope = False

    def receipt(self):
        paid = sum(self.native_calls.values())
        if paid + sum(self.omitted_by_radio.values()) != 2 * sum(self.visits.values()):
            raise ValueError("Paid and omitted calls must cover every admitted lane")
        return super().receipt() | dict(short_lane_mask=self.mode, omitted_by_radio=dict(self.omitted_by_radio))
