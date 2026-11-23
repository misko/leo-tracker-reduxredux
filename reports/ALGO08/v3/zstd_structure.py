"""Inspect ordinary Zstandard frame metadata without decoding signal samples."""

from collections import Counter


MAGIC = b"\x28\xb5\x2f\xfd"
MAX_BLOCK = 128 * 1024
LITERALS = ("raw", "rle", "huffman_new", "huffman_reused")


def word(data, offset, width):
    if offset + width > len(data):
        raise ValueError("Truncated Zstandard header")
    return int.from_bytes(data[offset:offset + width], "little")


def literal_section(data):
    first = word(data, 0, 1)
    mode, form = first & 3, (first >> 2) & 3
    if mode < 2:
        width, shift = ((1, 3), (2, 4), (1, 3), (3, 4))[form]
        decoded = word(data, 0, width) >> shift
        return LITERALS[mode], width, decoded if mode == 0 else 1, decoded, 0
    width, bits = ((3, 10), (3, 10), (4, 14), (5, 18))[form]
    packed = word(data, 0, width) >> 4
    return LITERALS[mode], width, packed >> bits, packed & ((1 << bits) - 1), 1 if form == 0 else 4


def sequence_count(data):
    first = word(data, 0, 1)
    if first == 0 and len(data) != 1:
        raise ValueError("Unexpected bytes after zero sequence count")
    if first < 128:
        return first
    if first < 255:
        return ((first - 128) << 8) + word(data, 1, 1)
    return 0x7f00 + word(data, 1, 2)


def inspect(frame, decoded_bytes, *, block_spans=None):
    data = memoryview(frame)
    if data[:4] != MAGIC:
        raise ValueError("Expected one ordinary Zstandard frame")
    descriptor = word(data, 4, 1)
    if descriptor & 8:
        raise ValueError("Reserved frame flag")
    single = bool(descriptor & 32)
    width = (int(single), 2, 4, 8)[descriptor >> 6]
    position = 5 + int(not single)
    dict_width = (0, 1, 2, 4)[descriptor & 3]
    if word(data, position, dict_width):
        raise ValueError("Dictionary frames are outside this diagnostic")
    position += dict_width
    content_size = word(data, position, width) + (256 if width == 2 else 0) if width else None
    position += width
    if content_size is not None and content_size != decoded_bytes:
        raise ValueError("Frame content size differs from committed decoded length")
    block_counts, literal_counts, literal_sizes, literal_bytes, streams = (Counter() for _ in range(5))
    raw = repeated = seq_bytes = seqs = zeros = literal_header = 0
    has_tree = False
    while True:
        head = word(data, position, 3)
        position += 3
        last, mode, size = head & 1, (head >> 1) & 3, head >> 3
        if mode == 3 or size > MAX_BLOCK:
            raise ValueError("Reserved or oversized block")
        payload = size if mode != 1 else 1
        if position + payload > len(data):
            raise ValueError("Truncated Zstandard block")
        block_counts[("raw", "rle", "compressed")[mode]] += 1
        if mode == 0:
            raw += size
        elif mode == 1:
            repeated += size
        else:
            block = data[position:position + payload]
            lit, header, packed, plain, lanes = literal_section(block)
            if lit == "huffman_reused" and not has_tree:
                raise ValueError("Missing earlier Huffman tree")
            has_tree |= lit == "huffman_new"
            if header + packed >= len(block) or plain > MAX_BLOCK:
                raise ValueError("Malformed literals section extent")
            sequences = sequence_count(block[header + packed:])
            if plain + 3*sequences > MAX_BLOCK:
                raise ValueError("The reported sequences cannot fit in this block")
            literal_counts[lit] += 1
            literal_sizes[lit] += plain
            literal_bytes[lit] += packed
            if lanes:
                streams[str(lanes)] += 1
            seqs += sequences
            zeros += sequences == 0
            seq_bytes += payload-header-packed
            literal_header += header
            if block_spans is not None:
                block_spans.append((position, payload, plain, sequences))
        position += payload
        if last:
            break
    checksum = bool(descriptor & 4)
    if position + 4*checksum != len(data):
        raise ValueError("Incomplete frame or trailing bytes")
    match_bytes = decoded_bytes - raw - repeated - sum(literal_sizes.values())
    if match_bytes < 3*seqs or (not seqs and match_bytes):
        raise ValueError("The trusted decoded size cannot match the reported sequences")
    return dict(block_counts=dict(block_counts), literal_counts=dict(literal_counts),
                regenerated_literals=dict(literal_sizes), encoded_literals=dict(literal_bytes),
                huffman_streams=dict(streams), sequences=seqs, zero_sequence_blocks=zeros,
                sequence_section_bytes=seq_bytes, literal_header_bytes=literal_header, match_bytes=match_bytes,
                raw_block_bytes=raw, rle_block_decoded_bytes=repeated, checksum=checksum,
                frame_content_size=content_size, compressed_bytes=len(data), decoded_bytes=decoded_bytes)
