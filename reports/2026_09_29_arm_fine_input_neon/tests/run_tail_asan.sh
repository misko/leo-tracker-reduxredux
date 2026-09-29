#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out="$root/tests/test_fine_precision_tail_asan"
gcc -DLEO_PRESENCE_FFTW=1 -DLEO_PROPOSAL_LIBRARY -DLEO_PROPOSAL_OMIT_POWER=1 \
  -DLEO_NEON_CONDITIONED_MOMENTS=1 -std=c11 -O1 -Wall -Wextra \
  -fno-fast-math -fno-math-errno -fno-trapping-math -fcx-limited-range \
  -DLEO_FINE_FRAME_BUDGET_DEFAULT=0 -DSKIP_CONDITIONED_RECHECK=1 \
  -DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1 -DLEO_PRESENCE_COARSE_FRAMES=16 \
  -DLEO_PRESENCE_COARSE_FP32 -DLEO_FULL_CONDITIONED_SCREEN \
  -DLEO_FULL_REFINEMENT_MODE=2 -g -fno-omit-frame-pointer \
  -fsanitize=address,undefined -I "$root/sources/src/native_presence" -I "$root/sources" \
  "$root/tests/test_fine_precision_tail_asan.c" "$root/sources/conditioned_czt.c" \
  "$root/sources/fft_full.c" -lfftw3f -lfftw3 -lm -fsanitize=address,undefined \
  -o "$out"
ASAN_OPTIONS=detect_leaks=0 "$out"
