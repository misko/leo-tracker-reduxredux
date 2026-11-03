#include "runtime.hpp"
#include <algorithm>
#include <cmath>
#include <cfenv>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace leo { namespace adaptive {

WindowAssembler::WindowAssembler(uint32_t rate, uint32_t receivers, Sink sink)
    : maximum_rate_(rate), maximum_receivers_(receivers), sink_(std::move(sink)) {
    if (!rate || rate>10000000 || rate%1000 || !receivers || receivers>2 || !sink_)
        throw std::invalid_argument("invalid window capacity");
    buffer_.resize(static_cast<size_t>(rate/1000)*20*receivers*2);
}
void WindowAssembler::begin(const Visit& v) {
    if (active_) throw std::logic_error("previous visit not finished");
    if (!v.generation || !v.rate || v.rate>maximum_rate_ || v.rate%1000 ||
        !v.receivers || v.receivers>maximum_receivers_ || v.end<=v.first ||
        !std::isfinite(v.actual_rf_hz) || v.actual_rf_hz<=0)
        throw std::invalid_argument("invalid visit");
    const uint64_t count=v.end-v.first;
    if (count>static_cast<uint64_t>(v.rate)*360/1000)
        throw std::invalid_argument("visit exceeds 360 ms capacity");
    visit_=v; width_=v.rate/1000*20; stride_=v.rate/1000*120;
    expected_=next_=v.first; index_=0; filled_=0; active_=true;
}
void WindowAssembler::advance() {
    ++index_; filled_=0;
    // Addition relative to visit avoids wrapping absolute device counters.
    const uint64_t offset=static_cast<uint64_t>(index_)*stride_;
    next_=offset>visit_.end-visit_.first ? visit_.end : visit_.first+offset;
}
void WindowAssembler::push(uint64_t first, const int16_t* data, size_t count) {
    if (!active_) throw std::logic_error("no active visit");
    if ((!data && count) || first<expected_ || first>visit_.end || count>visit_.end-first)
        throw std::invalid_argument("invalid or reordered sample block");
    if (!count) return;
    if (first!=expected_) {
        ++stats_.discontinuities;
        if (filled_) { ++stats_.missing; advance(); }
    }
    const uint64_t end=first+count;
    while (next_<visit_.end && visit_.end-next_>=width_) {
        if (next_+filled_<first) { ++stats_.missing; advance(); continue; }
        const uint64_t begin=next_+filled_;
        if (begin>=end) break;
        const size_t take=static_cast<size_t>(std::min<uint64_t>(end-begin,width_-filled_));
        const size_t channels=visit_.receivers*2;
        std::copy_n(data+static_cast<size_t>(begin-first)*channels,take*channels,
                    buffer_.data()+filled_*channels);
        filled_+=take;
        if (filled_!=width_) break;
        Window out{visit_,next_,index_,width_,buffer_.data()};
        advance(); ++stats_.emitted;
        sink_(out);
    }
    expected_=end;
}
void WindowAssembler::finish() {
    if (!active_) throw std::logic_error("no active visit");
    while (next_<visit_.end && visit_.end-next_>=width_) {
        ++stats_.missing; advance();
    }
    if (expected_!=visit_.end) ++stats_.discontinuities;
    active_=false;
}

