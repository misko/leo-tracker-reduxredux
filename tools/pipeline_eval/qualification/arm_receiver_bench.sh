#!/bin/sh
set -eu
cd "$(dirname "$0")"
sha256sum -c SHA256SUMS >&2
case ${1:-native} in
    native) ;;
    qemu) command -v qemu-aarch64 >/dev/null ;;
    *) printf '%s\n' 'usage: ./benchmark [native|qemu]' >&2; exit 2 ;;
esac
for edge in lower upper; do
    case $edge in lower) modes='stock fifth' ;; upper) modes='fifth stock' ;; esac
    for mode in $modes; do
        printf '{"kind":"stream","edge":"%s","mode":"%s"}\n' "$edge" "$mode"
        set -- "${1:-native}" ./arm-receiver "$mode" "templates/$edge-exact.c16" \
            "templates/$edge-control.c16" "templates/$edge-filters.c8" \
            "templates/$edge-energies.f64" 2 "fixtures/$edge/"*.ci16
        backend=$1
        shift
        case $backend in qemu) qemu-aarch64 -cpu cortex-a53 "$@" ;; native) "$@" ;; esac
        set -- "$backend"
    done
done
