#!/bin/sh
set -eu
set -C
umask 077
mkdir /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/seed-pgo-v1/use /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/observations.tsv 151 8 512 8 4 16 > /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/seeds.stdout 2> /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/seeds.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/curvature-pgo-v1/use /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/observations.tsv --acceleration 250 --seeds /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/seeds.stdout > /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/tracks.stdout 2> /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/tracks.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 360 /mnt/glrtbench/prepared-threshold-full-v1/leo-memory-position /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/observations.tsv /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/graph.tsv /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/tracks.stdout /mnt/glrtbench/modular-orbit-v1/selected.tle -60 10 43 38.5816 -121.4944 250 1 /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/associations.json > /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/search.stdout 2> /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/search.stderr
cat /mnt/glrtbench/cadence-four-threshold-pgo-v1/scan-0/results/search.stdout
