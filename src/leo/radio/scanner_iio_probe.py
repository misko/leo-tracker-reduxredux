"""Private child process for the bounded scanner endpoint probe."""

import sys

from leo.radio.scanner_iio_compat import verify_endpoint

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(2)
    verify_endpoint(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    print("scanner-endpoint-verified")