// Nearest-even implements Python's round independently of the current FP mode.
static double nearest_even(double x) {
    const double lo=std::floor(x), f=x-lo;
    return f<0.5 ? lo : f>0.5 ? lo+1 : (std::fmod(lo,2)==0 ? lo : lo+1);
}
// A volatile store is an explicit binary64 rounding point even when a caller
// compiles this source with wider evaluation registers.  The build also turns
// contraction off, but fractional_support is linked by several components
// with independently owned build scripts.
static double binary64(double value) {
    volatile double rounded=value;
    return rounded;
}
static double expansion_sum(const double* values,size_t count) {
    double partials[1024];size_t n=0;
    for(size_t k=0;k<count;++k) {
        double x=values[k];size_t i=0;
        for(size_t j=0;j<n;++j) {
            double y=partials[j];if(std::abs(x)<std::abs(y))std::swap(x,y);
            const double hi=binary64(x+y);
            const double lo=binary64(y-binary64(hi-x));
            if(lo!=0)partials[i++]=lo;
            x=hi;
        }
        partials[i]=x;n=i+1;
    }
    double hi=0,lo=0;
    if(n) {
        hi=partials[--n];
        while(n) {
            const double x=hi,y=partials[--n];hi=binary64(x+y);
            lo=binary64(y-binary64(hi-x));if(lo!=0)break;
        }
        if(n && ((lo<0 && partials[n-1]<0)||(lo>0 && partials[n-1]>0))) {
            const double y=binary64(lo*2),x=binary64(hi+y);
            if(y==binary64(x-hi))hi=x;
        }
    }
    return hi;
}
static Support fractional_support_uncached(uint32_t rate,uint32_t samples,int64_t epoch,double frac) {
    if (!rate || rate>10000000 || !samples || samples>rate/50 || epoch<0 ||
        epoch>=static_cast<int64_t>(samples) || !std::isfinite(frac) || std::abs(frac)>2)
        throw std::invalid_argument("invalid fractional support input");
    const bool integer=std::abs(frac-nearest_even(frac))<=1e-12;
    const int left=integer ? 0 : 7, right=integer ? 0 : 8;
    const double period=static_cast<double>(rate)/750.0, symbol=rate*4.4e-6;
    const int64_t templ=static_cast<int64_t>(nearest_even(period));
    // At most 16 frames x 64 symbol centers for a 20-ms window; fixed memory.
    // Each retained center is exactly c2/2 + frac.  Keeping c2 integral makes
    // the variance translation-invariant and avoids architecture-dependent
    // long-double rounding of the large absolute sample positions.
    double centers[1024]; size_t n=0;
    int64_t start=samples, end=0;
    for (unsigned frame=0;frame<16;++frame) {
        const int64_t base=epoch+static_cast<int64_t>(nearest_even(frame*period));
        if (base+frac>=samples || base+nearest_even(2*symbol)+frac>=samples) break;
        for (int s=2;s<66;++s) {
            const int64_t a=static_cast<int64_t>(nearest_even(s*symbol));
            const int64_t b=std::min<int64_t>(static_cast<int64_t>(nearest_even((s+1)*symbol)),templ);
            const int64_t count=b-a;
            const double x=base+a+frac;
            if (count<2 || x<left || x+count-1>=samples-right) continue;
            centers[n++]=binary64(x+static_cast<double>(count-1)/2.0);
            start=std::min(start,static_cast<int64_t>(std::floor(x))-left);
            end=std::max(end,static_cast<int64_t>(std::floor(x+count-1))+right+1);
        }
    }
    if (n<2) throw std::invalid_argument("insufficient fractional support");
    const double center=binary64(expansion_sum(centers,n)/static_cast<double>(n));
    double second[1024],third[1024];
    for(size_t i=0;i<n;++i) {
        const double d=binary64(binary64(centers[i]-center)/rate);
        second[i]=std::pow(d,2.0);
        third[i]=std::pow(d,3.0);
    }
    const double moment2=binary64(binary64(expansion_sum(second,n)/static_cast<double>(n))/2.0);
    const double moment3=binary64(binary64(expansion_sum(third,n)/static_cast<double>(n))/6.0);
    return {start,end,center,moment2,moment3,static_cast<uint32_t>(n)};
}
Support fractional_support(uint32_t rate,uint32_t samples,int64_t epoch,double frac) {
    struct Entry {
        uint32_t rate=0,samples=0;
        int64_t epoch=0;
        uint64_t fraction_bits=0;
        int rounding=FE_TONEAREST;
        Support support{};
        bool valid=false;
    };
    thread_local Entry last;
    uint64_t fraction_bits;
    static_assert(sizeof fraction_bits==sizeof frac,"binary64 key width");
    std::memcpy(&fraction_bits,&frac,sizeof fraction_bits);
    const int rounding=std::fegetround();
    if(last.valid && last.rate==rate && last.samples==samples && last.epoch==epoch &&
       last.fraction_bits==fraction_bits && last.rounding==rounding)
        return last.support;
    const Support support=fractional_support_uncached(rate,samples,epoch,frac);
    last={rate,samples,epoch,fraction_bits,rounding,support,true};
    return support;
}
int64_t support_utc_ns(uint64_t anchor,int64_t utc,uint64_t window,double local,uint32_t rate) {
    if (!rate || !std::isfinite(local) || local<0 || window<anchor || window-anchor>UINT64_C(9007199254740992))
        throw std::invalid_argument("invalid counter/time mapping");
    const double delta=nearest_even((static_cast<double>(window-anchor)+local)*1e9/rate);
    if (delta<0 || delta>=9223372036854775808.0)
        throw std::overflow_error("UTC mapping overflow");
    const int64_t offset=static_cast<int64_t>(delta);
    if (utc>std::numeric_limits<int64_t>::max()-offset)
        throw std::overflow_error("UTC mapping overflow");
    return utc+offset;
}

