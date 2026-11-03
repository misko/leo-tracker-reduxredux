#include "usb_source_port.h"
#include "runtime.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#define CHECK(x) do { if (!(x)) { std::cerr << __FILE__ << ':' << __LINE__ \
    << ": check failed: " #x "\n"; std::exit(1); } } while (0)

namespace {

enum class RetuneMode {
    normal, missing_boundary, backwards, future_boundary, forged_software
};

struct Fake {
    leo_usb_capabilities caps{};
    std::vector<int16_t> samples;
    uint32_t receivers{1},chunk{3};
    uint64_t counter{100};
    size_t position{};
    int probes{},opens{},acquires{},releases{},cancels{},retunes{},closes{};
    int release_error{};
    RetuneMode retune_mode{RetuneMode::normal};
};

leo_usb_capabilities capabilities(uint32_t counter=LEO_USB_COUNTER_NONE,
                                  uint32_t receivers=1)
{
    leo_usb_capabilities value{};
    value.abi_version=LEO_USB_SOURCE_ABI_VERSION;
    value.sample_format_mask=LEO_USB_SAMPLE_FORMAT_CI16;
    value.flags=LEO_USB_CAP_EXCLUSIVE_OPEN|LEO_USB_CAP_CANCEL|
        LEO_USB_CAP_OVERFLOW_REPORTING|LEO_USB_CAP_RETUNE|
        LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY;
    if(receivers==2) value.flags|=LEO_USB_CAP_SIMULTANEOUS_RX|
        LEO_USB_CAP_COHERENT_RX;
    value.max_receivers=receivers;
    value.max_samples_per_block=1000000;
    value.counter_authority=counter;
    value.time_authority=counter==LEO_USB_COUNTER_NONE ?
        LEO_USB_TIME_NONE:LEO_USB_TIME_DEVICE;
    value.minimum_time_uncertainty_ns=counter==LEO_USB_COUNTER_NONE ? 0:50;
    value.minimum_sample_rate_hz=1000;
    value.maximum_sample_rate_hz=10000000;
    value.minimum_bandwidth_hz=1000;
    value.maximum_bandwidth_hz=10000000;
    value.minimum_frequency_hz=1000000;
    value.maximum_frequency_hz=6000000000ULL;
    return value;
}

leo_usb_config config(uint32_t receivers=1)
{
    leo_usb_config value{};
    value.abi_version=LEO_USB_SOURCE_ABI_VERSION;
    value.selector="fake=port";
    value.sample_rate_hz=7500000;
    value.analog_bandwidth_hz=6000000;
    value.samples_per_block=900000;
    value.receiver_count=receivers;
    value.center_frequency_hz=1710000000;
    value.maximum_frequency_error_hz=2;
    value.maximum_time_uncertainty_ns=100;
    return value;
}

void fill(Fake& fake,uint32_t count=12)
{
    fake.samples.resize(static_cast<size_t>(count)*fake.receivers*2);
    for(size_t index=0;index<fake.samples.size();++index)
        fake.samples[index]=static_cast<int16_t>(index*17u+3u);
}

int probe(void* context,const char*,leo_usb_capabilities* out)
{
    auto& fake=*static_cast<Fake*>(context);++fake.probes;*out=fake.caps;return 0;
}
int open_source(void* context,const leo_usb_config*,void** capture)
{
    auto& fake=*static_cast<Fake*>(context);++fake.opens;*capture=&fake;return 0;
}
int acquire(void* context,void*,leo_usb_provider_block* out)
{
    auto& fake=*static_cast<Fake*>(context);++fake.acquires;
    const size_t available=fake.samples.size()/(fake.receivers*2)-fake.position;
    if(!available)return -ENODATA;
    const auto count=static_cast<uint32_t>(
        std::min<size_t>(available,fake.chunk));
    out->ci16=fake.samples.data()+fake.position*fake.receivers*2;
    out->iq_bytes=static_cast<size_t>(count)*fake.receivers*2*sizeof(int16_t);
    out->samples_per_receiver=count;
    out->receiver_count=fake.receivers;
    out->counter_authority=fake.caps.counter_authority;
    out->time_authority=fake.caps.time_authority;
    out->first_counter=fake.counter+fake.position;
    if(out->time_authority!=LEO_USB_TIME_NONE){
        out->first_time_ns=1000000+fake.position*100;
        out->time_uncertainty_ns=fake.caps.minimum_time_uncertainty_ns;
    }
    out->token=fake.position+11;
    fake.position+=count;
    return 0;
}
int cancel(void* context,void*)
{++static_cast<Fake*>(context)->cancels;return 0;}
int release(void* context,void*,uintptr_t)
{auto& fake=*static_cast<Fake*>(context);++fake.releases;return fake.release_error;}
int retune(void* context,void*,uint64_t frequency,leo_usb_provider_retune* out)
{
    auto& fake=*static_cast<Fake*>(context);++fake.retunes;
    out->actual_frequency_hz=frequency+1;
    if(fake.retune_mode==RetuneMode::forged_software){
        out->flags=LEO_USB_RETUNE_VALID_COUNTER;
        out->counter_authority=LEO_USB_COUNTER_SOFTWARE_DELIVERED;
        out->valid_counter=fake.position;
    }else if(fake.caps.counter_authority!=LEO_USB_COUNTER_NONE &&
             fake.retune_mode!=RetuneMode::missing_boundary){
        out->flags=LEO_USB_RETUNE_VALID_COUNTER|LEO_USB_RETUNE_VALID_TIME;
        out->counter_authority=fake.caps.counter_authority;
        out->time_authority=fake.caps.time_authority;
        out->valid_counter=fake.counter+fake.position;
        if(fake.retune_mode==RetuneMode::backwards)--out->valid_counter;
        if(fake.retune_mode==RetuneMode::future_boundary)
            out->valid_counter+=10;
        out->valid_time_ns=1000000+fake.position*100;
        out->time_uncertainty_ns=fake.caps.minimum_time_uncertainty_ns;
    }
    return 0;
}
int close_source(void* context,void*)
{++static_cast<Fake*>(context)->closes;return 0;}

leo_usb_provider_ops operations(Fake& fake)
{
    return {LEO_USB_SOURCE_ABI_VERSION,&fake,probe,open_source,acquire,cancel,
        release,retune,close_source};
}

leo_usb_source* open(Fake& fake,uint32_t receivers=1)
{
    auto ops=operations(fake);auto cfg=config(receivers);leo_usb_source* source=nullptr;
    CHECK(leo_usb_source_open(&cfg,&ops,&source)==0);return source;
}

void test_capability_preflight_and_info()
{
    Fake unsupported;unsupported.caps=capabilities();fill(unsupported);
    unsupported.caps.flags&=~LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY;
    auto* source=open(unsupported);leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==-ENOTSUP);
    CHECK(!adapter&&unsupported.retunes==0);
    CHECK(leo_usb_source_close(source)==0);

