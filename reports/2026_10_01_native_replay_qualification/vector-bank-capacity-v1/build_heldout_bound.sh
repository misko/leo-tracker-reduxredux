#!/usr/bin/env bash
set -euo pipefail
mode="${1:?host or arm}"
library="${2:?qualified location build directory}"
output="${3:?output directory}"
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
mkdir -p "$output"
case "$mode" in
  host) compiler="${CXX:-g++}"; ar=ar; target=(); link=(-pthread);;
  arm)
    toolchain="${LEO_ARM_TOOLCHAIN:-/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf}"
    compiler="$toolchain-g++"; ar="$toolchain-ar"
    target=(-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard)
    link=(-pthread -static-libstdc++ -static-libgcc);;
  *) exit 2;;
esac
flags=(-std=c++17 -O3 -fno-fast-math "${target[@]}" -I "$root/native/adaptive/location")
if [[ "${6:-pair}" == subset ]]; then flags+=(-DLEO_RESEARCH_SUBSET_BOUND); fi
if [[ "${7:-generic}" == planned ]]; then flags+=(-DLEO_RESEARCH_PLANNED_BOUND); fi
if [[ "${9:-direct}" == horizon ]]; then flags+=(-DLEO_RESEARCH_HORIZON_PREFIX); fi
if [[ "${10:-quiet}" == profile ]]; then flags+=(-DLEO_RESEARCH_SCORE_PROFILE); fi
if [[ "${11:-uncached}" == cache ]]; then flags+=(-DLEO_RESEARCH_BOUND_CACHE); fi
if [[ "${12:-unbanked}" == bank ]]; then flags+=(-DLEO_RESEARCH_ENDPOINT_BANK); fi
if [[ "${13:-double-pair}" == float-pair ]]; then flags+=(-DLEO_RESEARCH_FLOAT_PAIR_BOUND); fi
if [[ "${14:-mutable}" == immutable ]]; then
  [[ "${12:-unbanked}" == bank ]] || { echo 'immutable session requires endpoint bank' >&2; exit 2; }
  flags+=(-DLEO_RESEARCH_IMMUTABLE_ORBIT)
fi
cli_flags=()
bank_mib="${16:-default}"
if [[ "$bank_mib" != default ]]; then
  [[ "$bank_mib" == 32 || "$bank_mib" == 64 || "$bank_mib" == 128 ]] || {
    echo 'endpoint bank MiB must be default, 32, 64 or 128' >&2; exit 2; }
  flags+=("-DLEO_RESEARCH_ENDPOINT_BANK_BYTES=$((bank_mib*1024*1024))")
fi
if [[ "${15:-scalar}" == vector ]]; then
  [[ "${14:-mutable}" == immutable && "${12:-unbanked}" == bank ]] || {
    echo 'vector pair bounds require immutable endpoint bank' >&2; exit 2; }
  flags+=(-DLEO_RESEARCH_VECTOR_PAIR_BOUND)
fi
if [[ "${4:-cold}" == warm ]]; then cli_flags=(-DLEO_RESEARCH_SCORE_WARM_START); fi
if [[ "${5:-quiet}" == progress ]]; then cli_flags+=(-DLEO_RESEARCH_SEARCH_PROGRESS); fi
if [[ "${8:-full}" == capped ]]; then cli_flags+=(-DLEO_RESEARCH_CAPPED_SEARCH); fi
"$compiler" "${flags[@]}" -DLEO_RESEARCH_HELDOUT_BOUND -c \
  "$root/native/adaptive/location/score.cpp" -o "$output/score.o"
"$ar" rcs "$output/libleolocation.a" "$library/orbit.o" "$library/search.o" "$library/sgp4.o" "$output/score.o"
"$compiler" "${flags[@]}" "${cli_flags[@]}" "$root/native/adaptive/location/location_cli.cpp" \
  "$output/libleolocation.a" "${link[@]}" -lm -o "$output/leo-location"
tests=(test_heldout_bound test_horizon_prefix test_bound_state_cache test_endpoint_state_bank test_float_pair_bound test_location)
if [[ "${15:-scalar}" == vector ]]; then tests+=(test_doppler_interval4); fi
if [[ "${14:-mutable}" == immutable ]]; then tests+=(test_immutable_orbit); fi
for test in "${tests[@]}"; do
  source="$root/tests/native_adaptive/location/$test.cpp"
  if [[ "$test" != test_location ]]; then source="$root/tests/native_adaptive/location/research/$test.cpp"; fi
  "$compiler" "${flags[@]}" "$source" "$output/libleolocation.a" "${link[@]}" -lm -o "$output/$test"
  if [[ "$mode" == host ]]; then "$output/$test"; fi
done
