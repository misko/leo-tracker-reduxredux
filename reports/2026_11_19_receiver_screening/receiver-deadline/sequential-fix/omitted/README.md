# Disjoint offered squares withheld early and published at fallback

Both anchors rejected early release with the 25 km offer shifted 30 km east. Both complete compact fallbacks then published false fixes. The original and shifted squares have a 5 km gap, verified before fitting. After sealing the results, scoring placed the survey about 12.296 km outside each shifted square. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)

| Recording | Early decision in both arms | Constrained 255 s geographic error, `c = 0` / fitted `c` (km) | Complete fallback error, `c = 0` / fitted `c` (km) |
| --- | --- | ---: | ---: |
| DS26-0237 | Withheld | 12.711 / 12.698 | 12.545 / 12.485 |
| DS29-0082 | Withheld | 12.537 / 12.483 | 12.497 / 12.543 |

Every 255 s fit reached a tile face exactly. The nominal 95% radii ranged from 4.749 to 6.904 km, above the 2 km gate threshold. All six capped services returned fits with both coefficient arms and zero swap. The final policy has two false publications because it takes the actual full result when the early gate rejects. These are offered-region controls from one physical site. [Release evidence](release-decisions.json) · [Per-arm scores](scores.csv) · [Service timings](position-stages.csv) · [Position figures](charts/index.html) · [Score lock](score-lock.json)