    Fake malformed;malformed.caps=capabilities();fill(malformed);
    malformed.caps.flags&=~LEO_USB_CAP_RETUNE;
    auto ops=operations(malformed);auto cfg=config();source=nullptr;
    CHECK(leo_usb_source_open(&cfg,&ops,&source)==-EPROTO);
    CHECK(!source&&malformed.opens==0);

    Fake fake;fake.caps=capabilities();fill(fake);source=open(fake);
    leo_usb_stream_info info{};
    CHECK(leo_usb_source_get_stream_info(source,&info)==0);
    CHECK(info.abi_version==LEO_USB_SOURCE_ABI_VERSION&&
        info.sample_rate_hz==7500000&&info.receiver_count==1&&
        info.maximum_samples_per_block==1000000&&
        info.counter_authority==LEO_USB_COUNTER_SOFTWARE_DELIVERED&&
        info.time_authority==LEO_USB_TIME_NONE&&info.watermark_valid==1&&
        info.delivered_watermark==0);
    leo_usb_block block{};CHECK(leo_usb_source_next(source,&block)==0);
    CHECK(leo_usb_source_get_stream_info(source,&info)==-EBUSY);
    CHECK(leo_usb_source_release(source,&block)==0);
    CHECK(leo_usb_source_get_stream_info(source,&info)==0&&
        info.delivered_watermark==3);
    CHECK(leo_usb_source_close(source)==0);
}

