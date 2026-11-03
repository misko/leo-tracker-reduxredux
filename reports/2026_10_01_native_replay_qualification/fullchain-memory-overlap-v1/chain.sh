#!/bin/sh
set -eu
set -C
umask 077
mkdir /mnt/glrtbench/fullchain-memory-overlap-v1/results
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/fresh-graph-tracking-v1/seed /mnt/glrtbench/modular-ds9-iq-v1/overlap-vector-queue16-observations-v1.tsv 151 8 512 8 4 16 > /mnt/glrtbench/fullchain-memory-overlap-v1/results/seeds.stdout 2> /mnt/glrtbench/fullchain-memory-overlap-v1/results/seeds.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 90 /mnt/glrtbench/fresh-graph-tracking-v1/tracker /mnt/glrtbench/modular-ds9-iq-v1/overlap-vector-queue16-observations-v1.tsv --acceleration 250 --seeds /mnt/glrtbench/fullchain-memory-overlap-v1/results/seeds.stdout > /mnt/glrtbench/fullchain-memory-overlap-v1/results/tracks.stdout 2> /mnt/glrtbench/fullchain-memory-overlap-v1/results/tracks.stderr
/mnt/glrtbench/native-adaptive/current/measure-run 360 /mnt/glrtbench/fullchain-memory-overlap-v1/leo-memory-position /mnt/glrtbench/modular-ds9-iq-v1/overlap-vector-queue16-observations-v1.tsv /mnt/glrtbench/modular-ds9-iq-v1/overlap-vector-queue16-graph-v1.tsv /mnt/glrtbench/fullchain-memory-overlap-v1/results/tracks.stdout /mnt/glrtbench/modular-orbit-v1/selected.tle -60 10 43 38.5816 -121.4944 250 1 /mnt/glrtbench/fullchain-memory-overlap-v1/results/associations.json > /mnt/glrtbench/fullchain-memory-overlap-v1/results/search.stdout 2> /mnt/glrtbench/fullchain-memory-overlap-v1/results/search.stderr
cat /mnt/glrtbench/fullchain-memory-overlap-v1/results/search.stdout
