#define LEO_RESEARCH_CAPPED_SEARCH
#define LEO_RESEARCH_SCORE_WARM_START
#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main

int main(int argc,char** argv) {
    if(argc!=3)return 2;
    Fixture fixture;if(!load_fixture(argv[1],&fixture))return 3;
    std::unique_ptr<FILE,FileCloser> input(std::fopen(argv[2],"r"));if(!input)return 2;
    ScoreEngine scorer(fixture,2);scorer.objective_only=true;
    if(!scorer.valid())return 4;
    std::vector<leo_track_score> tracks;double east,north;unsigned count=0;
    std::puts("[");
    while(std::fscanf(input.get(),"%lf %lf",&east,&north)==2) {
        if(++count>64 || !std::isfinite(east) || !std::isfinite(north))return 2;
        auto site=make_site(38.5816,-121.4944,east,north);leo_point_score point{};
        if(!score_site(&scorer,fixture,site,&tracks,&point))return 4;
        std::printf("%s[%.17g,%.17g,%.17g]",count==1?"":",",east,north,point.residual_rmse_hz);
    }
    if(!std::feof(input.get()) || !count)return 2;
    std::puts("]");return 0;
}
