static _Thread_local DirectedTrace directed_trace[2];
static _Thread_local int directed_stamp;

int directed_timing_trace(DirectedTrace *out) {
    int count = directed_stamp;
    if (count > 0 && count <= 2)
        memcpy(out, directed_trace, count * sizeof(*out));
    directed_stamp = 0;
    return count;
}

void directed_timing_input(TimingFirst *w, const int16_t *iq, int lane) {
    input(w, iq, lane, 0.);
}

int directed_timing_gate(TimingFirst *w, const int16_t *iq, int lane, int sample, double hz) {
    Peak p = {.hz = hz, .sample = sample};
    if (iq) {
        if (gate_ci16(w, &p, 160, 0, iq, lane) || gate_ci16(w, &p, 232, 0, iq, lane))
            return 1;
        return gate_ci16(w, &p, 0, 1, iq, lane) ? 2 : 0;
    }
    if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0))
        return 1;
    return gate(w, &p, 0, 1) ? 2 : 0;
}

int directed_timing_bank(TimingFirst *w, const DirectedSeed *seeds, int count,
                         double low, double high, double (*out)[4]) {
    RefineRequest requests[directed_cap];
    for (int i = 0; i < count; ++i)
        requests[i] = (RefineRequest){seeds[i].epoch, seeds[i].hz};
    return delay_refine_bank((float *)w->data, (float *)(w->pilot + first), requests, count, low, high, out);
}

int directed_timing_cancel(TimingFirst *w, const float *pilot, float *scratch,
                           double epoch, double hz) {
    return pilot_cancel_resident((float *)w->data, pilot, scratch, epoch, hz);
}
