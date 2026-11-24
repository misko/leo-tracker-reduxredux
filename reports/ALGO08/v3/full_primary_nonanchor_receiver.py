"""Research opt-in for full-aperture primaries between two-scan stereo anchors."""

from contextlib import ExitStack, contextmanager
import ctypes
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import mixed_aperture_receiver as mixed


LIBRARY = Path("/var/tmp/leo-algo08v3-primary-schedule-trial-native/primary.so")
LIBRARY_SHA256 = "5e9667bbe38c1aeb897189c5ebff0a05cd400fd21f41703a279a384c202f3f50"
ROLES = {"full": "20ms_two_scan", "short_primary": "20ms_primary"}
DESCRIPTION = "20 ms full two-scan anchors and 20 ms primary nonanchors, strongest verified margin"


def recipe():
    return dict(installed_sha256=mixed.INSTALLED_SHA, primary_helper_sha256=LIBRARY_SHA256,
                adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                rule=[ROLES[mode] for mode in mixed.FULL_RULE], streams=["edge", "channel", "actual_rf_hz"],
                aperture_samples=[200_000, 200_000],
                selection="maximum verified fractional margin, lower native rank on tie")


class FullPrimaryNonanchor(mixed.MixedApertureDetector):
    def __init__(self, installed):
        super().__init__(installed, mixed.INSTALLED_SHA, full_coverage=True)
        mixed.verified(LIBRARY, LIBRARY_SHA256)
        self.primary = ctypes.CDLL(str(LIBRARY)).primary_factors

    @contextmanager
    def detector(self, *args, **kwargs):
        original = mixed.NativePath

        def bind(library, pilot, mode):
            path = original(library, pilot, "full")
            if mode == "short_primary":
                self.primary.argtypes, self.primary.restype = path.call.argtypes, path.call.restype
                path.call, path.maximum = self.primary, 1
            return path

        with ExitStack() as scope:
            with patch.object(mixed, "NativePath", bind):
                receive = scope.enter_context(super().detector(*args, **kwargs))
            yield receive

    def receipt(self):
        audit = super().receipt()
        audit["rule"] = [ROLES[mode] for mode in audit["rule"]]
        del audit["short_primary_sha256"]
        audit["primary_helper_sha256"] = LIBRARY_SHA256
        for field in ("visits", "native_calls", "factors", "native_cpu_ns", "native_wall_ns"):
            audit[field] = {ROLES[mode]: value for mode, value in audit[field].items()}
        return audit
