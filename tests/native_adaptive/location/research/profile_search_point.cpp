#define LEO_RESEARCH_CAPPED_SEARCH
#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main

int main(int argc,char** argv) {
    if(argc!=2) return 2;
    Fixture fixture;if(!load_fixture(argv[1],&fixture)) return 3;
    ScoreEngine scorer(fixture,2);scorer.objective_only=true;
    const auto site=make_site(38.5816,-121.4944,-150,-150);
    std::vector<leo_track_score> tracks;
    leo_point_score point{};
    if(!scorer.valid() || !score_site(&scorer,fixture,site,&tracks,&point)) return 4;
    std::printf("{\"east_km\":-150,\"north_km\":-150,\"score_hz\":%.17g}\n",point.residual_rmse_hz);
}
