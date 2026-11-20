/* Included in the release's detector TU. This partner port searches frequency
 * only at a primary-supplied integer epoch, then runs ordinary fractional GLRT. */
int leo_single_rx_glrt_analyze_partner_v1(leo_single_rx_glrt *single,
    const int16_t *ci16, size_t count, const int32_t *epochs, size_t epoch_count,
    leo_native_glrt_result *result)
{
    if (!single || single->magic != LEO_SINGLE_RX_GLRT_CONTEXT_MAGIC ||
        !single->native || single->native->magic != LEO_NATIVE_GLRT_CONTEXT_MAGIC ||
        !ci16 || !epochs || !result || count != 200000 || epoch_count < 1 ||
        epoch_count > 2 || fegetround() != FE_TONEAREST)
        return LEO_NATIVE_GLRT_INVALID;
    leo_native_glrt *context = single->native;
    if (context->receiver_count != 1 || context->rate != 10000000 ||
        context->refinement_mode != 3 || context->frame != 13333)
        return LEO_NATIVE_GLRT_INVALID;
    for (size_t i = 0; i < epoch_count; ++i)
        if (epochs[i] < 0 || epochs[i] >= (int32_t)context->frame)
            return LEO_NATIVE_GLRT_INVALID;
    int status = context_enter(context);
    if (status) return status;
    leo_presence_workspace *w = context->search;
    if (!w->wide_regional) regional_cfo_band(w, 1);
    w->acquisition_first_frame = 0;
    w->acquisition_regions[0] = w->acquisition_regions[1] = 0;
    double started = clock_ms(CLOCK_THREAD_CPUTIME_ID);
    for (size_t k = 0; k < count; ++k)
        w->samples[k] = (double)ci16[2*k] + I*(double)ci16[2*k+1];
    leo_full_search_result search = {0};
    leo_fine_precision_cache fine;
    if (leo_fine_precision_init(&fine, w->fine_fft.size, &context->fine_workspace)) {
        context_leave(context);
        return LEO_NATIVE_GLRT_KERNEL;
    }
    const int side = (int)floor(regional_cfo_limit(w) / w->fine_step_hz);
    const int bins = 2*side+1;
    /* The release uses 500 Hz or coarser fine cells at 10 MS/s. */
    double scores[3201];
    if (bins > (int)(sizeof(scores)/sizeof(scores[0]))) {
        status = LEO_NATIVE_GLRT_KERNEL;
        goto finish;
    }
    for (size_t i = 0; i < epoch_count; ++i) {
        int epoch = epochs[i];
        double stage = clock_ms(CLOCK_THREAD_CPUTIME_ID);
        if (leo_fine_precision_scores(w, count, epoch, -side*w->fine_step_hz,
            bins, scores, &fine)) {
            status = LEO_NATIVE_GLRT_KERNEL;
            goto finish;
        }
        int best = 0;
        for (int q = 1; q < bins; ++q)
            if (scores[q] > scores[best] ||
                (scores[q] == scores[best] && abs(q-side) < abs(best-side)))
                best = q;
        double cell = (best-side)*w->fine_step_hz;
        double cfo = cell;
        if (best > 0 && best+1 < bins) {
            double curve = scores[best-1] - 2*scores[best] + scores[best+1];
            if (isfinite(curve) && curve < -1e-15)
                cfo += w->fine_step_hz *
                    fmax(-1, fmin(1, .5*(scores[best-1]-scores[best+1])/curve));
        }
        search.fine_fft_cpu_ms += clock_ms(CLOCK_THREAD_CPUTIME_ID)-stage;

        double score[3];
        stage = clock_ms(CLOCK_THREAD_CPUTIME_ID);
        if (glrt(w, count, epoch, cfo, 0, LEO_PRESENCE_EPOCH_FRAMES, 0, score)) {
            status = LEO_NATIVE_GLRT_KERNEL;
            goto finish;
        }
        search.glrt_cpu_ms += clock_ms(CLOCK_THREAD_CPUTIME_ID)-stage;
        ++search.actual_executed_glrt_calls;
        leo_full_search_candidate *row = &search.candidates[search.candidate_count++];
        row->coarse_epoch = row->refined_epoch = row->candidate.epoch = epoch;
        row->coarse_bin = -1;
        row->frame_support = full_frame_support(w, count, epoch);
        row->refinement_skipped = row->glrt_complete = 1;
        row->fine_cfo_hz = cell;
        row->candidate.acquired_cfo_hz = cfo;
        row->candidate.tracking_cfo_hz = cfo + score[2];
        row->candidate.exact_score = score[0];
        row->candidate.control_score = score[1];
        row->candidate.margin = score[0]-score[1];
        stage = clock_ms(CLOCK_THREAD_CPUTIME_ID);
        if (full_fractional_epoch(w, count, row)) {
            status = LEO_NATIVE_GLRT_KERNEL;
            goto finish;
        }
        search.fractional_epoch_cpu_ms += clock_ms(CLOCK_THREAD_CPUTIME_ID)-stage;
    }
finish:
    search.fine_precision_calls = fine.calls;
    search.fine_precision_guard_checks = fine.guard_checks;
    search.fine_precision_fallbacks = fine.fallbacks;
    search.fine_precision_nonfinite_fallbacks = fine.nonfinite_fallbacks;
    search.fine_precision_near_tie_fallbacks = fine.near_tie_fallbacks;
    search.fine_precision_interpolation_fallbacks = fine.interpolation_fallbacks;
    leo_fine_precision_free(&fine);
    if (!status) {
        leo_native_glrt_result out = {.row_count = 1};
        leo_proposal_timing no_proposal = {0};
        search.total_cpu_ms = clock_ms(CLOCK_THREAD_CPUTIME_ID)-started;
        out.detector_cpu_ms = search.total_cpu_ms;
        copy_row(&out.rows[0], 0, 0, 0, &search, &no_proposal, 0, 0, 0);
        if (finite_result(&out)) *result = out;
        else status = LEO_NATIVE_GLRT_KERNEL;
    }
    context_leave(context);
    return status;
}
