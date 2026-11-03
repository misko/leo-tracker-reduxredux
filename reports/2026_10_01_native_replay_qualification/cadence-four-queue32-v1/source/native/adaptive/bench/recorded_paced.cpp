// Recorded-IQ diagnostic: bounded owned buffers, original monotonic arrivals.
// Compile against the exact detector ABI used to build the linked library.
#include "../runtime/runtime.hpp"
#include "../runtime/detector_projection.hpp"
#include "monotonic_schedule.hpp"
extern "C" {
#include "native_glrt.h"
}
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <sys/resource.h>
using Clock=leo::adaptive::bench::MonotonicClock;
static double ms(Clock::duration d){return std::chrono::duration<double,std::milli>(d).count();}
static double thread_cpu_ms(){rusage r{};
    if(getrusage(RUSAGE_THREAD,&r))throw std::runtime_error("thread CPU measurement failed");
    return 1000.0*(r.ru_utime.tv_sec+r.ru_stime.tv_sec)+.001*(r.ru_utime.tv_usec+r.ru_stime.tv_usec);
}
// Diagnostic owned-buffer experiment. A buffer is returned only after the
// detector's const borrow ends. Unread tails stay zero in prefix mode.
class IqPool {
    mutable std::mutex mutex_;std::vector<std::vector<int16_t>> free_;
    size_t capacity_,allocated_=0;
public:
    explicit IqPool(size_t capacity):capacity_(capacity){free_.reserve(capacity);}
    std::vector<int16_t> take(){std::lock_guard<std::mutex> lock(mutex_);
        if(!free_.empty()){auto v=std::move(free_.back());free_.pop_back();return v;}
        if(allocated_==capacity_)throw std::runtime_error("IQ pool exhausted");
        std::vector<int16_t> v(1200000);++allocated_;return v;
    }
    void recycle(std::vector<int16_t>& v){std::lock_guard<std::mutex> lock(mutex_);
        if(v.size()!=1200000 || free_.size()>=allocated_)throw std::runtime_error("invalid IQ buffer return");
        free_.push_back(std::move(v));
    }
    size_t allocations() const {std::lock_guard<std::mutex> lock(mutex_);return allocated_;}
};
static uint64_t integer(const std::string& s){size_t n=0;auto v=std::stoull(s,&n);
    if(s.empty()||s[0]=='-'||n!=s.size())throw std::runtime_error("invalid integer");
    return v;}
