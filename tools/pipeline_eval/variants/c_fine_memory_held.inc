/* Exact and symbol-rolled held pilots see the same measured samples and CFO. */
static void held_pilots(PortableVerifier *w, unsigned epoch, double cfo,
                        double *exact, double *control) {
    const int limit = 302*taps;
    double energy_exact = 0, energy_control = 0;
    PortableFineComplex *rolled = w->fine.scratch;
    memset(&w->reference, 0, sizeof(w->reference));
    memset(rolled, 0, limit*sizeof(*rolled));
    for (int k = 3*taps; k < limit; k += 2*taps) for (int j = k; j < k+taps; ++j) {
        const PortableFineComplex phase = rotate(-tau*cfo*j/rate);
        w->reference.fine[j] = multiply(conjugate(w->exact[j]), phase);
        rolled[j] = multiply(conjugate(w->control[j]), phase);
        energy_exact += energy(w->exact[j]);
        energy_control += energy(w->control[j]);
    }
    double received[max_frames], correlations[max_frames][2];
    int32_t starts[max_frames];
    int frames = 0;
    for (int f = 0; f < max_frames; ++f) {
        const int start = frame_start(epoch, f);
        if (start + limit > samples) break;
        double norm = 0;
        for (int k = 3*taps; k < limit; k += 2*taps) for (int j = k; j < k+taps; ++j)
            norm += compact_energy(w->iq.fine[start+j]);
        starts[frames] = start;
        received[frames++] = norm;
    }
    double *scores[] = {exact, control};
    const double *templates[] = {w->reference.data, (const double *)rolled};
    const double norms[] = {energy_exact, energy_control};
    for (int c = 0; c < 2; ++c) {
        conditioned_single(w->iq.data, templates[c], starts, frames, limit, &correlations[0][0]);
        double sum = 0;
        for (int f = 0; f < frames; ++f) {
            const double denom = sqrt(norms[c]*received[f]);
            if (denom > 0) sum += hypot(correlations[f][0], correlations[f][1]) / denom;
        }
        *scores[c] = frames ? sum/frames : 0;
    }
}
