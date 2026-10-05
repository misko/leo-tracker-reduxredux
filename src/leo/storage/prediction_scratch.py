"""Disposable mapped prediction arrays, written directly in bounded chunks."""

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


class PredictionScratch:
    def __init__(self, root: Path):
        directory = root / "prediction-scratch"
        directory.mkdir(parents=True, exist_ok=True)
        self._temporary = TemporaryDirectory(prefix="bank-", dir=directory)
        self._arrays: list[np.memmap] = []

    def __enter__(self):
        return self

    def allocate(self, shape: tuple[int, ...], dtype=np.float64) -> np.ndarray:
        if not all(shape):
            return np.empty(shape, dtype=dtype)
        path = Path(self._temporary.name) / f"array-{len(self._arrays)}.npy"
        array = np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=shape)
        self._arrays.append(array)
        return array

    def finalize(self, array: np.ndarray, used: int) -> np.ndarray:
        if not 0 <= used <= len(array):
            raise ValueError("used array prefix is outside allocated capacity")
        if not isinstance(array, np.memmap):
            return array[:used]
        index = next(i for i, item in enumerate(self._arrays) if item is array)
        array.flush()
        path = array.filename
        array._mmap.close()
        retained = np.load(path, mmap_mode="r", allow_pickle=False)
        self._arrays[index] = retained
        return retained[:used]

    def retain(self, values: np.ndarray) -> np.ndarray:
        allocated = self.allocate(values.shape, values.dtype)
        allocated[:] = values
        return self.finalize(allocated, len(values))

    def __exit__(self, exc_type, exc, traceback):
        for array in self._arrays:
            array._mmap.close()
        self._arrays.clear()
        self._temporary.cleanup()
