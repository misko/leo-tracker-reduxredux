# DSX01-S01: ordered polynomial track review

Original Graph fragments, ordered by receiver, channel and start time. Satellite fits use the supplied GPS, per-scan/RX/band hardware and one orbital phase per NORAD. These are candidate matches, not authenticated satellite IDs.

The gray curve is the frozen polynomial. Blue is physical Doppler plus the fitted shared hardware, shared satellite phase, native alias and penalized component constant. No component slope is removed. Each residual plot retains all original points. Linear fragments do not calibrate hardware or orbital phase.

| Order | Track | Time s | Points | Candidate | Doppler RMS Hz | Result |
|---|---|---|---|---|---|---|
| 1 | [S01-RX1-CH1-T008](S01-RX1-CH1-T008.png) | 0.72–26.98 | 28 | 47357 | 136.7 | candidate compatible |
| 2 | [S01-RX1-CH1-T004](S01-RX1-CH1-T004.png) | 20.94–43.30 | 25 | 67654 | 85.3 | candidate compatible |
| 3 | [S01-RX1-CH1-T011](S01-RX1-CH1-T011.png) | 44.37–53.24 | 13 | 47357 | 74.6 | candidate compatible |
| 4 | [S01-RX1-CH1-T005](S01-RX1-CH1-T005.png) | 52.53–73.10 | 30 | 69433 | 123.4 | candidate compatible |
| 5 | [S01-RX1-CH1-T000](S01-RX1-CH1-T000.png) | 74.52–92.98 | 25 | 60372 | 114.2 | candidate compatible |
| 6 | [S01-RX1-CH1-T012](S01-RX1-CH1-T012.png) | 90.85–102.91 | 16 | 64936 | 149.8 | rejected: bias_bound |
| 7 | [S01-RX1-CH1-T013](S01-RX1-CH1-T013.png) | 120.30–138.40 | 17 | 56413 | 378.9 | rejected: slope, curvature |
| 8 | [S01-RX1-CH1-T009](S01-RX1-CH1-T009.png) | 134.49–168.92 | 27 | 60282 | 1055.7 | rejected: rms, bias_bound |
| 9 | [S01-RX1-CH1-T001](S01-RX1-CH1-T001.png) | 151.17–184.54 | 32 | 69546 | 175.8 | rejected: slope, curvature |
| 10 | [S01-RX1-CH1-T002](S01-RX1-CH1-T002.png) | 180.27–193.06 | 19 | 100015 | 162.7 | candidate compatible |
| 11 | [S01-RX1-CH1-T007](S01-RX1-CH1-T007.png) | 194.47–224.63 | 26 | 66163 | 110.4 | candidate compatible |
| 12 | [S01-RX1-CH1-T003](S01-RX1-CH1-T003.png) | 210.79–254.09 | 57 | 65627 | 142.6 | candidate compatible |
| 13 | [S01-RX1-CH1-T006](S01-RX1-CH1-T006.png) | 256.22–284.26 | 36 | 67658 | 193.7 | rejected: slope, curvature, step |
| 14 | [S01-RX1-CH1-T010](S01-RX1-CH1-T010.png) | 284.61–298.82 | 15 | 69428 | 192.4 | rejected: slope, curvature, bias_bound |
| 15 | S01-RX1-CH2-T005 | 0.41–41.22 | 33 | 66151 | 148.1 | rejected: slope, step |
| 16 | S01-RX1-CH2-T010 | 26.66–39.08 | 9 | 67954 | 72.9 | candidate compatible |
| 17 | S01-RX1-CH2-T002 | 40.50–73.14 | 38 | 69433 | 127.4 | candidate compatible |
| 18 | S01-RX1-CH2-T007 | 74.57–89.11 | 22 | 64936 | 66.8 | rejected: bias_bound |
| 19 | S01-RX1-CH2-T004 | 90.53–116.44 | 33 | 69333 | 130.2 | rejected: slope, curvature, step |
| 20 | S01-RX1-CH2-T011 | 108.64–118.93 | 9 | 64936 | 147.1 | rejected: bias_bound |
| 21 | S01-RX1-CH2-T001 | 120.34–162.93 | 61 | 63474 | 1087.5 | rejected: slope, curvature, step, correlation, rms, bias_bound |
| 22 | S01-RX1-CH2-T003 | 166.48–194.16 | 37 | 69522 | 123.7 | candidate compatible |
| 23 | S01-RX1-CH2-T009 | 194.52–208.36 | 12 | 69546 | 91.1 | rejected:  |
| 24 | S01-RX1-CH2-T008 | 210.13–222.19 | 17 | 66163 | 113.7 | candidate compatible |
| 25 | S01-RX1-CH2-T006 | 218.99–238.87 | 26 | 65627 | 74.3 | candidate compatible |
| 26 | S01-RX1-CH2-T000 | 240.30–298.86 | 80 | 62811 | 201.0 | rejected: slope, curvature, step, correlation |
| 27 | S01-RX1-CH3-T006 | 14.65–49.07 | 37 | 47357 | 116.8 | rejected: curvature |
| 28 | S01-RX1-CH3-T007 | 34.51–59.00 | 25 | 69333 | 120.0 | rejected: slope |
| 29 | S01-RX1-CH3-T005 | 60.42–89.16 | 31 | 62052 | 176.5 | rejected: slope, curvature, step |
| 30 | S01-RX1-CH3-T008 | 74.61–88.81 | 12 | 60372 | 92.9 | candidate compatible |
| 31 | S01-RX1-CH3-T009 | 90.58–103.00 | 19 | 64936 | 189.7 | rejected: slope, curvature, bias_bound |
| 32 | S01-RX1-CH3-T002 | 150.55–178.59 | 27 | 63474 | 2111.9 | rejected: curvature, correlation, rms, bias_bound |
| 33 | S01-RX1-CH3-T003 | 164.75–208.75 | 27 | 100168 | 134.5 | candidate compatible |
| 34 | S01-RX1-CH3-T004 | 172.20–198.47 | 17 | 100168 | 92.6 | candidate compatible |
| 35 | S01-RX1-CH3-T012 | 210.17–220.46 | 8 | 69546 | 189.3 | rejected:  |
| 36 | S01-RX1-CH3-T001 | 224.37–282.22 | 33 | 62811 | 93.1 | candidate compatible |
| 37 | S01-RX1-CH3-T000 | 224.72–276.89 | 43 | 62811 | 161.2 | rejected: correlation |
| 38 | S01-RX1-CH3-T010 | 276.18–282.92 | 8 | 67938 | 72.2 | rejected: bias_bound |
| 39 | S01-RX1-CH3-T011 | 284.70–298.91 | 21 | 67658 | 143.5 | rejected:  |
| 40 | S01-RX1-CH4-T000 | 0.50–29.24 | 43 | 69523 | 180.7 | rejected: slope, curvature, step, correlation |
| 41 | S01-RX1-CH4-T001 | 32.78–92.75 | 45 | 69333 | 234.7 | rejected: slope, curvature, step, correlation |
| 42 | S01-RX1-CH4-T002 | 34.56–63.30 | 13 | 69333 | 100.0 | candidate compatible |
| 43 | S01-RX1-CH4-T003 | 42.72–76.78 | 18 | 69333 | 153.4 | rejected: slope, curvature |
| 44 | S01-RX1-CH4-T015 | 76.43–103.05 | 15 | 69333 | 120.2 | candidate compatible |
| 45 | S01-RX1-CH4-T004 | 90.62–102.69 | 10 | 69333 | 106.8 | candidate compatible |
| 46 | S01-RX1-CH4-T006 | 104.47–119.01 | 23 | 64936 | 176.3 | rejected: slope, curvature, bias_bound |
| 47 | S01-RX1-CH4-T007 | 120.43–136.40 | 23 | 62814 | 146.8 | rejected: slope, curvature, step |
| 48 | S01-RX1-CH4-T011 | 136.75–149.17 | 18 | 69546 | 151.6 | rejected:  |
| 49 | S01-RX1-CH4-T010 | 150.24–163.02 | 17 | 68736 | 444.8 | rejected: slope, curvature, bias_bound |
| 50 | S01-RX1-CH4-T012 | 180.41–192.48 | 15 | 62814 | 155.7 | candidate compatible |
| 51 | S01-RX1-CH4-T009 | 182.90–208.44 | 22 | 69546 | 225.4 | rejected: slope, curvature |
| 52 | S01-RX1-CH4-T008 | 210.22–222.99 | 21 | 58952 | 94.3 | candidate compatible |
| 53 | S01-RX1-CH4-T005 | 224.41–274.81 | 72 | 62811 | 112.3 | candidate compatible |
| 54 | S01-RX1-CH4-T013 | 272.68–284.03 | 13 | 69332 | 137.4 | candidate compatible |
| 55 | S01-RX1-CH4-T014 | 284.39–298.95 | 21 | 69428 | 219.5 | rejected: slope, curvature, bias_bound |
| 56 | S01-RX1-CH5-T000 | 0.19–49.86 | 63 | 69523 | 193.2 | rejected: slope, curvature, step, correlation |
| 57 | S01-RX1-CH5-T008 | 60.16–71.50 | 16 | 67654 | 120.3 | candidate compatible |
| 58 | S01-RX1-CH5-T004 | 75.41–104.16 | 44 | 69333 | 191.9 | rejected: slope, curvature, step, correlation |
| 59 | S01-RX1-CH5-T007 | 119.77–151.34 | 28 | 62814 | 170.0 | rejected: slope, curvature, step |
| 60 | S01-RX1-CH5-T009 | 149.57–173.71 | 20 | 69522 | 121.9 | candidate compatible |
| 61 | S01-RX1-CH5-T001 | 165.19–191.46 | 25 | 100168 | 138.8 | candidate compatible |
| 62 | S01-RX1-CH5-T003 | 180.10–193.23 | 13 | 69522 | 118.3 | candidate compatible |
| 63 | S01-RX1-CH5-T002 | 195.36–235.10 | 38 | 58952 | 170.9 | candidate compatible |
| 64 | S01-RX1-CH5-T010 | 215.93–237.94 | 8 | 65627 | 193.3 | candidate compatible |
| 65 | S01-RX1-CH5-T006 | 255.34–269.18 | 21 | 67658 | 126.6 | rejected:  |
| 66 | S01-RX1-CH5-T005 | 269.53–299.71 | 41 | 69332 | 136.8 | candidate compatible |
| 67 | S01-RX1-CH6-T003 | 0.23–32.16 | 42 | 69523 | 210.7 | rejected: slope, curvature, step, correlation |
| 68 | S01-RX1-CH6-T004 | 29.68–58.07 | 32 | 47357 | 93.8 | candidate compatible |
| 69 | S01-RX1-CH6-T009 | 33.94–44.23 | 9 | 67954 | 84.4 | candidate compatible |
| 70 | S01-RX1-CH6-T000 | 59.49–105.98 | 66 | 60372 | 155.7 | rejected: slope, curvature, step |
| 71 | S01-RX1-CH6-T001 | 105.27–177.30 | 71 | 63474 | 1556.3 | rejected: slope, curvature, step, correlation, rms, bias_bound |
| 72 | S01-RX1-CH6-T007 | 151.74–184.05 | 16 | 66163 | 141.7 | candidate compatible |
| 73 | S01-RX1-CH6-T006 | 179.43–193.63 | 17 | 69546 | 191.0 | rejected:  |
| 74 | S01-RX1-CH6-T005 | 195.40–221.31 | 25 | 69522 | 76.0 | candidate compatible |
| 75 | S01-RX1-CH6-T008 | 225.21–233.72 | 9 | 62811 | 58.7 | candidate compatible |
| 76 | S01-RX1-CH6-T002 | 255.38–299.75 | 63 | 69428 | 330.4 | rejected: slope, curvature, step, correlation, bias_bound |
| 77 | S01-RX1-CH7-T000 | 0.28–43.92 | 47 | 69523 | 225.7 | rejected: slope, curvature, step, correlation |
| 78 | S01-RX1-CH7-T014 | 20.15–41.44 | 12 | 47357 | 64.2 | candidate compatible |
| 79 | S01-RX1-CH7-T005 | 42.15–58.12 | 18 | 69433 | 154.8 | candidate compatible |
| 80 | S01-RX1-CH7-T008 | 59.89–74.08 | 22 | 67954 | 179.1 | candidate compatible |
| 81 | S01-RX1-CH7-T006 | 75.50–91.46 | 21 | 60372 | 154.3 | candidate compatible |
| 82 | S01-RX1-CH7-T007 | 89.69–104.25 | 20 | 64936 | 170.2 | rejected: curvature, bias_bound |
| 83 | S01-RX1-CH7-T015 | 121.98–137.60 | 8 | 62814 | 130.5 | candidate compatible |
| 84 | S01-RX1-CH7-T001 | 137.95–163.86 | 21 | 63474 | 574.9 | rejected: slope, curvature, rms, bias_bound |
| 85 | S01-RX1-CH7-T002 | 149.66–162.08 | 15 | 63474 | 272.5 | rejected: slope, curvature, bias_bound |
| 86 | S01-RX1-CH7-T013 | 165.28–174.15 | 9 | 100168 | 113.8 | candidate compatible |
| 87 | S01-RX1-CH7-T009 | 179.47–194.03 | 17 | 62814 | 175.6 | candidate compatible |
| 88 | S01-RX1-CH7-T003 | 195.45–231.99 | 35 | 66163 | 182.4 | rejected: slope, curvature, step, correlation |
| 89 | S01-RX1-CH7-T010 | 225.96–253.30 | 14 | 65627 | 269.1 | candidate compatible |
| 90 | S01-RX1-CH7-T004 | 255.07–277.07 | 25 | 62811 | 168.3 | candidate compatible |
| 91 | S01-RX1-CH7-T011 | 275.30–283.81 | 9 | 69332 | 93.7 | candidate compatible |
| 92 | S01-RX1-CH7-T012 | 285.23–297.66 | 16 | 67658 | 118.7 | rejected:  |
| 93 | S01-RX1-CH8-T000 | 0.32–33.67 | 48 | 69523 | 216.1 | rejected: slope, curvature, step, correlation |
| 94 | S01-RX1-CH8-T001 | 34.03–58.16 | 34 | 69333 | 124.7 | rejected: slope |
| 95 | S01-RX1-CH8-T005 | 75.54–101.81 | 27 | 69333 | 156.7 | candidate compatible |
| 96 | S01-RX1-CH8-T010 | 95.77–114.22 | 9 | 64936 | 123.1 | rejected: bias_bound |
| 97 | S01-RX1-CH8-T003 | 135.51–155.38 | 17 | 63474 | 466.2 | rejected: slope, curvature, rms, bias_bound |
| 98 | S01-RX1-CH8-T004 | 145.80–159.29 | 10 | 63474 | 332.0 | rejected: curvature, bias_bound |
| 99 | S01-RX1-CH8-T009 | 160.00–178.10 | 10 | 100168 | 123.7 | candidate compatible |
| 100 | S01-RX1-CH8-T006 | 172.07–194.08 | 22 | 58952 | 2308.8 | rejected: curvature, rms, bias_bound |
| 101 | S01-RX1-CH8-T002 | 225.30–257.24 | 41 | 62811 | 140.4 | candidate compatible |
| 102 | S01-RX1-CH8-T007 | 251.57–269.31 | 22 | 67658 | 108.8 | rejected:  |
| 103 | S01-RX1-CH8-T008 | 269.66–283.14 | 10 | 62811 | 173.6 | candidate compatible |
| 104 | S01-RX2-CH1-T004 | 14.91–43.30 | 33 | 67654 | 132.1 | candidate compatible |
| 105 | S01-RX2-CH1-T010 | 46.85–59.27 | 16 | 47357 | 95.3 | rejected: slope |
| 106 | S01-RX2-CH1-T005 | 60.34–73.10 | 20 | 51117 | 257.1 | rejected: slope, curvature |
| 107 | S01-RX2-CH1-T012 | 74.52–83.03 | 13 | 47357 | 101.8 | candidate compatible |
| 108 | S01-RX2-CH1-T001 | 77.00–102.91 | 28 | 62052 | 134.4 | rejected: slope, curvature, step, correlation |
| 109 | S01-RX2-CH1-T011 | 104.69–119.23 | 22 | 60372 | 64.2 | candidate compatible |
| 110 | S01-RX2-CH1-T002 | 121.01–149.04 | 25 | 100320 | 191.5 | rejected: slope, curvature |
| 111 | S01-RX2-CH1-T006 | 150.46–158.27 | 10 | 100168 | 198.6 | candidate compatible |
| 112 | S01-RX2-CH1-T007 | 164.66–184.18 | 22 | 63474 | 140.6 | rejected: slope, curvature, bias_bound |
| 113 | S01-RX2-CH1-T008 | 194.47–209.02 | 23 | 100168 | 29.9 | candidate compatible |
| 114 | S01-RX2-CH1-T000 | 210.44–254.09 | 59 | 66163 | 90.6 | rejected: slope, curvature, step |
| 115 | S01-RX2-CH1-T003 | 254.80–284.26 | 39 | 59326 | 107.0 | rejected: slope, curvature, step |
| 116 | S01-RX2-CH1-T009 | 284.61–298.82 | 21 | 62811 | 35.6 | candidate compatible |
| 117 | S01-RX2-CH2-T000 | 14.96–68.54 | 65 | 66151 | 80.0 | candidate compatible |
| 118 | S01-RX2-CH2-T007 | 60.38–73.14 | 15 | 51117 | 312.2 | rejected: slope, curvature |
| 119 | S01-RX2-CH2-T005 | 74.57–86.63 | 18 | 47357 | 129.3 | rejected: slope, curvature |
| 120 | S01-RX2-CH2-T009 | 90.53–102.96 | 19 | 51117 | 160.4 | rejected: slope, curvature |
| 121 | S01-RX2-CH2-T008 | 104.38–118.93 | 23 | 60372 | 62.8 | candidate compatible |
| 122 | S01-RX2-CH2-T001 | 120.35–149.08 | 43 | 100320 | 234.0 | rejected: slope, curvature, step |
| 123 | S01-RX2-CH2-T003 | 150.50–162.93 | 19 | 63474 | 225.3 | rejected: bias_bound |
| 124 | S01-RX2-CH2-T004 | 164.71–178.90 | 20 | 100168 | 63.0 | candidate compatible |
| 125 | S01-RX2-CH2-T006 | 210.13–224.32 | 21 | 62814 | 41.4 | candidate compatible |
| 126 | S01-RX2-CH2-T002 | 266.20–298.86 | 38 | 62811 | 78.7 | candidate compatible |
| 127 | S01-RX2-CH3-T003 | 40.55–59.01 | 28 | 47357 | 157.7 | rejected: slope |
| 128 | S01-RX2-CH3-T001 | 62.55–103.00 | 52 | 62052 | 187.8 | rejected: slope, curvature, step, correlation |
| 129 | S01-RX2-CH3-T007 | 118.97–133.16 | 14 | 58219 | 19.8 | candidate compatible |
| 130 | S01-RX2-CH3-T000 | 150.55–209.11 | 80 | 100168 | 101.6 | rejected: slope, curvature, step |
| 131 | S01-RX2-CH3-T002 | 224.72–254.18 | 28 | 58952 | 45.6 | rejected: correlation |
| 132 | S01-RX2-CH3-T004 | 254.54–268.73 | 21 | 57784 | 64.1 | rejected:  |
| 133 | S01-RX2-CH3-T006 | 270.15–282.92 | 18 | 59326 | 21.4 | candidate compatible |
| 134 | S01-RX2-CH3-T005 | 284.70–298.91 | 20 | 62811 | 33.3 | candidate compatible |
| 135 | S01-RX2-CH4-T003 | 30.66–43.08 | 19 | 66151 | 20.2 | candidate compatible |
| 136 | S01-RX2-CH4-T008 | 45.21–70.75 | 10 | 69523 | 215.8 | candidate compatible |
| 137 | S01-RX2-CH4-T004 | 90.62–102.69 | 16 | 51117 | 165.0 | rejected: slope, curvature |
| 138 | S01-RX2-CH4-T007 | 104.47–119.01 | 20 | 60372 | 88.6 | candidate compatible |
| 139 | S01-RX2-CH4-T000 | 110.50–172.60 | 73 | 100320 | 287.9 | rejected: curvature, step, correlation |
| 140 | S01-RX2-CH4-T002 | 184.67–222.99 | 51 | 62814 | 86.4 | rejected: slope, step |
| 141 | S01-RX2-CH4-T006 | 224.41–234.34 | 10 | 58952 | 27.3 | candidate compatible |
| 142 | S01-RX2-CH4-T001 | 226.89–268.78 | 55 | 57784 | 79.3 | rejected: step |
| 143 | S01-RX2-CH4-T005 | 270.55–298.95 | 15 | 62811 | 131.2 | candidate compatible |
| 144 | S01-RX2-CH5-T001 | 45.61–87.47 | 34 | 66151 | 30.6 | candidate compatible |
| 145 | S01-RX2-CH5-T002 | 97.77–118.00 | 23 | 60372 | 68.6 | candidate compatible |
| 146 | S01-RX2-CH5-T000 | 165.19–207.78 | 60 | 100168 | 106.7 | rejected: slope, curvature, step |
| 147 | S01-RX2-CH5-T004 | 209.55–223.75 | 17 | 62814 | 36.1 | candidate compatible |
| 148 | S01-RX2-CH5-T003 | 229.42–253.56 | 19 | 57784 | 146.0 | rejected: slope, curvature |
| 149 | S01-RX2-CH6-T003 | 27.55–44.23 | 24 | 54771 | 121.1 | candidate compatible |
| 150 | S01-RX2-CH6-T006 | 41.75–58.07 | 18 | 47357 | 155.7 | candidate compatible |
| 151 | S01-RX2-CH6-T005 | 59.49–73.32 | 17 | 54771 | 21.1 | candidate compatible |
| 152 | S01-RX2-CH6-T001 | 75.45–97.81 | 27 | 62052 | 176.6 | rejected: slope, curvature, bias_bound |
| 153 | S01-RX2-CH6-T002 | 95.68–118.04 | 31 | 60372 | 65.3 | candidate compatible |
| 154 | S01-RX2-CH6-T000 | 165.24–209.24 | 57 | 56413 | 743.4 | rejected: slope, curvature, step, correlation, rms, bias_bound |
| 155 | S01-RX2-CH6-T007 | 209.60–223.79 | 14 | 62814 | 41.5 | candidate compatible |
| 156 | S01-RX2-CH6-T004 | 285.19–299.75 | 23 | 59352 | 116.8 | candidate compatible |
| 157 | S01-RX2-CH7-T002 | 20.15–44.28 | 33 | 54771 | 154.7 | candidate compatible |
| 158 | S01-RX2-CH7-T007 | 46.05–67.69 | 14 | 65398 | 79.2 | candidate compatible |
| 159 | S01-RX2-CH7-T006 | 59.54–74.08 | 17 | 51117 | 297.0 | rejected: slope, curvature |
| 160 | S01-RX2-CH7-T000 | 77.62–118.09 | 48 | 67954 | 242.4 | candidate compatible |
| 161 | S01-RX2-CH7-T005 | 135.47–149.30 | 16 | 100320 | 158.3 | rejected: bias_bound |
| 162 | S01-RX2-CH7-T003 | 165.28–193.68 | 31 | 100168 | 118.2 | candidate compatible |
| 163 | S01-RX2-CH7-T004 | 194.03–222.06 | 21 | 62814 | 82.3 | candidate compatible |
| 164 | S01-RX2-CH7-T008 | 225.96–237.32 | 8 | 66163 | 33.7 | candidate compatible |
| 165 | S01-RX2-CH7-T001 | 271.75–299.09 | 29 | 59326 | 33.6 | candidate compatible |
| 166 | S01-RX2-CH8-T003 | 45.39–58.16 | 11 | 65398 | 155.0 | candidate compatible |
| 167 | S01-RX2-CH8-T001 | 90.09–118.13 | 27 | 67954 | 101.5 | candidate compatible |
| 168 | S01-RX2-CH8-T002 | 137.64–157.51 | 16 | 100320 | 173.5 | rejected: bias_bound |
| 169 | S01-RX2-CH8-T004 | 161.42–178.10 | 10 | 100168 | 133.8 | candidate compatible |
| 170 | S01-RX2-CH8-T000 | 195.49–223.88 | 34 | 57129 | 135.9 | candidate compatible |

All170 tracks have metadata and their top three scored candidate residuals in tracks.json. The first lane's14 tracks have full figures. Candidate scores are research criteria, not identity probabilities. The ledger also records the frozen standard pipeline's associations on exactly these observation IDs.

Current configuration: original GLRT values; drift bound ±1Hz/s, prior σ0.5Hz/s; component constant σ1000Hz and bound3000Hz; matched fitted-c arm. The known-position review does not estimate location accuracy.
