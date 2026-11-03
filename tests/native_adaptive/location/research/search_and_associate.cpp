// Research composition of existing search and full scoring; output schemas
// remain unchanged. The additional checkpoint is exclusive-create.
#define main location_replay_main
#include "../../../../native/adaptive/location/location_cli.cpp"
#undef main

int main(int argc,char** argv) {
    if(argc!=7)return 2;
    double value[3];
    for(unsigned i=0;i<3;++i) {
        char* end=nullptr;value[i]=std::strtod(argv[i+2],&end);
        if(end==argv[i+2] || *end || !std::isfinite(value[i]))return 2;
    }
    if(value[0]<-90 || value[0]>90 || value[1]<-180 || value[1]>180 ||
       value[2]<=0 || value[2]>20000)return 2;
    unsigned workers=1;
    if(!parse_workers(argv[5],&workers))return 2;
    Fixture fixture;if(!load_fixture(argv[1],&fixture))return 2;
    std::unique_ptr<FILE,FileCloser> output(std::fopen(argv[6],"wx"));
    if(!output)return 2;
    return run_search(fixture,value[0],value[1],value[2],workers,output.get());
}
