#!/bin/sh
set -eu
set -C
umask 077
mkdir /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/seed-pgo-v1/use /mnt/glrtbench/three-distinct-cadence-v2/scan-2/observations.tsv 151 8 512 8 4 16 > /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/seeds.stdout 2> /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/seeds.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/curvature-pgo-v1/use /mnt/glrtbench/three-distinct-cadence-v2/scan-2/observations.tsv --acceleration 250 --seeds /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/seeds.stdout > /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/tracks.stdout 2> /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/tracks.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 600 /mnt/glrtbench/prepared-threshold-full-v1/leo-memory-position /mnt/glrtbench/three-distinct-cadence-v2/scan-2/observations.tsv /mnt/glrtbench/three-distinct-cadence-v2/scan-2/graph.tsv /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/tracks.stdout /mnt/glrtbench/three-scan-iq-v1/scan-fw-ee2831131a88440f/selected.tle -60 10 43 38.5816 -121.4944 250 1 /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/associations.json > /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/search.stdout 2> /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/search.stderr
cat /mnt/glrtbench/three-distinct-cadence-v2/scan-2/results/search.stdout
