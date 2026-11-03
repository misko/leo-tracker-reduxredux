// Existing-IQ arrival simulator. Input preloading is excluded from pacing.
// The producer follows an independent monotonic schedule and never waits for
// detector completion. Rejected work remains visible in the result stream.
#include "../runtime/runtime.hpp"
extern "C" {
#include "../detector/native_glrt.h"
}
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using Clock=std::chrono::steady_clock;
static double ms(Clock::duration d) {return std::chrono::duration<double,std::milli>(d).count();}
template<class T> static std::vector<T> read(const std::string& path,size_t count) {
    std::vector<T> data(count);std::ifstream file(path,std::ios::binary);
    if(!file.read(reinterpret_cast<char*>(data.data()),count*sizeof(T)) ||
       file.peek()!=std::char_traits<char>::eof()) throw std::runtime_error("bad fixture: "+path);
    return data;
}
struct Input {uint32_t rate,dwell,stride;std::vector<int16_t> iq;};
struct Work {
    leo_native_glrt* detector=nullptr;const Input* input=nullptr;
    Clock::time_point due,submitted,started,finished;
    bool accepted=false;int status=0,candidates=0,positive=0,fractional=0;
};
static void analyze(void* opaque,size_t) {
    auto& w=*static_cast<Work*>(opaque);w.started=Clock::now();
    auto result=std::make_unique<leo_native_glrt_result>();
    w.status=leo_native_glrt_analyze(w.detector,w.input->iq.data(),w.input->iq.size()/4,
        w.input->dwell,w.input->stride,result.get());
    w.finished=Clock::now();if(w.status) throw std::runtime_error("detector failed");
    for(size_t r=0;r<result->row_count;++r) for(int i=0;i<result->rows[r].candidate_count;++i) {
        const auto& c=result->rows[r].candidates[i];++w.candidates;
        w.positive+=c.margin>=.025;w.fractional+=c.fractional_epoch_status==1;
    }
}
int main(int argc,char**argv) {
    try {
        if(argc!=6) throw std::invalid_argument("usage: leo-paced MANIFEST PERIOD_MS ROUNDS QUEUE_CAPACITY FRACTIONAL_0_OR_1");
        auto integer=[](const char* p) {std::string s(p);size_t n;auto v=std::stoul(s,&n);
            if(n!=s.size()||s.empty()||s[0]=='-'||v>UINT32_MAX)
                throw std::invalid_argument("invalid integer");
            return v;};
        const auto period=integer(argv[2]),rounds=integer(argv[3]),capacity=integer(argv[4]),fractional=integer(argv[5]);
        if(!period||period>1000||!rounds||rounds>100||!capacity||capacity>64||fractional>1)
            throw std::invalid_argument("invalid limits");
        std::ifstream manifest(argv[1]);if(!manifest) throw std::runtime_error("missing manifest");
        std::vector<Input> inputs;std::string line,exact_path,control_path;size_t bytes=0;
        while(std::getline(manifest,line)) {
            std::vector<std::string> fields;std::istringstream stream(line);std::string field;
            while(std::getline(stream,field,'\t')) fields.push_back(field);
            if(fields.size()!=8||inputs.size()==32) throw std::runtime_error("invalid manifest");
            if(integer(fields[0].c_str())!=inputs.size()) throw std::runtime_error("sequence mismatch");
            Input input{};input.rate=integer(fields[1].c_str());input.dwell=integer(fields[2].c_str());input.stride=integer(fields[3].c_str());
            if(inputs.empty()) {exact_path=fields[4];control_path=fields[5];}
            else if(exact_path!=fields[4]||control_path!=fields[5]||input.rate!=inputs[0].rate)
                throw std::runtime_error("mixed detector context");
            size_t times=0,rows=0;
            if(leo_native_glrt_layout(input.rate,input.dwell,input.stride,&times,&rows)) throw std::runtime_error("invalid layout");
            bytes+=times*8;if(bytes>128*1024*1024) throw std::runtime_error("preload bound exceeded");
            input.iq=read<int16_t>(fields[6],times*4);inputs.push_back(std::move(input));
        }
        if(inputs.empty()) throw std::runtime_error("empty manifest");
        const size_t frame=(inputs[0].rate+375)/750;
        auto exact=read<leo_native_glrt_complex>(exact_path,frame),control=read<leo_native_glrt_complex>(control_path,frame);
        leo_native_glrt* raw=nullptr;
        if(leo_native_glrt_create_with_mode(&raw,inputs[0].rate,exact.data(),control.data(),frame,fractional))
            throw std::runtime_error("detector create failed");
        std::unique_ptr<leo_native_glrt,decltype(&leo_native_glrt_destroy)> detector(raw,leo_native_glrt_destroy);
        std::vector<Work> jobs(inputs.size()*rounds);leo::adaptive::Executor executor(1,capacity);
        const auto origin=Clock::now()+std::chrono::milliseconds(100);
        for(size_t i=0;i<jobs.size();++i) {
            auto& w=jobs[i];w.detector=raw;w.input=&inputs[i%inputs.size()];
            w.due=origin+std::chrono::milliseconds(i*period);
            std::this_thread::sleep_until(w.due);w.submitted=Clock::now();
            w.accepted=executor.submit({i,analyze,&w});
        }
        executor.drain();const auto stats=executor.stats();
        std::cout<<std::setprecision(17);
        for(size_t i=0;i<jobs.size();++i) {const auto& w=jobs[i];
            std::cout<<"{\"kind\":\"arrival\",\"sequence\":"<<i<<",\"input_index\":"<<i%inputs.size()
                <<",\"accepted\":"<<(w.accepted?"true":"false")<<",\"producer_late_ms\":"<<ms(w.submitted-w.due);
            if(w.accepted) std::cout<<",\"queue_ms\":"<<ms(w.started-w.submitted)<<",\"service_ms\":"<<ms(w.finished-w.started)
                <<",\"due_to_finish_ms\":"<<ms(w.finished-w.due)<<",\"status\":"<<w.status
                <<",\"candidates\":"<<w.candidates<<",\"positive\":"<<w.positive<<",\"fractional_complete\":"<<w.fractional;
            std::cout<<"}\n";
        }
        std::cout<<"{\"kind\":\"summary\",\"period_ms\":"<<period<<",\"preloaded_bytes\":"<<bytes
            <<",\"arrivals\":"<<jobs.size()<<",\"completed\":"<<stats.completed<<",\"failed\":"<<stats.failed
            <<",\"rejected\":"<<stats.rejected<<",\"queue_high_water\":"<<stats.high_water<<"}\n";
        executor.rethrow_first_failure();return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
}
