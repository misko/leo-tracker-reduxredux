"""Research-only blocked correlation oracle; no production dispatch changes."""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def folded_gemm(values, template, sample_rate_hz, absolute_cfo_hz, symbols, epoch_count,
                *, correlation='gemm'):
    from leo.analysis.starlink.acquisition import (
        FRAME_RATE_HZ,
        OFDM_SYMBOL_DURATION_S,
        _power_prefix,
    )

    values = np.asarray(values, dtype=np.complex128)
    prefix = _power_prefix(values)
    accumulated = np.zeros((len(absolute_cfo_hz), epoch_count))
    support = np.zeros(epoch_count, dtype=np.int32)
    period = sample_rate_hz/FRAME_RATE_HZ
    offsets = [round(frame*period) for frame in range(int(values.size/period)+2)
               if round(frame*period) < values.size]
    input_fft = {}
    for symbol in symbols:
        start = round(symbol*sample_rate_hz*OFDM_SYMBOL_DURATION_S)
        stop = round((symbol+1)*sample_rate_hz*OFDM_SYMBOL_DURATION_S)
        reference = np.asarray(template[start:stop], dtype=np.complex128)
        count = len(reference)
        angles = (2*np.pi*np.arange(count)[:, None]*np.asarray(absolute_cfo_hz)[None, :]
                  /sample_rate_hz)
        bank = np.ascontiguousarray(np.conj(reference[:, None]*(np.cos(angles)+1j*np.sin(angles))))
        windows = sliding_window_view(values, count)
        # One matrix multiplication handles every CFO for a bounded sample block.
        if correlation == 'gemm':
            correlations = np.empty((len(windows), len(absolute_cfo_hz)), dtype=np.complex128)
            for position in range(0, len(windows), 4096):
                chunk = np.ascontiguousarray(windows[position:position+4096])
                correlations[position:position+len(chunk)] = chunk @ bank
        elif correlation == 'overlap_fft':
            nfft = max(256, 2**int(np.ceil(np.log2(2*count))))
            step = nfft-count+1
            blocks = (len(values)+step-1)//step
            if count not in input_fft:
                padded = np.pad(values, (count-1, blocks*step-len(values)))
                chunks = sliding_window_view(padded, nfft)[::step]
                input_fft[count] = np.fft.fft(chunks, axis=-1)
            kernels = np.fft.fft(bank.T[:, ::-1], n=nfft, axis=-1)
            correlations = np.empty((len(windows), len(absolute_cfo_hz)), dtype=np.complex128)
            for first in range(0, len(kernels), 4):
                values_fft = input_fft[count][None, :, :]*kernels[first:first+4, None, :]
                inverse = np.fft.ifft(values_fft, axis=-1)[:, :, count-1:]
                full = inverse.reshape(len(inverse), -1)
                correlations[:, first:first+len(inverse)] = full[:, count-1:len(values)].T
        else:
            raise ValueError('Unknown experimental correlation method')
        received_energy = np.maximum(prefix[count:]-prefix[:-count], 0)
        denominator = np.sqrt(float(np.sum(reference.real**2+reference.imag**2))*received_energy)
        normalized = np.divide(np.abs(correlations), denominator[:, None],
                               out=np.zeros(correlations.shape, dtype=float),
                               where=denominator[:, None] > 0)
        for offset in offsets:
            base = start+offset
            length = min(epoch_count, len(windows)-base)
            if length <= 0:
                break
            accumulated[:, :length] += normalized[base:base+length].T
            support[:length] += 1
    return tuple(np.divide(accumulated, support[None, :], out=accumulated,
                           where=support[None, :] > 0))
