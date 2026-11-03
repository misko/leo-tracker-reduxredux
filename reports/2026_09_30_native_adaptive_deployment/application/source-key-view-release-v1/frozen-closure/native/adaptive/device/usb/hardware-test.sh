#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../../../.." && pwd)"
output="${1:-$root/native/adaptive/device/usb/build/soapy}"
"$root/native/adaptive/device/usb/build-soapy.sh" "$output" >/dev/null
: "${LEO_USB_SDR_SELECTOR:?set an explicit Soapy selector}"
: "${LEO_USB_ALLOW_CAPTURE:?set to yes to authorize one receive block}"
: "${LEO_USB_SAMPLE_RATE_HZ:?required}"
: "${LEO_USB_BANDWIDTH_HZ:?required}"
: "${LEO_USB_BLOCK_SAMPLES:?required}"
: "${LEO_USB_FREQUENCY_HZ:?required}"
: "${LEO_USB_FREQUENCY_ERROR_HZ:?required}"
"$output/test-soapy-hardware"