Executor::Executor(size_t workers,size_t capacity) {
    if (!workers || workers>64 || !capacity || capacity>65536)
        throw std::invalid_argument("invalid executor bounds");
    ring_.resize(capacity);
    try { for(size_t i=0;i<workers;++i) workers_.emplace_back(&Executor::work,this,i); }
    catch (...) { stop(true); throw; }
}
Executor::~Executor() { stop(false); }
bool Executor::submit(Job job) {
    if (!job.run) throw std::invalid_argument("empty job");
    std::lock_guard<std::mutex> lock(mutex_);
    if (stopping_ || stats_.queued==ring_.size()) { ++stats_.rejected; return false; }
    ring_[tail_]=job; tail_=(tail_+1)%ring_.size(); ++stats_.queued; ++stats_.accepted;
    stats_.high_water=std::max(stats_.high_water,stats_.queued); ready_.notify_one(); return true;
}
void Executor::work(size_t worker) {
    for (;;) {
        Job job;
        { std::unique_lock<std::mutex> lock(mutex_);
          ready_.wait(lock,[this]{return stopping_ || stats_.queued;});
          if (!stats_.queued && stopping_) return;
          job=ring_[head_]; head_=(head_+1)%ring_.size(); --stats_.queued; ++stats_.running; }
        std::exception_ptr error;
        try { job.run(job.context,worker); } catch (...) { error=std::current_exception(); }
        { std::lock_guard<std::mutex> lock(mutex_);
          --stats_.running;
          if (error) { ++stats_.failed; if (!failure_) failure_=error; }
          else ++stats_.completed;
          if (!stats_.queued && !stats_.running) idle_.notify_all(); }
    }
}
void Executor::drain() {
    std::unique_lock<std::mutex> lock(mutex_);
    idle_.wait(lock,[this]{return !stats_.queued && !stats_.running;});
}
void Executor::stop(bool cancel) {
    { std::lock_guard<std::mutex> lock(mutex_); stopping_=true;
      if (cancel) { stats_.cancelled+=stats_.queued; stats_.queued=0; head_=tail_; }
      ready_.notify_all(); idle_.notify_all(); }
    for(auto& worker:workers_) if (worker.joinable()) worker.join();
}
ExecutorStats Executor::stats() const { std::lock_guard<std::mutex> lock(mutex_); return stats_; }
void Executor::rethrow_first_failure() const {
    std::lock_guard<std::mutex> lock(mutex_); if(failure_) std::rethrow_exception(failure_);
}
} }
