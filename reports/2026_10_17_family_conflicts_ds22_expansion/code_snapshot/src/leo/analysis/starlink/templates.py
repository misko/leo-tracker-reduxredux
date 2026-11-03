# ruff: noqa: E501
"""Published Qin edge-pilot states and sampled waveforms.

The Appendix-A constants and numerical construction were independently ported
from ``leo-tracker`` commit 0bb80d14759fd8496b74e7d3219a690be18565a6.
That repository is a development oracle only and is never imported at runtime.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import numpy as np

from leo.contracts.states import StarlinkEdge

FRAME_RATE_HZ = 750.0
OFDM_SYMBOL_DURATION_S = 4.4e-6
CYCLIC_PREFIX_DURATION_S = 2 / 15 * 1e-6
SUBCARRIER_SPACING_HZ = 234_375.0
CONTROL_SYMBOL_ROLL = 17
QIN_ARXIV_ID = "2602.02627v1"


# Factual 600-bit pilot integers from Qin et al. Appendix A. Each hexadecimal
# value encodes 300 base-4 states for one published pilot subcarrier.
QIN_EDGE_PILOT_HEX_V1 = {
    488: "7634046DA45F89042D0117E163167D4AE832D857515F3CAD90337697FB8F1CD048EFEF559ECD79688BCBBF44D2FA9BDFAE639DB5D7B1DD2DDCE4EC9733C0D4DCCF3172A0EC34CC226C530E",
    489: "CD9AFAA654147A5FE2B407B51FFE15215B3A71624139619628A9C33E8E3A32E5146C09BD3EE9026CA52032D7FD38960FFC52599E9B8A7F6942334BD4C6D99D4331DEF5674570B245FBB25F",
    490: "02481A2B278B88F096C8D174D369D0CF6781B70EBD402D6A6F4C985DA6265866A8374DC0B3E4917146FE3274CA5D61C3F9A31CB8125F291155CBD4F4F84E93C0D854BBC54EE14443EC2DF8",
    491: "D8DC99C2654265B8C32450114C37E2B725A822F1054B46F272877122E47109F113D59E37DFF418FEA3627C7A5CC0A93ABA0F9408E958DF4179C4DE40CEF842D333632B3E77BEB34B2E6045",
    492: "3CC5CA83B0D33089B14C3B6AC3D1946359726B4966B2E966BE61124A5D53E22A73EDBEB383A92F06CA6CAA8A5B1ECE695465145E286EEE1804CD79A00C84FC80C87DE9DF572F9B54AE798B",
    493: "C77BD59D15C2C917EEC97FB479B9F0B2BF5D2ECCD80248D2AC68C84CEA11BAD18D9F6F31B6AFD783347943562E2C6832EA76828FCDAB31EFF6A9A88EA48E3AFA625B2FCDA7B99B0295E926",
    494: "6152EF153B85110FB0B7E24D8334B1C4196DE872B598767BC3CB4A4827A09D924AA7F57EB946F1981D036E3001934B10C9E22ABB6AF1F047B3A874CA95E68CBA67063F605FD05D532AAD3C",
    495: "CD8CACF9DEFACD2CB9811439D8B7E16F9E09BED47370207150A86DFE24EA1298CCB0907F5BAB67D4660462C6B10F74B8D9FA7B6F9EC1399B30B43AF622A894B2220B6B509A84AABB58D023",
    528: "CCBF3A16929836160CEC6EB7417AE6C37DC1E828CEFB60CE0E6C3B546A76B0AE1E7BC0E9577528B0F78F82A4104EA2C316B945D385200C7E5A1C5B48F5F9F9AF5C4BA920ACA3A599DB9974",
    529: "9CF72F5F5B95CE7342C925CF1AAF457F182C32810E2F7486705D5FA2D9C8923B0173FB206B46045C6F162BB9FFD051DB5E5900EFD2DE24D4BB3FE87DD776F00B5613A7D22B2821E139A599",
    530: "296319D723210189953BB730DC6046E4EC5FB48F9718D5B600A01578CAC3159B58EE8A306663921FBE78EE7C1E8E049B4230A14EB4954933AB64F67B396DD6DB12BCBB3CCA60EA79E0614B",
    531: "1017FBBD3D03981EE9F4424D473B8A73E136C777956EAEBD4CA51E9B70D9F5D10657F268595A5C3687D2DD06C98630F817CABEF3EE660822350A70F10A29A8740212A9CF7E7D814D60A69C",
    532: "712EA482B28E96676E65D09994965587314F2B562D0E750FE566E89205A8D4DFED2C4FAFFC5ED1EA6FB63EC13513444006B78ADFB4BDB6CB05470601C9F8F4901423069C9FBD68D292C16F",
    533: "584E9F48ACA08784E696644C78ED9684FC484F32AA1B4DA8E95457358DF89FE8B9D84D47F30D3CA2F2DDF0E76E57F14A44675326EDCF15052CB62B7DF0EBE623057605CF2406E25BD56B3B",
    534: "4AF2ECF32983A9E781852F6E90DC6CCE901863F527E038DA22C0CE02E44FA0563718D93E7454293962B43594CC2EE427FAE6F15C1238D9C85ABC4E303F3AEC3404A52310CAC0378665E19A",
    535: "084AA73DF9F60535829A716EC94D95AA6901B41E81AEF28B03F08CDE7D45425B1164009D56459C4286E269F4B8EBDBA8BF6FC79847B08A69F79AF6E6A7AF05DA504455BA72727DD7BE7744",
}


def qin_edge_pilot_indices(edge: StarlinkEdge | str) -> tuple[int, ...]:
    selected = StarlinkEdge(edge)
    return tuple(range(528, 536)) if selected is StarlinkEdge.LOWER else tuple(range(488, 496))


def qin_edge_pilot_states(edge: StarlinkEdge | str, *, symbol_roll: int = 0) -> np.ndarray:
    """Return the exact 300 by 8 published base-4 state matrix."""

    if isinstance(symbol_roll, bool) or not isinstance(symbol_roll, int):
        raise TypeError("symbol_roll must be an integer")
    indexes = qin_edge_pilot_indices(edge)
    output = np.empty((300, 8), dtype=np.int8)
    for output_row in range(300):
        source_row = (output_row - symbol_roll) % 300
        shift = 2 * (299 - source_row)
        for column, index in enumerate(indexes):
            output[output_row, column] = (int(QIN_EDGE_PILOT_HEX_V1[index], 16) >> shift) & 3
    output.flags.writeable = False
    return output


def qin_edge_pilot_symbols(edge: StarlinkEdge | str, *, symbol_roll: int = 0) -> np.ndarray:
    states = qin_edge_pilot_states(edge, symbol_roll=symbol_roll)
    output = np.asarray(np.exp(0.5j * np.pi * (states.astype(float) + 0.5)), np.complex64)
    output.flags.writeable = False
    return output


@lru_cache(maxsize=32)
def _cached_frame(sample_rate_hz: float, edge: StarlinkEdge, symbol_roll: int) -> np.ndarray:
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    count = round(sample_rate_hz / FRAME_RATE_HZ)
    if count <= 0 or count > 1_000_000:
        raise ValueError("sample rate produces an unsupported template length")
    time_s = np.arange(count, dtype=float) / sample_rate_hz
    symbol_index = np.floor(time_s / OFDM_SYMBOL_DURATION_S).astype(int)
    output = np.zeros(count, dtype=np.complex64)
    symbols = qin_edge_pilot_symbols(edge, symbol_roll=symbol_roll)
    indexes = qin_edge_pilot_indices(edge)
    absolute = np.asarray([_subcarrier_offset_hz(index) for index in indexes])
    tuning_offset_hz = float(np.mean(absolute))
    for index in range(2, 302):
        selected = np.flatnonzero(symbol_index == index)
        if not selected.size:
            continue
        local_time = time_s[selected] - index * OFDM_SYMBOL_DURATION_S
        values = np.zeros(selected.size, dtype=np.complex128)
        for column, subcarrier in enumerate(indexes):
            frequency_hz = _subcarrier_offset_hz(subcarrier) - tuning_offset_hz
            values += symbols[index - 2, column] * np.exp(
                2j * np.pi * frequency_hz * (local_time - CYCLIC_PREFIX_DURATION_S)
            )
        output[selected] = values / math.sqrt(8)
    output.flags.writeable = False
    return output


def qin_edge_pilot_frame(
    sample_rate_hz: float,
    edge: StarlinkEdge | str,
    *,
    symbol_roll: int = 0,
) -> np.ndarray:
    """Synthesize one complex64 pilot-only frame at pilot-band center."""

    return _cached_frame(float(sample_rate_hz), StarlinkEdge(edge), symbol_roll).copy()


def template_sha256(samples: np.ndarray) -> str:
    """Digest the canonical little-endian interleaved complex64 payload."""

    values = np.asarray(samples, dtype="<c8")
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def edge_frequencies_hz(edge: StarlinkEdge | str) -> np.ndarray:
    absolute = np.asarray(
        [_subcarrier_offset_hz(index) for index in qin_edge_pilot_indices(edge)],
        dtype=float,
    )
    return absolute - np.mean(absolute)


def _subcarrier_offset_hz(index: int) -> float:
    signed = index if index < 512 else index - 1024
    return signed * SUBCARRIER_SPACING_HZ
