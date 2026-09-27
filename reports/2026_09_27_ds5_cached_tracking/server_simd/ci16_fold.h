/* Exact x86 SIMD extension of the pinned deployment ci16_fold.h.
 * Each int16 product is widened separately before complex int64 add/sub. */
#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("ssse3,sse4.1")))
static inline __m128i server_deinterleave_real32(__m128i values)
{
    const __m128i mask=_mm_setr_epi8(0,1,4,5,8,9,12,13,
        (char)0x80,(char)0x80,(char)0x80,(char)0x80,
        (char)0x80,(char)0x80,(char)0x80,(char)0x80);
    return _mm_cvtepi16_epi32(_mm_shuffle_epi8(values,mask));
}

__attribute__((target("ssse3,sse4.1")))
static inline __m128i server_deinterleave_imag32(__m128i values)
{
    const __m128i mask=_mm_setr_epi8(2,3,6,7,10,11,14,15,
        (char)0x80,(char)0x80,(char)0x80,(char)0x80,
        (char)0x80,(char)0x80,(char)0x80,(char)0x80);
    return _mm_cvtepi16_epi32(_mm_shuffle_epi8(values,mask));
}

__attribute__((target("ssse3,sse4.1")))
static inline void server_add_widened_pair(int64_t *destination,
    __m128i first, __m128i second, int subtract)
{
    __m128i first_lo=_mm_cvtepi32_epi64(first);
    __m128i first_hi=_mm_cvtepi32_epi64(_mm_srli_si128(first,8));
    __m128i second_lo=_mm_cvtepi32_epi64(second);
    __m128i second_hi=_mm_cvtepi32_epi64(_mm_srli_si128(second,8));
    __m128i lo=subtract ? _mm_sub_epi64(first_lo,second_lo) : _mm_add_epi64(first_lo,second_lo);
    __m128i hi=subtract ? _mm_sub_epi64(first_hi,second_hi) : _mm_add_epi64(first_hi,second_hi);
    _mm_storeu_si128((__m128i *)destination,
        _mm_add_epi64(_mm_loadu_si128((const __m128i *)destination),lo));
    _mm_storeu_si128((__m128i *)(destination+2),
        _mm_add_epi64(_mm_loadu_si128((const __m128i *)(destination+2)),hi));
}

__attribute__((target("ssse3,sse4.1")))
static inline void server_coarse_fold_four(const int16_t *a_iq, const int16_t *b_iq,
    int64_t *energy, int64_t *real, int64_t *imag,
    int32_t *support, int32_t *diff_support)
{
    __m128i a=_mm_loadu_si128((const __m128i *)a_iq);
    __m128i b=_mm_loadu_si128((const __m128i *)b_iq);
    __m128i ar=server_deinterleave_real32(a), ai=server_deinterleave_imag32(a);
    __m128i br=server_deinterleave_real32(b), bi=server_deinterleave_imag32(b);
    server_add_widened_pair(real,_mm_mullo_epi32(ar,br),_mm_mullo_epi32(ai,bi),0);
    server_add_widened_pair(imag,_mm_mullo_epi32(ar,bi),_mm_mullo_epi32(ai,br),1);
    server_add_widened_pair(energy,_mm_mullo_epi32(ar,ar),_mm_mullo_epi32(ai,ai),0);
    __m128i one=_mm_set1_epi32(1);
    _mm_storeu_si128((__m128i *)support,
        _mm_add_epi32(_mm_loadu_si128((const __m128i *)support),one));
    _mm_storeu_si128((__m128i *)diff_support,
        _mm_add_epi32(_mm_loadu_si128((const __m128i *)diff_support),one));
}
#endif

static void coarse_fold_ci16(leo_presence_workspace *w, const int16_t *iq, size_t count)
{
    for (size_t block=0; block<w->n; block+=256) {
        size_t width=w->n-block<256 ? w->n-block : 256;
        int64_t energy[256]={0}, real[256]={0}, imag[256]={0};
        int32_t support[256]={0}, diff_support[256]={0};
        for (int frame=0; frame<16; ++frame) {
            size_t start=(size_t)frame_start(w,0,frame);
            if (start>=count || count-start<=block) break;
            size_t valid=count-start-block;
            if (valid>width) valid=width;
            size_t available=count-start-block;
            size_t paired=available>LEO_PRESENCE_DIFFERENTIAL_LAG ?
                available-LEO_PRESENCE_DIFFERENTIAL_LAG : 0;
            if (paired>valid) paired=valid;
            size_t k=0;
#if defined(__x86_64__) || defined(__i386__)
            if (server_simd_enabled()) for (; k+3<paired; k+=4)
                server_coarse_fold_four(iq+2*(start+block+k),
                    iq+2*(start+block+k+LEO_PRESENCE_DIFFERENTIAL_LAG),
                    energy+k,real+k,imag+k,support+k,diff_support+k);
#endif
            for (; k<valid; ++k) {
                size_t offset=2*(start+block+k);
                int64_t ar=iq[offset], ai=iq[offset+1];
                energy[k]+=ar*ar+ai*ai;
                ++support[k];
                if (k<paired) {
                    int64_t br=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG];
                    int64_t bi=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG+1];
                    real[k]+=ar*br+ai*bi; imag[k]+=ar*bi-ai*br;
                    ++diff_support[k];
                }
            }
        }
        for (size_t k=0; k<width; ++k) {
            w->power_native_folded[block+k]=(double)energy[k];
            w->diff_folded[block+k]=(double)real[k]+I*(double)imag[k];
            w->support[block+k]=support[k];
            w->diff_support[block+k]=diff_support[k];
        }
    }
}
