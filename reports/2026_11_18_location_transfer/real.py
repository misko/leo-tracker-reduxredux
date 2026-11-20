"""Score unchanged anonymous DS26 tracks through deliberately moved search tiles."""

import json
from models import CONFIG, bench, cold, held_out_contest, identity, latlon, run_models, save, tile


def main():
    original = bench.PANEL["search_center_latlon"]
    rows = []
    for case in CONFIG["real_cases"]:
        source = cold.GRAPHS / f"{case}.json"
        graph = json.loads(source.read_bytes())
        digest = identity(source)
        receipt = cold.read(cold.GRAPHS / f"{case}-receipt.json")
        assert digest == receipt["output_sha256"].removeprefix("sha256:")
        for name, offset in CONFIG["real_tile_offsets_east_north_km"].items():
            center = latlon(original, offset)
            with tile(center):
                bank, sky = cold.build_bank(case, graph["metadata"], check_approximation=False)
            entry = dict(case=case, tile=name, center=center, graph_sha256=digest,
                         orbit=sky["snapshot"], regional_candidates=sky["regional"],
                         methods=run_models(graph, bank, center, refine=True))
            if name in ("original", "east150", "north150"):
                entry["time_holdout"] = held_out_contest(graph, bank, center)
            rows.append(entry)
        print(case, flush=True)
    save("real-predictions.json", rows)


if __name__ == "__main__":
    main()
