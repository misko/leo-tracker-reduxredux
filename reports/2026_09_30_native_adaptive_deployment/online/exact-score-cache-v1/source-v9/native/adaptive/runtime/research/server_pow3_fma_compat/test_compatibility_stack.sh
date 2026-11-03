#!/bin/sh
set -eu

mode=${1:-host}
base=${2:-/tmp/leo-server-compatibility-stack-$mode}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
pow_out="$base/pow"
lexeme_out="$base/lexeme"

"$here/build.sh" "$mode" "$pow_out"
"$here/test.sh" "$mode" "$pow_out"
"$here/build_lexeme.sh" "$mode" "$lexeme_out"
"$here/test_lexeme.sh" "$mode" "$lexeme_out" "$pow_out/actual.tsv"

echo "server support compatibility stack: binary64 moments and Python lexemes exact"
