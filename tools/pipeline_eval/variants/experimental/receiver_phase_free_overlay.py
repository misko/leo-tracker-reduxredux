"""Use frame-relative phase in the final fractional evidence, with a stock fallback."""

from textwrap import indent

from .receiver_build import replace


def verifier_overlay(source):
    source = replace(source, '    double integer_hz;',
                     '    double integer_hz, phase_margin_radius;')
    source = replace(
        source,
        '''static double glrt_spectrum(PortableVerifier *w, const GlrtComplex *values, int frames,
                            int *winner, unsigned *flags) {''',
        '''static double glrt_spectrum_details(PortableVerifier *w, const GlrtComplex *values,
                                    int frames, int *winner, unsigned *flags,
                                    double *norm, double *gap) {''',
    )
    source = replace(source, '    if (ceiling == 0) return 0;',
                     '    if (norm) *norm = ceiling;\n    if (ceiling == 0) return 0;')
    source = replace(source, '    return best / ceiling;\n}',
                     '''    if (gap) *gap = (best - second) / ceiling;
    return best / ceiling;
}

static double glrt_spectrum(PortableVerifier *w, const GlrtComplex *values, int frames,
                            int *winner, unsigned *flags) {
    return glrt_spectrum_details(w, values, frames, winner, flags, NULL, NULL);
}

#include "receiver_phase_free_verify.inc"''')
    source = replace(source, 'double *exact, double *control, double *residual, unsigned *flags) {',
                     'double *exact, double *control, double *residual, unsigned *flags, '
                     'int allow_phase_free) {')
    begin = source.index('    if (integer) {', source.index('static int glrt('))
    stop = source.index('    if (!residual) return 0;', begin)
    stock = replace(source[begin:stop], '    int best, unused;\n', '    int unused;\n')
    guarded = '''    int best;
    if (integer || !allow_phase_free ||
        !phase_free_fractional(w, frames, starts, cfo, offset, exact, control, &best, flags)) {
''' + indent(stock, '    ', lambda line: not line.startswith('#')) + '    }\n'
    source = source[:begin] + guarded + source[stop:]
    source = replace(source, 'diagnostics ? &residual : NULL, &out->flags))',
                     'diagnostics ? &residual : NULL, &out->flags, 0))')
    source = replace(source, '&out->fractional_residual_hz, &out->flags))',
                     '&out->fractional_residual_hz, &out->flags, allow_phase_free))')
    source = replace(source, 'PortableVerifierResult *out, int diagnostics) {',
                     'PortableVerifierResult *out, int diagnostics, int allow_phase_free) {')
    source = replace(source, '    double freq = out->acquired_hz;',
                     '    w->phase_margin_radius = 0.;\n    double freq = out->acquired_hz;')
    source = replace(source, 'return verify_glrt(w, epoch, out, 1);',
                     'return verify_glrt(w, epoch, out, 1, 0);')
    return replace(source, 'return verify_glrt(w, epoch, out, 0);\n}',
                   '''return verify_glrt(w, epoch, out, 0, 1);
}

int portable_verifier_factor_reference(PortableVerifier *w, unsigned epoch,
                                       PortableVerifierResult *out) {
    return verify_glrt(w, epoch, out, 0, 0);
}''')


def measurement_overlay(source):
    signature = source.index('static int measure(')
    start = source.index('    int count = 0;', signature)
    end = source.index('int two_carrier_detect(', start)
    verify = source[start:end]
    verify = replace(verify, '    int count = 0;',
                     '    int count = 0;\n    double radius[2] = {0.};')
    call = '        if (portable_verifier_factor(r->verify, integer, &v)) return -1;'
    verify = replace(verify, call,
                     '''        int status = allow_phase_free
            ? portable_verifier_factor(r->verify, integer, &v)
            : portable_verifier_factor_reference(r->verify, integer, &v);
        if (status) return -1;''')
    verify = replace(verify, '        out[count++] =',
                     '        radius[count] = portable_verifier_margin_radius(r->verify);\n'
                     '        out[count++] =')
    verify = replace(verify, '    if (count == 2 && out[1].margin > out[0].margin) {',
                     '''    double combined = radius[0] + radius[1];
    if (allow_phase_free && count == 2 && combined > 0. &&
        fabs(out[1].margin - out[0].margin) <= combined) {
        portable_verifier_margin_order_retry();
        return verify_peaks(r, p, out, factors, 0);
    }
    if (count == 2 && out[1].margin > out[0].margin) {''')
    header = '''int portable_verifier_factor_reference(PortableVerifier *, unsigned,
                                       PortableVerifierResult *);
double portable_verifier_margin_radius(const PortableVerifier *);
void portable_verifier_margin_order_retry(void);

static int verify_peaks(TwoCarrierReceiver *r, const TimingFirstResult p[2],
                        TwoCarrierPeak out[2], ScanFactor *factors, int allow_phase_free) {
'''
    return (source[:signature] + header + verify + source[signature:start]
            + '    return verify_peaks(r, p, out, factors, 1);\n}\n\n' + source[end:])
