"""Opt-in decoder ports for the unchanged verified-once owned-window reader."""

import ctypes as ct
from dataclasses import dataclass

import numpy as np

from .zstd_literal_pair import OwnedWork, Work


@dataclass
class Context:
    snapshot: tuple
    handle: int
    native: bool
    emitted: int = 0
    replayed: int = 0
    replay_owner: object = None
    fallback: str | None = None


class OwnedPorts:
    """Borrow the FusedMember's original authenticated, pinned private snapshot."""

    def __init__(self, paired, ordinary):
        self.paired = paired
        self.ordinary = ordinary
        self.finished = None

    def fused_history_open_unindexed(self, source, size, total, owned):
        self.finished = None
        snapshot = source, size, total, owned
        handle = self.paired.owned_open(*snapshot)
        if handle:
            return Context(snapshot, handle, True)
        handle = self.ordinary.fused_history_open_unindexed(*snapshot)
        return Context(snapshot, handle, False, fallback="unsupported original layout") if handle else None

    def fused_history_close(self, ctx):
        (self.paired.owned_close if ctx.native else self.ordinary.fused_history_close)(ctx.handle)

    def fused_history_owned_capacity(self, ctx):
        if ctx.native:
            return ctx.snapshot[-1] + 2 * 131072
        return self.ordinary.fused_history_owned_capacity(ctx.handle)

    def fused_history_scratch(self, ctx):
        return (self.paired.owned_scratch if ctx.native else self.ordinary.fused_history_scratch)(ctx.handle)

    def fused_history_read(self, ctx, out, size):
        result = self.ordinary.fused_history_read(ctx.handle, out, size)
        ctx.emitted += bool(result)
        return result

    def _ordinary_restart(self, ctx, reason):
        handle = self.ordinary.fused_history_open_unindexed(*ctx.snapshot)
        if not handle:
            return False
        self.paired.owned_close(ctx.handle)
        ctx.native, ctx.handle, ctx.fallback = False, handle, reason
        capacity = self.ordinary.fused_history_owned_capacity(handle)
        if not capacity:
            raise RuntimeError("An admitted paired layout no longer admits the ordinary owned path")
        spare = np.empty(capacity, dtype=np.uint8)
        for _ in range(ctx.emitted):
            if not self.ordinary.fused_history_read_owned(handle, spare.ctypes.data, capacity):
                return False
            # The ordinary decoder's pending bytes and external history still
            # refer to the latest replay buffer until the next successful call.
            ctx.replay_owner, spare = spare, (ctx.replay_owner if ctx.replay_owner is not None else
                                               np.empty(capacity, dtype=np.uint8))
            ctx.replayed += 1
        return True

    def fused_history_read_owned(self, ctx, out, size):
        if ctx.native:
            result = self.paired.owned_read(ctx.handle, out, size)
            if result:
                ctx.emitted += 1
                return result
            if not self._ordinary_restart(ctx, "paired native read rejected; replayed already delivered ordinals"):
                return 0
        result = self.ordinary.fused_history_read_owned(ctx.handle, out, size)
        ctx.replay_owner = None
        ctx.emitted += bool(result)
        return result

    def fused_history_finish(self, ctx):
        if ctx.native:
            work, owned = Work(), OwnedWork()
            if self.paired.owned_finish(ctx.handle, ct.byref(work), ct.byref(owned)):
                self.finished = {name: getattr(span, name) for span in (work, owned) for name, _ in span._fields_}
                self.finished.update(route="paired", emitted=ctx.emitted, replayed=0)
                return 1
            if not self._ordinary_restart(ctx, "paired native EOF rejected; replayed already delivered ordinals"):
                return 0
        result = self.ordinary.fused_history_finish(ctx.handle)
        if result:
            self.finished = dict(route="ordinary_fallback", emitted=ctx.emitted,
                                 replayed=ctx.replayed, reason=ctx.fallback)
        return result
