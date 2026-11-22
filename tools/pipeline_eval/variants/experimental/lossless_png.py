"""Use libdeflate on the guarded renderer's contiguous Agg RGBA buffers."""

from ctypes import CDLL, c_int, c_size_t, c_void_p
from functools import cache
from io import BytesIO
from struct import pack, unpack_from
from time import process_time
from unittest.mock import patch
from zlib import crc32

import matplotlib.image as mpl_image
import numpy as np

from tools.pipeline_eval.variants.experimental import shared_orbit_figures
from tools.pipeline_eval.variants.experimental.raster_layout import render_layout

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_RGBA_IHDR = b"\x08\x06\x00\x00\x00"
_MAX_FILTERED_BYTES = 128 * 1024 * 1024


@cache
def _libraries(filter_library, deflate_library):
    if filter_library is None:
        return None
    try:
        filters = CDLL(str(filter_library))
        filters.leo_png_filter_rgba.argtypes = [
            c_void_p,
            c_size_t,
            c_size_t,
            c_void_p,
            c_void_p,
            c_int,
        ]
        filters.leo_png_filter_rgba.restype = None
        deflate = CDLL(str(deflate_library))
        deflate.libdeflate_alloc_compressor.argtypes = [c_int]
        deflate.libdeflate_alloc_compressor.restype = c_void_p
        deflate.libdeflate_zlib_compress_bound.argtypes = [c_void_p, c_size_t]
        deflate.libdeflate_zlib_compress_bound.restype = c_size_t
        deflate.libdeflate_zlib_compress.argtypes = [
            c_void_p,
            c_void_p,
            c_size_t,
            c_void_p,
            c_size_t,
        ]
        deflate.libdeflate_zlib_compress.restype = c_size_t
        deflate.libdeflate_free_compressor.argtypes = [c_void_p]
        deflate.libdeflate_free_compressor.restype = None
    except (OSError, AttributeError):
        return None
    return filters, deflate


def _template_chunks(imsave, options):
    # Delegate metadata policy, text encoding and DPI rounding to the same
    # Matplotlib/Pillow writer, using one dummy RGBA pixel to obtain its chunks.
    template = BytesIO()
    pixel = memoryview(np.zeros((1, 1, 4), dtype=np.uint8))
    imsave(template, pixel, **options)
    payload = template.getvalue()
    if not payload.startswith(_SIGNATURE):
        return None
    chunks = []
    position = len(_SIGNATURE)
    while position < len(payload):
        size, tag = unpack_from(">I4s", payload, position)
        end = position + size + 12
        chunks.append((tag, payload[position:end]))
        position = end
    if (
        chunks[0][0] != b"IHDR"
        or chunks[0][1][16:21] != _RGBA_IHDR
        or chunks[-1][0] != b"IEND"
        or sum(tag == b"IDAT" for tag, _ in chunks) != 1
    ):
        return None
    return chunks


def _write_chunk(stream, tag, payload):
    stream.write(pack(">I4s", len(payload), tag))
    stream.write(payload)
    stream.write(pack(">I", crc32(payload, crc32(tag))))


class LosslessPng:
    def __init__(
        self, filter_library, *, deflate_library="libdeflate.so.0", level=3, simd=True, profile=None
    ):
        if not 1 <= level <= 12:
            raise ValueError("libdeflate level must be between 1 and 12")
        self.libraries = _libraries(filter_library, deflate_library)
        self.level = level
        self.simd = simd
        self.profile = profile

    def _encode(self, imsave, stream, pixels, options):
        if (
            self.libraries is None
            or type(stream) is not BytesIO
            or options.keys() - {"format", "origin", "dpi", "metadata", "pil_kwargs"}
            or options.get("format") != "png"
            or options.get("origin") != "upper"
            or options.get("pil_kwargs")
            or not isinstance(pixels, memoryview)
            or pixels.format != "B"
            or pixels.ndim != 3
            or pixels.shape[2] != 4
            or not pixels.c_contiguous
        ):
            return False
        height, width, _ = pixels.shape
        row_bytes = 4 * width
        filtered_bytes = (row_bytes + 1) * height
        if min(width, height) <= 0 or filtered_bytes > _MAX_FILTERED_BYTES:
            return False

        encode_start = process_time()
        chunks = _template_chunks(imsave, options)
        if chunks is None:
            return False
        template_s = process_time() - encode_start

        start = process_time()
        filters, deflate = self.libraries
        source = np.asarray(pixels)
        filtered = np.empty(filtered_bytes, dtype=np.uint8)
        row_scratch = np.empty(row_bytes, dtype=np.uint8)
        filters.leo_png_filter_rgba(
            source.ctypes.data,
            row_bytes,
            height,
            filtered.ctypes.data,
            row_scratch.ctypes.data,
            self.simd,
        )
        filter_s = process_time() - start

        start = process_time()
        compressor = deflate.libdeflate_alloc_compressor(self.level)
        if not compressor:
            return False
        try:
            bound = deflate.libdeflate_zlib_compress_bound(compressor, filtered_bytes)
            compressed = np.empty(bound, dtype=np.uint8)
            size = deflate.libdeflate_zlib_compress(
                compressor, filtered.ctypes.data, filtered_bytes, compressed.ctypes.data, bound
            )
        finally:
            deflate.libdeflate_free_compressor(compressor)
        compression_s = process_time() - start
        if not size:
            return False

        start = process_time()
        stream.write(_SIGNATURE)
        for tag, original in chunks:
            if tag == b"IHDR":
                _write_chunk(stream, tag, pack(">II", width, height) + _RGBA_IHDR)
            elif tag == b"IDAT":
                _write_chunk(stream, tag, memoryview(compressed)[:size])
            else:
                stream.write(original)
        if self.profile is not None:
            end = process_time()
            self.profile.append(
                dict(
                    width=width,
                    height=height,
                    scanline_bytes=filtered_bytes,
                    compressed_bytes=size,
                    header_cpu_s=template_s,
                    filter_cpu_s=filter_s,
                    compress_cpu_s=compression_s,
                    write_cpu_s=end - start,
                    encode_cpu_s=end - encode_start,
                )
            )
        return True

    def wrap(self, imsave):
        def save(*args, **options):
            if len(args) == 2 and self._encode(imsave, *args, options):
                return None
            return imsave(*args, **options)

        return save


def render_lossless_png(packet, *, encoder, require_trial=False, **kwargs):
    """Change only the encoder of the serial raster-layout experiment."""
    if encoder.libraries is None:
        return render_layout(packet, require_trial=require_trial, **kwargs)
    with (
        patch.object(mpl_image, "imsave", encoder.wrap(mpl_image.imsave)),
        patch.object(shared_orbit_figures, "imsave", encoder.wrap(shared_orbit_figures.imsave)),
    ):
        return render_layout(packet, require_trial=require_trial, **kwargs)
