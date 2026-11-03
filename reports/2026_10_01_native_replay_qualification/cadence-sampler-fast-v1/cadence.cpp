// Bounded Linux recorded-load controller. No IQ, radio, or scientific logic.
#include "monotonic_schedule.hpp"
#include "process_stat.hpp"
#include <algorithm>
#include <cerrno>
#include <csignal>
#include <deque>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>
using Clock=leo::adaptive::bench::MonotonicClock;
static volatile sig_atomic_t interrupted=0;
static void interrupt(int){interrupted=1;}
static uint64_t number(const std::string& s){
    if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos)
        throw std::runtime_error("invalid integer");
    return std::stoull(s);
}
struct Job {std::string output;std::vector<std::string> args;};
struct Scan {Job detector,downstream;};
struct Child {pid_t pid;size_t scan;bool detector;Clock::time_point started;};
static uint64_t sampled_rss(const std::vector<Child>& active){
    std::set<pid_t> groups;for(const auto& c:active)groups.insert(c.pid);
    DIR* directory=opendir("/proc");if(!directory)throw std::runtime_error("missing proc memory accounting");
    uint64_t pages=0;
    while(auto* entry=readdir(directory)){
        const std::string name=entry->d_name;
        if(name.empty()||name.find_first_not_of("0123456789")!=std::string::npos)continue;
        std::ifstream stat("/proc/"+name+"/stat");std::string line;
        if(!std::getline(stat,line))continue; // A process may exit during sampling.
        int group=0;uint64_t rss=0;
        if(!leo::adaptive::bench::process_stat(line.c_str(),group,rss))continue;
        if(std::stol(name)==getpid()||groups.count(group))pages+=rss;
    }
    closedir(directory);const auto page_size=sysconf(_SC_PAGESIZE);
    if(page_size<=0)throw std::runtime_error("unknown page size");
    return pages*static_cast<uint64_t>(page_size)/1024;
}
static std::vector<Scan> read_plan(const char* path){
    std::ifstream input(path);if(!input)throw std::runtime_error("missing plan");
    std::vector<Scan> scans;std::set<std::string> outputs;std::string line;
    while(std::getline(input,line)){
        if(line.find('\0')!=std::string::npos)throw std::runtime_error("NUL in plan");
        std::vector<std::string> fields;std::istringstream row(line);std::string field;
        while(std::getline(row,field,'\t'))fields.push_back(field);
        if(fields.size()<4||fields.size()>64||fields.back().empty()||line.back()=='\t')
            throw std::runtime_error("invalid plan row");
        for(const auto& value:fields)if(value.empty())throw std::runtime_error("empty plan field");
        const auto i=number(fields[1]);
        if(i>=4||i>scans.size())throw std::runtime_error("nonsequential scan");
        if(i==scans.size())scans.emplace_back();
        Job* job=fields[0]=="detector"?&scans[i].detector:
                 fields[0]=="downstream"?&scans[i].downstream:nullptr;
        if(!job||!job->args.empty()||!outputs.insert(fields[2]).second)
            throw std::runtime_error("duplicate or invalid job");
        job->output=fields[2];job->args.assign(fields.begin()+3,fields.end());
        if(job->args[0][0]!='/')throw std::runtime_error("executable must be absolute");
        for(const auto& arg:job->args)if(arg=="--start-monotonic-ns")
            throw std::runtime_error("controller owns origin");
        for(const auto* suffix:{".stdout",".stderr"}){
            if(access((job->output+suffix).c_str(),F_OK)==0)
                throw std::runtime_error("output already exists");
        }
    }
    if(!input.eof()||scans.empty())throw std::runtime_error("empty or unreadable plan");
    for(const auto& s:scans)if(s.detector.args.empty()||s.downstream.args.empty())
        throw std::runtime_error("missing scan job");
    return scans;
}
static Child launch(const Job& job,size_t index,bool detector,Clock::time_point origin){
    auto args=job.args;
    if(detector){args.push_back("--start-monotonic-ns");args.push_back(std::to_string(origin.time_since_epoch().count()));}
    std::vector<char*> argv;for(auto& a:args)argv.push_back(a.data());argv.push_back(nullptr);
    const int out=open((job.output+".stdout").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(out<0)throw std::runtime_error("cannot create stdout");
    const int err=open((job.output+".stderr").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(err<0){close(out);throw std::runtime_error("cannot create stderr");}
    const auto started=Clock::now();const pid_t pid=fork();
    if(pid==0){
        if(setpgid(0,0)||dup2(out,STDOUT_FILENO)<0||dup2(err,STDERR_FILENO)<0)_exit(126);
        close(out);close(err);
        // Scientific downstream runs below the detector in scheduler priority.
        if(!detector){errno=0;if(nice(19)==-1&&errno)_exit(126);}
        execv(argv[0],argv.data());_exit(127);
    }
    close(out);close(err);if(pid<0)throw std::runtime_error("fork failed");
    // Child also sets its group before exec; EACCES means it has already exec'd.
    if(setpgid(pid,pid)&&errno!=EACCES&&errno!=ESRCH){kill(pid,SIGKILL);waitpid(pid,nullptr,0);throw std::runtime_error("process group failed");}
    std::cout<<"{\"kind\":\"launch\",\"scan\":"<<index<<",\"detector\":"<<(detector?"true":"false")
             <<",\"pid\":"<<pid<<",\"monotonic_ns\":"<<started.time_since_epoch().count()
             <<",\"scan_origin_ns\":"<<origin.time_since_epoch().count()<<"}\n"<<std::flush;
    return {pid,index,detector,started};
}
static void terminate(std::vector<Child>& children){
    for(const auto& c:children)kill(-c.pid,SIGTERM);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    for(const auto& c:children){kill(-c.pid,SIGKILL);while(waitpid(c.pid,nullptr,0)<0&&errno==EINTR){}}
    children.clear();
}
int main(int argc,char** argv){
    std::vector<Child> active;
    try{
        if(argc==3&&std::string(argv[1])=="--sample-cost"){
            const auto count=number(argv[2]);
            if(!count||count>1000)throw std::runtime_error("invalid sampler repetition count");
            const auto begin=Clock::now();uint64_t peak=0;
            for(uint64_t i=0;i<count;++i)peak=std::max(peak,sampled_rss(active));
            std::cout<<"{\"samples\":"<<count<<",\"wall_ns\":"<<(Clock::now()-begin).count()
                     <<",\"peak_rss_kib\":"<<peak<<"}\n";return 0;
        }
        if(argc!=4)throw std::runtime_error("usage: leo-cadence PLAN PERIOD_MS INITIALIZATION_LEAD_MS");
        const auto scans=read_plan(argv[1]);const auto period_ms=number(argv[2]),lead_ms=number(argv[3]);
        if(!period_ms||period_ms>300000||!lead_ms||lead_ms>=period_ms||lead_ms>60000)
            throw std::runtime_error("invalid cadence bounds");
        const auto period=std::chrono::milliseconds(period_ms),lead=std::chrono::milliseconds(lead_ms);
        const auto origin=Clock::now()+lead+std::chrono::milliseconds(100);
        const auto deadline=origin+period*(scans.size()+2);
        std::signal(SIGTERM,interrupt);std::signal(SIGINT,interrupt);
        std::deque<size_t> pending;size_t next=0,completed=0,detected=0,peak_pending=0,peak_detectors=0;
        auto memory_due=Clock::now();uint64_t peak_rss=0;
        active.reserve(3);
        std::cout<<"{\"kind\":\"cadence\",\"origin_ns\":"<<origin.time_since_epoch().count()
                 <<",\"period_ns\":"<<std::chrono::duration_cast<std::chrono::nanoseconds>(period).count()
                 <<",\"scans\":"<<scans.size()<<",\"pending_capacity\":1,\"detector_capacity\":2}\n"<<std::flush;
        while(completed<scans.size()){
            if(interrupted)throw std::runtime_error("interrupted");
            if(Clock::now()>deadline)throw std::runtime_error("cadence watchdog expired");
            for(size_t i=0;i<active.size();){
                int status=0;const auto child=active[i];const auto got=waitpid(child.pid,&status,WNOHANG);
                if(got<0){if(errno==EINTR)continue;throw std::runtime_error("waitpid failed");}
                if(!got){++i;continue;}
                const int code=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
                std::cout<<"{\"kind\":\"finish\",\"scan\":"<<child.scan<<",\"detector\":"<<(child.detector?"true":"false")
                         <<",\"monotonic_ns\":"<<Clock::now().time_since_epoch().count()<<",\"exit_code\":"<<code<<"}\n"<<std::flush;
                if(code){kill(-child.pid,SIGKILL);active.erase(active.begin()+i);throw std::runtime_error("child failed");}
                active.erase(active.begin()+i);
                if(child.detector){
                    if(child.scan!=detected++)throw std::runtime_error("out-of-order detector completion");
                    if(pending.size()==1)throw std::runtime_error("downstream backlog capacity exceeded");
                    pending.push_back(child.scan);peak_pending=std::max(peak_pending,pending.size());
                }else ++completed;
            }
            const auto detectors=std::count_if(active.begin(),active.end(),[](const Child& c){return c.detector;});
            if(!pending.empty()&&static_cast<size_t>(detectors)==active.size()){
                const auto i=pending.front();pending.pop_front();
                active.push_back(launch(scans[i].downstream,i,false,origin+period*i));
            }
            if(next<scans.size()&&Clock::now()>=origin+period*next-lead){
                if(detectors>=2)throw std::runtime_error("detector lifecycle capacity exceeded");
                if(Clock::now()>=origin+period*next)throw std::runtime_error("missed detector launch deadline");
                active.push_back(launch(scans[next].detector,next,true,origin+period*next));++next;
                peak_detectors=std::max(peak_detectors,static_cast<size_t>(detectors+1));
            }
            if(Clock::now()>=memory_due){
                const auto rss=sampled_rss(active);peak_rss=std::max(peak_rss,rss);
                std::cout<<"{\"kind\":\"memory\",\"monotonic_ns\":"<<Clock::now().time_since_epoch().count()
                         <<",\"process_tree_rss_kib\":"<<rss<<",\"pending_scans\":"<<pending.size()<<"}\n"<<std::flush;
                memory_due=Clock::now()+std::chrono::seconds(1);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        std::cout<<"{\"kind\":\"summary\",\"completed_scans\":"<<completed<<",\"pending_high_water\":"<<peak_pending
                 <<",\"detector_process_high_water\":"<<peak_detectors<<",\"sampled_peak_process_tree_rss_kib\":"<<peak_rss<<",\"success\":true}\n";
        return 0;
    }catch(const std::exception& error){terminate(active);std::cerr<<error.what()<<'\n';return 2;}
}
