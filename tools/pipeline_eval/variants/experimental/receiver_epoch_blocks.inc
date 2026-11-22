enum { epoch_block_size = 64, max_epoch_blocks = (period + epoch_block_size - 1) / epoch_block_size };

static int best_epoch(const double *score, int begin, int end)
{
    int best = begin;
    double value = score[begin];
    for (int i = begin + 1; i < end; ++i) {
        if (score[i] > value) {
            best = i;
            value = score[i];
        }
    }
    return best;
}

static void reference_epochs(double *score, int count, int radius, int wanted, int *epochs)
{
    for (int k = 0; k < wanted; ++k) {
        int best = best_epoch(score, 0, count);
        epochs[k] = best;
        for (int j = -radius; j <= radius; ++j)
            score[(best + j + count) % count] = -1.;
    }
}

static int find_block_best(const double *score, int count, int block)
{
    int first = block * epoch_block_size, past = first + epoch_block_size;
    return best_epoch(score, first, past < count ? past : count);
}

void experimental_epoch_peaks(double *score, int count, int radius, int wanted, int blocked, int *epochs)
{
    if (count <= 0 || wanted <= 0) return;
    if (!blocked || count > period) {
        reference_epochs(score, count, radius, wanted, epochs);
        return;
    }
    int maxima[max_epoch_blocks];
    int blocks = (count + epoch_block_size - 1) / epoch_block_size;
    for (int b = 0; b < blocks; ++b) {
        /* A NaN at a block's first element changes how its scalar scan
           sees later values. Use the release's global scan for this case. */
        if (isnan(score[b * epoch_block_size])) {
            reference_epochs(score, count, radius, wanted, epochs);
            return;
        }
        maxima[b] = find_block_best(score, count, b);
    }
    for (int k = 0; k < wanted; ++k) {
        int best = maxima[0];
        double value = score[best];
        for (int b = 1; b < blocks; ++b) {
            int i = maxima[b];
            if (score[i] > value) {
                best = i;
                value = score[i];
            }
        }
        epochs[k] = best;
        for (int j = -radius; j <= radius; ++j)
            score[(best + j + count) % count] = -1.;
        int previous = -1;
        for (int j = -radius; j <= radius; ++j) {
            int block = ((best + j + count) % count) / epoch_block_size;
            if (block != previous) {
                maxima[block] = find_block_best(score, count, block);
                previous = block;
            }
        }
    }
}