void test_software_mapping_and_selection()
{
    Fake fake;fake.caps=capabilities();fill(fake);auto* source=open(fake);
    leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);leo_source_capabilities caps{};
    CHECK(leo_source_port_capabilities(port,&caps)==0);
    CHECK(caps.receiver_count==1&&
        caps.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED&&
        caps.position_semantics==LEO_SOURCE_POSITION_DELIVERED_WATERMARK&&
        caps.time_authority==LEO_SOURCE_TIME_NONE&&
        !(caps.flags&(LEO_SOURCE_CAP_SIMULTANEOUS_RX|
            LEO_SOURCE_CAP_COHERENT_RX|LEO_SOURCE_CAP_EXACT_GAP|
            LEO_SOURCE_CAP_TARGET_ATTESTATION|
            LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION)));
    leo_source_position position{};
    CHECK(leo_source_port_position(port,&position)==0&&position.coordinate==0);
    leo_source_selection selection{77,1720000000,2};
    leo_source_transition transition{};
    CHECK(leo_source_port_select(port,&selection,&transition)==0);
    CHECK(fake.retunes==1&&transition.actual_frequency_hz==1720000001&&
        transition.previous_valid_end==0&&transition.valid_start==0&&
        transition.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED&&
        transition.position_semantics==LEO_SOURCE_POSITION_DELIVERED_WATERMARK&&
        transition.selected_target_key==0&&transition.profile_crc32==0&&
        transition.time_authority==LEO_SOURCE_TIME_NONE&&
        transition.flags==(LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
            LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY));
    leo_source_block block{};CHECK(leo_source_port_next(port,&block)==0);
    CHECK(block.receiver_count==1&&block.first_coordinate==0&&
        block.end_coordinate==3&&block.stream_ordinal==0&&
        block.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED&&
        block.time_authority==LEO_SOURCE_TIME_NONE&&
        !(block.flags&LEO_SOURCE_BLOCK_GAP_EXACT));
    CHECK(leo_source_port_position(port,&position)==-EBUSY);
    CHECK(leo_source_port_release(port,&block)==0);
    CHECK(leo_source_port_position(port,&position)==0&&position.coordinate==3);
    CHECK(leo_source_port_cancel(port)==0&&fake.cancels==1);
    CHECK(leo_usb_source_port_destroy(adapter)==0);
    CHECK(leo_usb_source_close(source)==0);
}

void test_exact_dual_gap_and_no_time_transition()
{
    Fake fake;fake.receivers=2;
    fake.caps=capabilities(LEO_USB_COUNTER_PROVIDER_EXACT,2);fill(fake);
    auto* source=open(fake,2);leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);leo_source_capabilities caps{};
    CHECK(leo_source_port_capabilities(port,&caps)==0);
    CHECK(caps.receiver_count==2&&(caps.flags&LEO_SOURCE_CAP_SIMULTANEOUS_RX)&&
        (caps.flags&LEO_SOURCE_CAP_COHERENT_RX)&&
        (caps.flags&LEO_SOURCE_CAP_EXACT_GAP)&&
        caps.counter_authority==LEO_SOURCE_COUNTER_PROVIDER_EXACT);
    leo_source_position position{};CHECK(leo_source_port_position(port,&position)==-ENODATA);
    leo_source_block first{};CHECK(leo_source_port_next(port,&first)==0);
    CHECK(!(first.flags&LEO_SOURCE_BLOCK_GAP_EXACT));
    CHECK(leo_source_port_release(port,&first)==0);
    CHECK(leo_source_port_position(port,&position)==0&&position.coordinate==103);
    leo_source_selection selection{1,1720000000,2};leo_source_transition tr{};
    CHECK(leo_source_port_select(port,&selection,&tr)==0);
    CHECK(tr.previous_valid_end==103&&tr.valid_start==103&&
        !(tr.flags&LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY)&&
        tr.time_authority==LEO_SOURCE_TIME_NONE&&tr.valid_start_time_ns==0);
    fake.counter+=2;
    leo_source_block second{};CHECK(leo_source_port_next(port,&second)==0);
    CHECK((second.flags&LEO_SOURCE_BLOCK_GAP_EXACT)&&
        (second.flags&LEO_SOURCE_BLOCK_DISCONTINUITY)&&
        second.missing_samples_before==2&&second.first_coordinate==105);
    CHECK(leo_source_port_release(port,&second)==0);
    CHECK(leo_usb_source_port_destroy(adapter)==0);
    CHECK(leo_usb_source_close(source)==0);
}

