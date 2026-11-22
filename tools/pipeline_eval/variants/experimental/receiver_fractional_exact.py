"""Restore absolute-phase verification without replaying a selected lane."""

from .receiver_build import replace


def overlay(source, *, defer=False):
    if not defer:
        source = replace(source, 'return verify_glrt(w, epoch, out, 0, 1);',
                         'return verify_glrt(w, epoch, out, 0, 0);')
    source = replace(source, 'GlrtComplex glrt_rotation[max_frames * aperture];',
                     'GlrtComplex glrt_rotation[aperture];')
    source = replace(source, 'int32_t indices[max_frames * aperture], weight_row[max_frames * aperture];',
                     'int32_t indices[aperture], weight_row[aperture];')
    source = replace(source, '#include "receiver_stencil_verify.inc"',
                     '#include "receiver_stencil_verify.inc"\n'
                     '#ifndef LEO_DIRECT_KERNEL\n#include "receiver_fractional_exact.inc"\n#endif')
    start = source.index('        } else {\n', source.index('static int glrt('))
    end = source.index('#endif\n        int unused;', start)
    source = source[:start] + '''        } else if (absolute_fractional_correlations(w, frames, starts, cfo, offset)) {
            return -1;
        }
''' + source[end:]
    begin = source.index('    double steps[max_frames * 63];')
    end = source.index('    if (!frames) {', begin)
    geometry = source[begin:end]
    first_step = geometry.index('        if (residual) {')
    last_step = geometry.index('        ++frames;', first_step)
    steps = geometry[first_step:last_step]
    source = replace(source, geometry, geometry[len('    double steps[max_frames * 63];\n'):first_step]
                     + geometry[last_step:])
    steps = steps.removeprefix('        if (residual) {\n').removesuffix('        }\n')
    steps = '\n'.join(line[4:] for line in steps.splitlines()).replace('steps[frames*63', 'steps[frame*63')
    source = replace(source, '    int count = frames*63;', '''    if (!best) {
        *residual = 0.;
        return 0;
    }
    double steps[max_frames * 63];
    for (int frame = 0; frame < frames; ++frame) {
        int start = starts[frame] - (integer ? first + (int)nearbyint(offset) : 0);
''' + steps + '''
    }
    int count = frames*63;''')
    if defer:
        source += '''
int experimental_exact_fractional_score(PortableVerifier *w, unsigned epoch, double seed_hz,
                                        double offset, double *exact, double *control) {
    unsigned flags = 0;
    return glrt(w, epoch, seed_hz, offset, exact, control, NULL, &flags, 0);
}
'''
    return source


def deferred_measurement(source):
    factor = '''typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} ScanFactor;
'''
    source = replace(source, factor, '')
    source = replace(source, 'struct TwoCarrierReceiver {', factor + '\nstruct TwoCarrierReceiver {')
    source = replace(source, '    TimingFirst *timing;', '''    TimingFirst *timing;
    unsigned valid_score, approximate_score;
    double seed_hz[2];
    ScanFactor measured[2];''')
    source = replace(source, '    int count = 0;\n    double radius[2] = {0.};',
                     '    int count = 0;\n    double radius[2] = {0.};\n'
                     '    r->valid_score = r->approximate_score = 0;')
    source = replace(source, '    if (!r || !out) return -1;',
                     '    if (!r || !out) return -1;\n    r->valid_score = r->approximate_score = 0;')
    source = replace(source, '        radius[count] = portable_verifier_margin_radius(r->verify);',
                     '''        radius[count] = portable_verifier_margin_radius(r->verify);
        if (factors) {
            r->measured[i] = factors[count];
            r->seed_hz[i] = p[i].hz;
            r->valid_score |= 1u << i;
            if (radius[count] > 0.) r->approximate_score |= 1u << i;
        }''')
    return source + '\n#include "receiver_fractional_selected.inc"\n'
