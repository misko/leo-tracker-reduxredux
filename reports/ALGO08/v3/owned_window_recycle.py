"""Bounded reusable destinations for exact owned Zstandard window delivery."""

import ctypes as ct
from weakref import ref

import numpy as np

MAX_SLOTS = 2
MAX_CAPACITY = 2 * 1024**2


class WindowArena:
    """Lease a slot until the last buffer export and native history are gone."""

    def __init__(self):
        self.slots = []
        self.capacity = 0
        self.allocations = self.reuses = self.fallbacks = 0

    def borrow(self, capacity):
        if not 0 < capacity <= MAX_CAPACITY or self.capacity not in (0, capacity):
            self.fallbacks += 1
            return None
        for index, (backing, lease) in enumerate(self.slots):
            if lease() is None:
                self.reuses += 1
                break
        else:
            if len(self.slots) == MAX_SLOTS:
                self.fallbacks += 1
                return None
            index = len(self.slots)
            backing = np.empty(capacity, dtype=np.uint8)
            self.capacity = capacity
            self.allocations += 1
        # NumPy views can bypass intermediate ndarrays in their base chain.
        # They must retain the export token, rather than a weakref to a view.
        export = (ct.c_ubyte * capacity).from_buffer(backing)
        readonly = np.frombuffer(memoryview(export).toreadonly(), dtype=np.uint8)
        if index == len(self.slots):
            self.slots.append((backing, ref(export)))
        else:
            self.slots[index] = (backing, ref(export))
        return readonly

    def receipt(self):
        return dict(allocations=self.allocations, reuses=self.reuses, fallbacks=self.fallbacks,
                    retained_bytes=len(self.slots) * self.capacity)
