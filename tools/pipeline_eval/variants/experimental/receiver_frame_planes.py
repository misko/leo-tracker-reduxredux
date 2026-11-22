"""Share a normalized frame layout across the covariance and both selected projections."""

from .receiver_build import replace


def overlay(source):
    source = replace(source, '#include "receiver_mode_pair.inc"',
                     '#include "receiver_mode_pair.inc"\n#include "receiver_frame_planes.inc"')
    start = source.index("    const int paired =", source.index("static void principal_modes("))
    end = source.index("    for (int sweep = 0;", start)
    reference = source[start:end].splitlines(keepends=True)
    source = source[:start] + (
        '    const int have_planes = (w->width % 4 == 0) && __builtin_cpu_supports("avx2");\n'
        '    if (have_planes) {\n'
        '        build_frame_planes(w, low, covariance, axis);\n'
        '    } else {\n'
        + "".join("    " + line for line in reference)
        + "    }\n"
    ) + source[end:]
    return replace(source, "    memset(w->modes, 0, 2 * w->width * sizeof(Sample));",
                   "    if (have_planes) {\n"
                   "        project_frame_planes(w, covariance, axis);\n"
                   "        return;\n"
                   "    }\n"
                   "    memset(w->modes, 0, 2 * w->width * sizeof(Sample));")
