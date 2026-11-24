/* Pack or refill only the literal input samples. Frame phase stays absolute. */
static int compact_ranges(unsigned epoch, double offset, int32_t lo[max_frames], int32_t count[max_frames]) {
    if (epoch >= n || !isfinite(offset) || fabs(offset) > 1.5)
        return -1;
    const int integer = fabs(offset - nearbyint(offset)) <= 1e-12;
    int total = 0;
    for (int f = 0; f < max_frames; ++f) {
        const int start = frame_start(epoch, f);
        const int floor_lo = (int)floor(start + first + offset) - (integer ? 0 : 7);
        const int floor_hi = (int)floor(start + stop - 1 + offset) + (integer ? 0 : 8);
        if (floor_lo < 0 || floor_hi >= samples)
            break;
        lo[f] = integer ? start + first + (int)nearbyint(offset) : floor_lo;
        count[f] = integer ? aperture : floor_hi - floor_lo + 1;
        if (lo[f] < 0 || lo[f] + count[f] > samples || count[f] <= 0)
            return -1;
        total += count[f];
    }
    return total ? total : -1;
}

int short_cfo_compact_count(unsigned epoch, double offset) {
    int32_t lo[max_frames] = {0}, count[max_frames] = {0};
    return compact_ranges(epoch, offset, lo, count);
}

int short_cfo_pack_support(const int16_t *iq, unsigned lane, unsigned epoch, double offset,
                           int16_t *packed, int cells) {
    int32_t lo[max_frames] = {0}, count[max_frames] = {0};
    if (!iq || !packed || lane > 1 || cells <= 0 || cells != compact_ranges(epoch, offset, lo, count))
        return -1;
    for (int f = 0; f < max_frames && count[f]; ++f) {
        const int16_t *source = iq + 4 * lo[f] + 2 * lane;
        for (int i = 0; i < count[f]; ++i) {
            packed[2*i] = source[4*i];
            packed[2*i + 1] = source[4*i + 1];
        }
        packed += 2 * count[f];
    }
    return 0;
}

static int refill_compact(PortableVerifier *w, const int16_t *packed, int cells,
                          unsigned epoch, double offset) {
    int32_t lo[max_frames] = {0}, count[max_frames] = {0};
    if (cells <= 0 || cells != compact_ranges(epoch, offset, lo, count))
        return -1;
    for (int f = 0; f < max_frames && count[f]; ++f) {
        for (int i = 0; i < count[f]; ++i)
            w->iq.fine[lo[f]+i] = (PortableFineSample){packed[2*i], packed[2*i+1]};
        packed += 2 * count[f];
    }
    return 0;
}