void test_estimated_discontinuity_never_promotes_exact_gap()
{
    Fake fake;fake.caps=capabilities(LEO_USB_COUNTER_PROVIDER_ESTIMATED);fill(fake);
    auto* source=open(fake);leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);leo_source_capabilities caps{};
    CHECK(leo_source_port_capabilities(port,&caps)==0&&
        caps.counter_authority==LEO_SOURCE_COUNTER_PROVIDER_ESTIMATED&&
        !(caps.flags&LEO_SOURCE_CAP_EXACT_GAP));
    leo_source_block first{};CHECK(leo_source_port_next(port,&first)==0);
    CHECK(leo_source_port_release(port,&first)==0);fake.counter+=2;
    leo_source_block second{};CHECK(leo_source_port_next(port,&second)==0);
    CHECK((second.flags&LEO_SOURCE_BLOCK_DISCONTINUITY)&&
        !(second.flags&LEO_SOURCE_BLOCK_GAP_EXACT)&&
        second.missing_samples_before==0);
    CHECK(leo_source_port_release(port,&second)==0);
    CHECK(leo_usb_source_port_destroy(adapter)==0);
    CHECK(leo_usb_source_close(source)==0);
}

void test_promised_boundary_fail_closed()
{
    for(auto mode:{RetuneMode::missing_boundary,RetuneMode::backwards}){
        Fake fake;fake.caps=capabilities(LEO_USB_COUNTER_PROVIDER_EXACT);fill(fake);
        fake.retune_mode=mode;auto* source=open(fake);
        leo_usb_source_port* adapter=nullptr;
        CHECK(leo_usb_source_port_create(source,&adapter)==0);
        auto* port=leo_usb_source_port_get(adapter);leo_source_block block{};
        CHECK(leo_source_port_next(port,&block)==0);
        CHECK(leo_source_port_release(port,&block)==0);
        leo_source_selection selection{0,1720000000,2};leo_source_transition tr{};
        CHECK(leo_source_port_select(port,&selection,&tr)==-EPROTO);
        leo_source_position position{};
        CHECK(fake.retunes==1&&
            leo_source_port_position(port,&position)==-EPROTO);
        CHECK(leo_usb_source_port_destroy(adapter)==0);
        CHECK(leo_usb_source_close(source)==0);
    }
    Fake forged;forged.caps=capabilities();fill(forged);
    forged.retune_mode=RetuneMode::forged_software;auto* source=open(forged);
    leo_usb_source_port* adapter=nullptr;CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);
    leo_source_selection selection{0,1720000000,2};leo_source_transition tr{};
    CHECK(leo_source_port_select(port,&selection,&tr)==-EPROTO);
    CHECK(forged.retunes==1);
    CHECK(leo_usb_source_port_destroy(adapter)==0);
    CHECK(leo_usb_source_close(source)==0);
}

void test_release_failure_abandon_order()
{
    Fake fake;fake.caps=capabilities();fill(fake);auto* source=open(fake);
    leo_usb_source_port* adapter=nullptr;CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);leo_source_block block{};
    CHECK(leo_source_port_next(port,&block)==0);fake.release_error=-EIO;
    CHECK(leo_source_port_release(port,&block)==-EIO);
    CHECK(leo_source_port_cleanup(port)==-EIO);
    CHECK(leo_usb_source_port_destroy(adapter)==-EBUSY);
    CHECK(leo_usb_source_port_abandon_lease(adapter)==0);
    CHECK(leo_usb_source_close(source)==0&&fake.closes==1&&fake.releases==1);
}

