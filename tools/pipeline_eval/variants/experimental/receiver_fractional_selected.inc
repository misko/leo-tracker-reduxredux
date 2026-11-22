int experimental_exact_fractional_score(PortableVerifier *, unsigned, double, double,
                                        double *, double *);

/* Repair a row exported by the immediately preceding factor call. Both FFT
 * scores use the scout's frequency, before fractional residual is added. */
int experimental_repair_fractional_selection(TwoCarrierReceiver *r, ScanFactor *factor)
{
    if (!r || !factor || factor->rank < 0 || factor->rank > 1) return -1;
    unsigned rank = (unsigned)factor->rank;
    unsigned bit = 1u << rank;
    if (!(r->valid_score & bit)) return -1;
    ScanFactor saved = r->measured[rank];
    if (factor->integer != saved.integer || factor->offset != saved.offset ||
        factor->hz != saved.hz || factor->exact != saved.exact || factor->control != saved.control)
        return -1;
    if (!(r->approximate_score & bit)) return 0;
    if (experimental_exact_fractional_score(r->verify, (unsigned)saved.integer, r->seed_hz[rank],
                                             saved.offset, &factor->exact, &factor->control))
        return -1;
    return 1;
}
