"""Published Starlink SSS edge symbols, locally ported for this replay."""

from __future__ import annotations

import numpy as np

SSS_HEX = (
    "BD565D5064E9B3A94958F28624DED560946199F5B40F0E4FB5EFCB473B4C24"
    "B2D1E0BD01A6A04D5017DE91A8ECC0DA09EBFE57F9F1B44C532F161C583A4249"
    "0A5C09F2A117F9A28F9B2FD547A74C44BABB4BE85DA6A62B1235E2AD084C0018"
    "0142A8F7F357DEC4F31316BC58FA404909A3FCA7F88E421902B6A2580AE80308"
    "03F65809DB347F590DBC46F010EBE3A25C060D74429FC46BDF9B63719279798D"
    "232C5ABA274122FF66AD7E449F44CB40C49C24A1E2629F5BFE82CE531FDC34F8"
    "C64A43A963F40D5B71BDE6FB2F13492D6F2E8544B21D449722C635180342CD00"
    "26A1E7F7E80E91B175E852F919767E5AF9B6E909AF362F5218E2B908DC005803"
)


def sss_phase_states(indexes: tuple[int, ...] | None = None) -> np.ndarray:
    selected = tuple(range(2, 1022)) if indexes is None else tuple(indexes)
    if not selected or any(index < 2 or index > 1021 for index in selected):
        raise ValueError("SSS subcarrier indexes must lie in 2..1021")
    encoded = int(SSS_HEX, 16)
    return np.asarray([(encoded >> (2 * (index - 2))) & 3 for index in selected], dtype=np.int8)


def sss_edge_symbols(edge: str = "lower") -> np.ndarray:
    indexes = {"upper": tuple(range(488, 496)), "lower": tuple(range(528, 536))}
    if edge not in indexes:
        raise ValueError("edge must be lower or upper")
    return np.asarray(np.exp(1j * np.pi / 2 * sss_phase_states(indexes[edge])), np.complex64)
