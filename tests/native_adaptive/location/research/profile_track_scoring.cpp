// Research-only profile: reuse the explicit LOC1 reader, not application storage.
#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main
#include <chrono>

int main(int argc, char** argv) {
    if(argc!=2) return 2;
    Fixture fixture;
    if(!load_fixture(argv[1],&fixture)) return 3;
    ScoreEngine engine(fixture,1);
    if(!engine.valid()) return 4;
    auto config=leo_score_default_config();
    std::vector<leo_track_score> scores(fixture.tracks.size());
    leo_track_scores_clear(scores.data(),static_cast<uint32_t>(scores.size()));
    std::printf("{\"site_index\":0,\"workers\":1,\"satellites\":%u,\"tracks\":[",fixture.snapshot.satellite_count);
    for(size_t i=0;i<fixture.tracks.size();++i) {
        leo_score_stats stats{};
        auto start=std::chrono::steady_clock::now();
        auto status=leo_score_partition(engine.contexts[0],&fixture.snapshot,
            &fixture.tracks[i],1,&fixture.sites[0],&config,0,
            fixture.snapshot.satellite_count,&scores[i],&stats);
        double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        if(status!=LEO_LOCATION_OK) return 5;
        auto& s=scores[i];
        std::printf("%s{\"index\":%zu,\"observations\":%u,\"wall_s\":%.17g,"
            "\"evaluated\":%llu,\"rejected\":%llu,\"score\":{\"candidate_id\":%d,"
            "\"tau_s\":%d,\"held_hz\":%.17g,\"fit_hz\":%.17g,\"offset_hz\":%.17g}}",
            i?",":"",i,fixture.tracks[i].observation_count,elapsed,
            static_cast<unsigned long long>(stats.evaluated_satellite_tracks),
            static_cast<unsigned long long>(stats.rejected_satellite_tracks),
            s.candidate_id,s.tau_s,s.heldout_rms_hz,s.training_rms_hz,s.frequency_offset_hz);
    }
    leo_point_score point{};
    if(leo_point_score_finish(fixture.tracks.data(),static_cast<uint32_t>(scores.size()),
        scores.data(),&config,&point)!=LEO_LOCATION_OK) return 6;
    std::printf("],\"score_hz\":%.17g,\"matched_tracks\":%u}\n",point.residual_rmse_hz,point.matched_track_count);
    return 0;
}
