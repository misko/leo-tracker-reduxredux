"""Hold the bounded ordinary short-window CI16 preparation in its native context."""

_SPARSE = "    if(dwell_ms==120&&stride_ms==120){\n        prepared_view=&context->sparse_prepared;"
_SHORT = (
    "    if(short_window||(dwell_ms==120&&stride_ms==120)){\n"
    "        prepared_view=&context->sparse_prepared;"
)


def retain_short_window_preparation(source: str) -> str:
    if source.count(_SPARSE) != 1:
        raise ValueError("ordinary prepared-buffer source binding changed")
    return source.replace(_SPARSE, _SHORT)
