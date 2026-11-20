"""Resident standalone original-schedule detector and native packet projection."""

import ctypes as ct
from pathlib import Path

SOURCE = Path(__file__).with_suffix(".c")
EDGES = ("lower", "upper")
UNBRACKETED, COMPLETE = "unbracketed", "complete"
INTEGER_GATE, FRACTIONAL_GATE, FRACTIONAL_COMPLETE = 1, 2, 4


class Candidate(ct.Structure):
    _fields_ = [
        *((name, ct.c_uint) for name in ("epoch", "coarse_epoch", "seed_index", "flags")),
        *(
            (name, ct.c_double)
            for name in (
                "coarse_cfo",
                "coarse_score",
                "acquired_cfo",
                "acquisition_score",
                "integer_exact",
                "integer_control",
                "integer_residual",
                "fractional_offset",
                "fractional_exact",
                "fractional_control",
                "fractional_residual",
            )
        ),
    ]

    def packet(self, rank):
        complete = bool(self.flags & FRACTIONAL_COMPLETE)
        return dict(
            candidate_rank=rank,
            epoch_sample=self.epoch,
            acquired_cfo_hz=self.acquired_cfo,
            residual_cfo_hz=self.integer_residual,
            tracking_cfo_hz=self.acquired_cfo + self.integer_residual,
            exact_score=self.integer_exact,
            control_score=self.integer_control,
            margin=self.integer_exact - self.integer_control,
            passed_margin_gate=bool(self.flags & INTEGER_GATE),
            fractional_epoch_status=COMPLETE if complete else UNBRACKETED,
            fractional_epoch_offset_samples=self.fractional_offset if complete else None,
            fractional_frame_phase_sample=(self.epoch + self.fractional_offset) % 13333
            if complete
            else None,
            fractional_exact_score=self.fractional_exact if complete else None,
            fractional_control_score=self.fractional_control if complete else None,
            fractional_residual_cfo_hz=self.fractional_residual if complete else None,
            fractional_tracking_cfo_hz=self.acquired_cfo + self.fractional_residual
            if complete
            else None,
            fractional_margin=self.fractional_exact - self.fractional_control if complete else None,
        )


class Group(ct.Structure):
    _fields_ = [
        *((name, ct.c_uint) for name in ("lane", "anchors", "count")),
        *(
            (name, ct.c_uint64)
            for name in ("coarse_cpu", "coarse_wall", "verify_cpu", "verify_wall")
        ),
        ("candidates", Candidate * 8),
    ]

    def packets(self):
        return [
            candidate.packet(rank) for rank, candidate in enumerate(self.candidates[: self.count])
        ]

    def evidence(self, packets, published):
        return dict(
            lane=self.lane,
            anchors=self.anchors,
            published=published,
            coarse_cpu_ns=self.coarse_cpu,
            coarse_wall_ns=self.coarse_wall,
            verify_cpu_ns=self.verify_cpu,
            verify_wall_ns=self.verify_wall,
            candidates=[
                dict(
                    rank=row["candidate_rank"],
                    epoch=c.epoch,
                    coarse_epoch=c.coarse_epoch,
                    seed_index=c.seed_index,
                    flags=c.flags,
                    coarse_cfo_hz=c.coarse_cfo,
                    coarse_score=c.coarse_score,
                    acquired_cfo_hz=c.acquired_cfo,
                    acquisition_score=c.acquisition_score,
                    integer_margin=row["margin"],
                    fractional_offset_samples=row["fractional_epoch_offset_samples"],
                    fractional_tracking_cfo_hz=row["fractional_tracking_cfo_hz"],
                    fractional_margin=row["fractional_margin"],
                )
                for c, row in zip(self.candidates[: self.count], packets, strict=True)
            ],
        )


class Detector:
    def __init__(self, binary, edge):
        from leo.analysis.starlink.templates import edge_frequencies_hz

        library = self.library = ct.CDLL(str(binary))
        library.portable_field_create.argtypes = [ct.c_uint]
        library.portable_field_create.restype = ct.c_void_p
        library.portable_field_free.argtypes = [ct.c_void_p]
        library.portable_field_free.restype = None
        library.portable_field_detect.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_double,
            ct.c_double,
            ct.POINTER(Group),
        ]
        library.portable_field_detect.restype = ct.c_int
        library.portable_field_workspace_bytes.restype = ct.c_size_t
        library.portable_field_group_bytes.restype = ct.c_size_t
        if library.portable_field_group_bytes() != ct.sizeof(Group):
            raise ValueError("portable detector output ABI changed")
        self.edge = edge
        offsets = edge_frequencies_hz(edge)
        self.minimum, self.maximum = float(offsets.min()), float(offsets.max())
        self.workspace_bytes = library.portable_field_workspace_bytes()
        self.groups = (Group * 3)()
        self.attempts = []
        self.context = library.portable_field_create(EDGES.index(edge))
        if not self.context:
            raise MemoryError("portable detector workspace allocation failed")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.library.portable_field_free(self.context)
        self.context = None

    def __call__(self, window, receiver_ids):
        from leo.contracts.fast_scan import FastScanReceiverV1

        samples = window.samples
        target = window.target
        if (
            target["edge"] != self.edge
            or receiver_ids != (0, 1)
            or window.sample_rate_hz != 10_000_000
            or samples.shape != (200_000, 2, 2)
            or samples.dtype.str != "<i2"
            or not samples.flags.c_contiguous
        ):
            raise ValueError("portable detector requires complete dual 10 MHz CI16")
        center = (
            target["rf_center_hz"] - target["lnb_lo_hz"] - window.acquisition["actual_if_center_hz"]
        )
        half_rate = window.sample_rate_hz / 2
        width = min(800_000.0, center + self.minimum + half_rate, half_rate - center - self.maximum)
        count = self.library.portable_field_detect(
            self.context, samples.ctypes.data, center, width, self.groups
        )
        if count not in (2, 3):
            raise ValueError("portable original-schedule acquisition failed")
        groups = self.groups[:count]
        final = {group.lane: i for i, group in enumerate(groups)}
        packets = [group.packets() for group in groups]
        self.attempts = [
            group.evidence(packets[i], i == final[group.lane]) for i, group in enumerate(groups)
        ]
        return tuple(
            FastScanReceiverV1(receiver_id=lane, candidates=packets[final[lane]])
            for lane in receiver_ids
        )
