static int confirm_peak(TimingFirst *w, const Peak *peak)
{
    if (gate(w, peak, 160, 0) || gate(w, peak, 232, 0)) return 1;
    return gate(w, peak, 0, 1) ? 2 : 0;
}

static Peak parity_peak(const double v[4])
{
    return (Peak){v[0], v[1], v[3], (int)v[2]};
}

static int refine_confirmed(TimingFirst *w, const RefineRequest *requests, int count,
                            double lo, double hi, TimingFirstResult *out)
{
    if (!count) return 0;
    const float *x = (const float *)w->data, *h = (const float *)(w->pilot + first);
    double values[max_peaks][4];
    if (delay_refine_bank(x, h, requests, 1, lo, hi, values)) return -1;
    Peak best = parity_peak(values[0]);
    int confirmation = confirm_peak(w, &best);
    if (confirmation) {
        for (int i = 1; i < count; ++i) {
            int status = delay_refine_parity(x, h, requests[i], lo, hi, best.score, values[i]);
            if (status < 0) return -1;
            if (status || !(values[i][3] > best.score)) continue;
            Peak peak = parity_peak(values[i]);
            int accepted = confirm_peak(w, &peak);
            if (accepted) {
                best = peak;
                confirmation = accepted;
            }
        }
        *out = (TimingFirstResult){best.epoch, best.hz, best.score, confirmation};
        return 0;
    }

    /* Without a confirmed incumbent, finish the original search on every
       remaining request. The first request's gate already failed. */
    if (delay_refine_bank(x, h, requests + 1, count - 1, lo, hi, values + 1)) return -1;
    for (int i = 1; i < count; ++i) {
        int pick = 1;
        for (int j = 2; j < count; ++j)
            if (values[j][3] > values[pick][3]) pick = j;
        Peak peak = parity_peak(values[pick]);
        values[pick][3] = -1.;
        int accepted = confirm_peak(w, &peak);
        if (accepted) {
            *out = (TimingFirstResult){peak.epoch, peak.hz, peak.score, accepted};
            break;
        }
    }
    return 0;
}
