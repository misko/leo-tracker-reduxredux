#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main
#include <string>

int main(int argc,char** argv) {
    if(argc!=6 && argc!=8) return 2;
    Fixture fixture;
    if(!load_fixture(argv[1],&fixture)) return 3;
    leo_location_site site{};
    if(argc==6) site=make_site(std::stod(argv[2]),std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5]));
    else for(unsigned i=0;i<3;++i) {
        site.ecef_km[i]=std::stod(argv[2+i]);site.up[i]=std::stod(argv[5+i]);
    }
    std::fprintf(stderr,"{\"ecef\":[%.17g,%.17g,%.17g],\"up\":[%.17g,%.17g,%.17g]}\n",
        site.ecef_km[0],site.ecef_km[1],site.ecef_km[2],site.up[0],site.up[1],site.up[2]);
    fixture.sites={site};
    return run_score(fixture,2);
}