template<class T> static std::vector<T> read(const std::string& p,size_t count){
    std::vector<T> v(count);std::ifstream f(p,std::ios::binary);
    if(!f.read(reinterpret_cast<char*>(v.data()),count*sizeof(T))||f.peek()!=EOF)
        throw std::runtime_error("invalid input: "+p);
    return v;
}
static std::vector<int16_t> read_iq(const std::string& path,bool prefix,std::vector<int16_t> iq={}){
    if(iq.empty())iq.resize(1200000);
    if(iq.size()!=1200000)throw std::runtime_error("invalid IQ buffer size");
    if(!prefix){std::ifstream f(path,std::ios::binary);
        if(!f.read(reinterpret_cast<char*>(iq.data()),2400000)||f.peek()!=EOF)
            throw std::runtime_error("invalid input: "+path);
        return iq;
    }
    // Explicit sparse-probe mode for the pinned 120ms/120ms detector profile.
    // The full saved file remains required; unconsumed samples are zero-filled.
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if(!f||f.tellg()!=2400000)throw std::runtime_error("invalid full dwell file");
    f.seekg(0);
    if(!f.read(reinterpret_cast<char*>(iq.data()),400000))throw std::runtime_error("probe read failed");
    return iq;
}
struct Context {leo_native_glrt* p=nullptr;~Context(){if(p)leo_native_glrt_destroy(p);}};
struct Work {
    uint64_t offset_ns=0;std::string path;leo_native_glrt* detector=nullptr;
    std::vector<int16_t> iq;Clock::time_point due,submitted,started,finished;
    bool accepted=false;int status=0;size_t positive=0;
    double io_ms=0,detector_ms=0,projection_ms=0;std::string candidates,observations,graph;
    double io_cpu_ms=0,detector_cpu_ms=0,projection_cpu_ms=0,service_cpu_ms=0;
    IqPool* pool=nullptr;
    bool project=false,emit_graph=false;leo::adaptive::ProjectionSource authority{};
};
static void analyze(void* opaque,size_t){
    auto& w=*static_cast<Work*>(opaque);w.started=Clock::now();
    const double started_cpu=thread_cpu_ms();
    auto r=std::make_unique<leo_native_glrt_result>();
    w.status=leo_native_glrt_analyze(w.detector,w.iq.data(),w.iq.size()/4,120,120,r.get());
    w.detector_ms=ms(Clock::now()-w.started);
    w.detector_cpu_ms=thread_cpu_ms()-started_cpu;
    if(w.pool)w.pool->recycle(w.iq);else std::vector<int16_t>().swap(w.iq);
    if(w.status){w.finished=Clock::now();throw std::runtime_error("detector failure");}
    std::ostringstream out;out<<std::setprecision(17);bool first=true;
    for(size_t row=0;row<r->row_count;++row)for(int rank=0;rank<r->rows[row].candidate_count;++rank){
        const auto& c=r->rows[row].candidates[rank];
        if(!first)out<<',';
        first=false;
        out<<'['<<r->rows[row].receiver_id<<','<<r->rows[row].probe_index<<','<<rank<<','
           <<c.epoch<<','<<c.acquired_cfo_hz<<','<<c.tracking_cfo_hz<<','<<c.exact_score
           <<','<<c.control_score<<','<<c.margin<<','<<c.glrt_complete<<']';
        w.positive+=c.margin>=.025;
    }
    w.candidates=out.str();
    if(w.project){
        const auto begin=Clock::now();
        const double projection_cpu=thread_cpu_ms();
        try{
            auto observations=leo::adaptive::project_integer_detector_result(w.authority,*r);
            std::ostringstream text,support;text<<std::setprecision(17);support<<std::setprecision(17);
            for(const auto& ranked:observations){const auto& o=ranked.observation;
                text<<o.candidate_id<<'\t'<<o.source_group_id<<'\t'<<o.receiver<<'\t'<<o.channel<<'\t'
                    <<(o.upper_edge?"upper":"lower")<<'\t'<<o.actual_rf_hz<<'\t'<<o.support_start_utc_ns
                    <<'\t'<<o.support_center_utc_ns<<'\t'<<o.support_end_utc_ns<<'\t'<<o.measured_cfo_hz
                    <<'\t'<<o.exact_score<<'\t'<<o.control_score<<'\t'<<o.margin<<'\n';
                if(w.emit_graph)support<<o.candidate_id<<'\t'<<o.support_start_utc_ns<<'\t'
                    <<o.support_center_utc_ns<<'\t'<<o.support_end_utc_ns<<"\t1.0\t0.0\t"
                    <<o.moment2<<'\t'<<o.moment3<<'\n';
            }
            w.observations=text.str();w.graph=support.str();w.projection_ms=ms(Clock::now()-begin);
            w.projection_cpu_ms=thread_cpu_ms()-projection_cpu;
        }catch(...){w.status=-100;w.finished=Clock::now();throw;}
    }
    w.service_cpu_ms=thread_cpu_ms()-started_cpu;w.finished=Clock::now();
}
int main(int argc,char** argv){try{
    if(argc==2&&std::string(argv[1])=="--clock-now"){
        std::cout<<Clock::now().time_since_epoch().count()<<'\n';return 0;
    }
    if(argc<3)throw std::runtime_error("usage: leo-recorded-paced MANIFEST QUEUE_CAPACITY [--probe-prefix] [--authority FILE --observations FILE]");
    bool prefix=false,reuse=false;std::string authority_path,observations_path,graph_path,session;
    bool scheduled=false;uint64_t start_ns=0;
    for(int i=3;i<argc;++i){const std::string flag=argv[i];
        if(flag=="--probe-prefix"&&!prefix)prefix=true;
        else if(flag=="--reuse-iq"&&!reuse)reuse=true;
        else if(flag=="--start-monotonic-ns"&&!scheduled&&i+1<argc){
            scheduled=true;start_ns=integer(argv[++i]);
        }
        else if(flag=="--authority"&&authority_path.empty()&&i+1<argc)authority_path=argv[++i];
        else if(flag=="--observations"&&observations_path.empty()&&i+1<argc)observations_path=argv[++i];
        else if(flag=="--graph"&&graph_path.empty()&&i+1<argc)graph_path=argv[++i];
        else if(flag=="--session"&&session.empty()&&i+1<argc)session=argv[++i];
        else throw std::runtime_error("unknown/duplicate input mode");
    }
    if(authority_path.empty()!=observations_path.empty())throw std::runtime_error("projection requires authority and output");
    if(graph_path.empty()!=session.empty()||(!graph_path.empty()&&authority_path.empty())||
       session.find_first_of("\t\r\n ")!=std::string::npos||(!graph_path.empty()&&graph_path==observations_path))
        throw std::runtime_error("graph requires projection and a valid session identity");
    // Measured concurrent DS9 bursts exceed sixteen queued dwells. Keep the
    // diagnostic explicitly bounded; capacity+2 also bounds owned IQ buffers.
    const auto capacity=integer(argv[2]);if(!capacity||capacity>32)throw std::runtime_error("queue capacity");
    std::ifstream manifest(argv[1]);if(!manifest)throw std::runtime_error("missing manifest");
    std::vector<Work> jobs;std::map<std::string,std::unique_ptr<Context>> contexts;
    std::string line;
    while(std::getline(manifest,line)){
        std::istringstream in(line);std::vector<std::string> f;std::string value;
        while(std::getline(in,value,'\t'))f.push_back(value);
        if(f.size()!=5||jobs.size()>=10000||integer(f[0])!=jobs.size())throw std::runtime_error("invalid manifest");
        Work w;w.offset_ns=integer(f[1]);w.path=f[4];
        if(w.offset_ns>1200000000000ULL||(!jobs.empty()&&w.offset_ns<=jobs.back().offset_ns))
            throw std::runtime_error("invalid arrival schedule");
        const auto key=f[2]+"\n"+f[3];auto found=contexts.find(key);
        if(found==contexts.end()){
            if(contexts.size()>=2)throw std::runtime_error("context capacity");
            auto c=std::make_unique<Context>();auto e=read<leo_native_glrt_complex>(f[2],3333);
            auto control=read<leo_native_glrt_complex>(f[3],3333);
            if(leo_native_glrt_create(&c->p,2500000,e.data(),control.data(),3333))throw std::runtime_error("context create");
            found=contexts.emplace(key,std::move(c)).first;
        }
        w.detector=found->second->p;jobs.push_back(std::move(w));
    }
    if(jobs.empty()||jobs.front().offset_ns!=0)throw std::runtime_error("empty/nonzero-origin schedule");
    if(!authority_path.empty()){
        std::ifstream source(authority_path);if(!source)throw std::runtime_error("missing projection authority");
        size_t index=0;uint64_t first=0;
        while(std::getline(source,line)){
            if(index>=jobs.size())throw std::runtime_error("extra projection authority");
            std::istringstream in(line);auto& s=jobs[index].authority;unsigned upper,qualified;std::string extra;
            if(!(in>>s.rate>>s.anchor_counter>>s.anchor_utc_ns>>s.generation>>s.visit>>s.window_counter
                 >>s.probe_index>>s.receiver>>s.channel>>upper>>s.actual_rf_hz>>s.utc_bracket_width_ns
                 >>s.input_digest>>s.analysis_digest>>qualified)||(in>>extra)||upper>1||qualified!=1||
                 s.visit!=index||s.rate!=2500000||s.probe_index!=0||s.receiver!=0)
                throw std::runtime_error("invalid projection authority");
            s.upper_edge=upper;s.continuity_qualified=true;
            (void)leo::adaptive::classify_projection_input(s,leo::adaptive::FractionalCandidate{});
            if(index==0)first=s.window_counter;
            if(s.window_counter<first||(s.window_counter-first)>3000000000ULL||
               (s.window_counter-first)*400!=jobs[index].offset_ns)
                throw std::runtime_error("projection authority differs from arrival schedule");
            if(index&& (s.input_digest!=jobs[0].authority.input_digest||s.analysis_digest!=jobs[0].authority.analysis_digest||
               s.anchor_utc_ns!=jobs[0].authority.anchor_utc_ns||s.anchor_counter!=jobs[0].authority.anchor_counter||
               s.generation!=jobs[0].authority.generation))throw std::runtime_error("mixed capture authority");
            jobs[index].project=true;jobs[index].emit_graph=!graph_path.empty();++index;
        }
        if(!source.eof()||index!=jobs.size())throw std::runtime_error("incomplete projection authority");
        if(std::ifstream(observations_path))throw std::runtime_error("projection output already exists");
        if(!graph_path.empty()&&std::ifstream(graph_path))throw std::runtime_error("graph output already exists");
    }
    // Pool outlives executor destruction/drain, including exception paths.
    IqPool pool(capacity+2);leo::adaptive::Executor executor(1,capacity);
    const auto ready=Clock::now();
    const auto origin=scheduled?leo::adaptive::bench::scheduled_origin(start_ns,ready):
        ready+std::chrono::milliseconds(100);
    std::cerr<<"{\"kind\":\"replay_clock\",\"clock\":\"CLOCK_MONOTONIC\",\"origin_ns\":"
             <<origin.time_since_epoch().count()<<",\"ready_ns\":"<<ready.time_since_epoch().count()
             <<",\"external_origin\":"<<(scheduled?"true":"false")<<"}\n";
    for(size_t i=0;i<jobs.size();++i){auto& w=jobs[i];w.due=origin+std::chrono::nanoseconds(w.offset_ns);
        std::this_thread::sleep_until(w.due);const auto begin=Clock::now();
        const double io_cpu=thread_cpu_ms();w.pool=reuse?&pool:nullptr;
        w.iq=read_iq(w.path,prefix,reuse?pool.take():std::vector<int16_t>{});
        w.submitted=Clock::now();w.io_ms=ms(w.submitted-begin);w.io_cpu_ms=thread_cpu_ms()-io_cpu;
        w.accepted=executor.submit({i,analyze,&w});
        if(!w.accepted){if(w.pool)pool.recycle(w.iq);else std::vector<int16_t>().swap(w.iq);}
    }
    executor.drain();const auto stats=executor.stats();std::cout<<std::setprecision(17);
    if(!observations_path.empty()){
        std::ofstream output(observations_path);
        output<<"candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin\n";
        for(const auto& w:jobs)if(w.accepted&&w.status==0)output<<w.observations;
        output.close();if(!output)throw std::runtime_error("projection output failed");
    }
    if(!graph_path.empty()){
        std::ofstream output(graph_path);const auto& authority=jobs[0].authority;
        output<<"META\t"<<session<<'\t'<<authority.input_digest<<'\t'<<authority.anchor_utc_ns<<'\n'
              <<"candidate_id\tstart_utc_ns\tcenter_utc_ns\tend_utc_ns\tm0\tm1\tm2\tm3\n";
        for(const auto& w:jobs)if(w.accepted&&w.status==0)output<<w.graph;
        output.close();if(!output)throw std::runtime_error("graph output failed");
    }
    for(size_t i=0;i<jobs.size();++i){const auto& w=jobs[i];
        std::cout<<"{\"sequence\":"<<i<<",\"accepted\":"<<(w.accepted?"true":"false")
                 <<",\"io_ms\":"<<w.io_ms<<",\"producer_late_ms\":"<<ms(w.submitted-w.due);
        std::cout<<",\"io_cpu_ms\":"<<w.io_cpu_ms;
        if(w.accepted)std::cout<<",\"queue_ms\":"<<ms(w.started-w.submitted)<<",\"service_ms\":"<<ms(w.finished-w.started)
          <<",\"due_to_finish_ms\":"<<ms(w.finished-w.due)<<",\"status\":"<<w.status<<",\"positive\":"<<w.positive
          <<",\"detector_ms\":"<<w.detector_ms<<",\"projection_ms\":"<<w.projection_ms
          <<",\"detector_cpu_ms\":"<<w.detector_cpu_ms<<",\"projection_cpu_ms\":"<<w.projection_cpu_ms
          <<",\"service_cpu_ms\":"<<w.service_cpu_ms
          <<",\"candidates\":["<<w.candidates<<']';
        std::cout<<"}\n";
    }
    rusage usage{};getrusage(RUSAGE_SELF,&usage);
    std::cout<<"{\"kind\":\"summary\",\"arrivals\":"<<jobs.size()<<",\"completed\":"<<stats.completed
      <<",\"failed\":"<<stats.failed<<",\"rejected\":"<<stats.rejected<<",\"queue_capacity\":"<<capacity<<",\"queue_high_water\":"<<stats.high_water
      <<",\"max_rss_kib\":"<<usage.ru_maxrss<<",\"probe_prefix_only\":"<<(prefix?"true":"false")
      <<",\"iq_reuse\":"<<(reuse?"true":"false")<<",\"iq_buffer_allocations\":"<<(reuse?pool.allocations():jobs.size())
      <<",\"wall_ms\":"<<ms(Clock::now()-origin)<<"}\n";
    executor.rethrow_first_failure();return stats.rejected?3:0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
