extern "C" {
#include "native_glrt.h"
}
#include <chrono>
#include <thread>
struct leo_native_glrt {};
extern "C" int leo_native_glrt_layout(uint32_t,uint32_t,uint32_t,size_t* n,size_t* r) {*n=1;*r=1;return 0;}
extern "C" int leo_native_glrt_create_with_mode(leo_native_glrt** out,uint32_t,
    const leo_native_glrt_complex*,const leo_native_glrt_complex*,size_t,uint32_t) {
    *out=new leo_native_glrt;return 0;
}
extern "C" int leo_native_glrt_destroy(leo_native_glrt* p) {delete p;return 0;}
extern "C" int leo_native_glrt_analyze(leo_native_glrt*,const int16_t*,size_t,uint32_t,uint32_t,leo_native_glrt_result* r) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    *r={};r->row_count=1;r->rows[0].candidate_count=1;r->rows[0].candidates[0].margin=.1;return 0;
}