void test_mapping_error_release_failure_requires_abandon()
{
    Fake fake;fake.caps=capabilities(LEO_USB_COUNTER_PROVIDER_EXACT);fill(fake);
    auto* source=open(fake);leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);leo_source_block first{};
    CHECK(leo_source_port_next(port,&first)==0);
    CHECK(leo_source_port_release(port,&first)==0);
    fake.retune_mode=RetuneMode::future_boundary;
    leo_source_selection selection{0,1720000000,2};leo_source_transition tr{};
    CHECK(leo_source_port_select(port,&selection,&tr)==0&&tr.valid_start==113);
    fake.release_error=-EIO;leo_source_block invalid{};
    CHECK(leo_source_port_next(port,&invalid)==-EIO);
    CHECK(fake.releases==2&&leo_usb_source_port_destroy(adapter)==-EBUSY);
    CHECK(leo_usb_source_port_abandon_lease(adapter)==0);
    CHECK(leo_usb_source_close(source)==0&&fake.closes==1);
}

void test_ds9_single_receiver(const char* path)
{
    std::ifstream in(path,std::ios::binary);CHECK(in.good());
    std::vector<int16_t> dual(3600000);
    in.read(reinterpret_cast<char*>(dual.data()),7200000);
    CHECK(in.good()&&in.peek()==std::char_traits<char>::eof());
    Fake fake;fake.receivers=1;fake.chunk=77777;fake.caps=capabilities();
    for(size_t sample=0;sample<dual.size()/4;++sample){
        fake.samples.push_back(dual[4*sample]);
        fake.samples.push_back(dual[4*sample+1]);
    }
    auto* source=open(fake);leo_usb_source_port* adapter=nullptr;
    CHECK(leo_usb_source_port_create(source,&adapter)==0);
    auto* port=leo_usb_source_port_get(adapter);std::vector<int16_t> window;
    leo::adaptive::WindowAssembler assembler(7500000,1,
        [&](const leo::adaptive::Window& value){
            CHECK(value.first==0&&value.samples==150000&&value.visit.receivers==1);
            window.assign(value.iq,value.iq+static_cast<size_t>(value.samples)*2);
        });
    assembler.begin({1,276,0,900000,7500000,1,1710000000.0});
    for(;;){
        leo_source_block block{};const int status=leo_source_port_next(port,&block);
        if(status==-ENODATA)break;
        CHECK(status==0&&block.receiver_count==1&&
            block.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED&&
            block.time_authority==LEO_SOURCE_TIME_NONE&&
            !(block.flags&LEO_SOURCE_BLOCK_GAP_EXACT));
        assembler.push(block.first_coordinate,block.ci16,
            block.samples_per_receiver);
        CHECK(leo_source_port_release(port,&block)==0);
    }
    assembler.finish();const auto stats=assembler.stats();
    CHECK(stats.emitted==1&&stats.missing==0&&stats.discontinuities==0&&
        window.size()==300000);
    CHECK(std::memcmp(window.data(),fake.samples.data(),
        window.size()*sizeof(int16_t))==0);
    CHECK(leo_usb_source_port_destroy(adapter)==0);
    CHECK(leo_usb_source_close(source)==0&&fake.releases==12);
}

} // namespace

int main(int argc,char** argv)
{
    CHECK(argc==2);
    test_capability_preflight_and_info();
    test_software_mapping_and_selection();
    test_exact_dual_gap_and_no_time_transition();
    test_estimated_discontinuity_never_promotes_exact_gap();
    test_promised_boundary_fail_closed();
    test_release_failure_abandon_order();
    test_mapping_error_release_failure_requires_abandon();
    test_ds9_single_receiver(argv[1]);
    std::cout<<"usb source port: mapping, failure, and DS9 parity pass\n";
}
