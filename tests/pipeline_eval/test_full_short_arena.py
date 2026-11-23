import numpy as np
import pytest

from reports.ALGO08.v3.full_short_arena import SynchronousArena


class FakeDecoder:
    def decode(self, payload, storage, size):
        assert size == len(payload)
        storage[:] = np.frombuffer(payload, np.uint8)
        return True


def test_two_consumed_members_reuse_the_same_read_only_destination():
    arena = SynchronousArena(FakeDecoder(), size=8, windows=2)
    addresses = []
    for payload in (bytes(range(8)), bytes(range(8, 16))):
        with arena.frame(payload) as stream:
            for offset in (0, 4):
                samples = np.frombuffer(stream.read(4), np.uint8)
                with arena.consume(samples):
                    assert samples.tobytes() == payload[offset:offset + 4]
                    assert not samples.flags.writeable
                if offset == 0:
                    addresses.append(samples.ctypes.data)
    assert addresses[0] == addresses[1]
    assert arena.counts == {"allocation": 1, "reuse": 1, "completed_frames": 2, "released_callbacks": 4}


def test_rejects_incomplete_frame_and_active_or_retained_view():
    arena = SynchronousArena(FakeDecoder(), size=8, windows=2)
    with pytest.raises(RuntimeError, match="previous IQ loan"):
        with arena.frame(b"12345678") as stream:
            with arena.consume(np.frombuffer(stream.read(4), np.uint8)):
                with arena.frame(b"87654321"):
                    pytest.fail("Active input was overwritten")
    with pytest.raises(RuntimeError, match="completely consumed"):
        with arena.frame(b"12345678"):
            pass
    escaped = []
    with pytest.raises(RuntimeError, match="retained"):
        with arena.frame(b"12345678") as stream:
            samples = np.frombuffer(stream.read(4), np.uint8)
            with arena.consume(samples):
                escaped.append(samples)
