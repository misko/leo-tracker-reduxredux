"""Bind one-pass receiver preparation to the fixed wide short-window path."""

from pathlib import Path

HEADER = Path(__file__).with_name("glrt_reuse_prepare.h")


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("wide preparation requires the exact archived source anchor")
    return source.replace(old, new)


def overlay(source):
    marker = '#include "kernel/private/dwell_input.h"'
    source = replace(source, marker, marker + '\n#include "glrt_reuse_prepare.h"')
    marker = "    int prepare_failed=context->receiver_count==1"
    return replace(
        source,
        marker,
        """    int prepare_failed;
#if LEO_GLRT_WIDE_DUAL_PREPARE
    if (wide && persistent_prepared && context->receiver_count==2 && prepare_count==200000u &&
        __builtin_cpu_supports("avx2"))
        prepare_failed=leo_prepare_wide_pair(prepared_view,ci16,prepare_count);
    else
#endif
    prepare_failed=context->receiver_count==1""",
    )
