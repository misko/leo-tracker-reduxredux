#!/bin/sh
set -eu

test "$#" -eq 2
test ! -e /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_full88/solver/resource-time.txt
exec /usr/bin/time -v \
  -o /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_full88/solver/resource-time.txt \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_ds7_full88/solver/run-joint-v1.sh "$1" "$2"
