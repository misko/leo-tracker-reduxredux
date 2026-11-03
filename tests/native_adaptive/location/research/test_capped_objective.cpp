#define LEO_RESEARCH_CAPPED_SEARCH
#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main
#include <cassert>

int main(int argc,char** argv) {
    assert(argc==2);
    Fixture fixture;assert(load_fixture(argv[1],&fixture));
    ScoreEngine full(fixture,2),objective(fixture,2);objective.objective_only=true;
    assert(!full.objective_only);
    std::vector<leo_track_score> a,b;
    for(const auto& site:fixture.sites) {
        leo_point_score pa{},pb{};
        assert(score_site(&full,fixture,site,&a,&pa));
        assert(score_site(&objective,fixture,site,&b,&pb));
        assert(pa.weighted_mse_hz2==pb.weighted_mse_hz2);
        assert(pa.residual_rmse_hz==pb.residual_rmse_hz);
        for(size_t i=0;i<a.size();++i) if(a[i].heldout_rms_hz<800) {
            assert(a[i].candidate_id==b[i].candidate_id);
            assert(a[i].tau_s==b[i].tau_s);
            assert(a[i].heldout_rms_hz==b[i].heldout_rms_hz);
        }
        // Full association scoring must clear objective sentinels, including
        // when an engine has already visited objective-only sites.
        objective.objective_only=false;
        leo_point_score restored{};
        assert(score_site(&objective,fixture,site,&b,&restored));
        assert(pa.matched_track_count==restored.matched_track_count);
        assert(pa.weighted_mse_hz2==restored.weighted_mse_hz2);
        for(size_t i=0;i<a.size();++i) {
            assert(a[i].matched==b[i].matched);
            assert(a[i].candidate_id==b[i].candidate_id);
            assert(a[i].tau_s==b[i].tau_s);
            assert(a[i].heldout_rms_hz==b[i].heldout_rms_hz);
            assert(a[i].training_rms_hz==b[i].training_rms_hz);
            assert(a[i].frequency_offset_hz==b[i].frequency_offset_hz);
        }
        objective.objective_only=true;
    }
    std::puts("capped objective equals full loss; uncapped winners preserved");
}
