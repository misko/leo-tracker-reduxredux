#include "tracking.hpp"
#include "hough_bin.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <new>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <unordered_map>

namespace leo::adaptive::tracking {
namespace {

constexpr double kNsPerSecond = 1'000'000'000.0;
constexpr const char* kAlgorithmVersion = "persistent-hop-normalized-hough-episode-graph-v1";
constexpr const char* kDeploymentConfigDigest =
    "sha256:f3f57ddb7f931433e5c93f16ed69892012896287277a53a6d382c8c95417b913";

struct LaneKey {
    int channel;
    std::string edge;
    int receiver_id;
    double actual_rf_hz;

    bool operator<(const LaneKey& other) const {
        return std::tie(channel, edge, receiver_id, actual_rf_hz) <
               std::tie(other.channel, other.edge, other.receiver_id, other.actual_rf_hz);
    }
};

struct Point {
    const Candidate* source{};
    double time_s{};
    double frequency_hz{};
    double weight{};
};

struct Segment {
    std::string segment_id;
    std::vector<std::size_t> indexes;
    double start_s{};
    double end_s{};
    double weighted_support{};
    double slope{};
    double intercept{};
    double residual_rms{};
    double residual_max{};
};

struct BinChunk {
    std::size_t first_point{};
    std::size_t point_count{};
    std::vector<std::uint16_t> values;
};

struct BinView {
    const std::vector<BinChunk>* chunks{};
};

double positive_mod(double value, double modulus) {
    double result = std::fmod(value, modulus);
    return result < 0.0 ? result + modulus : result;
}

double circular_residual(double frequency, double prediction, double spacing) {
    return positive_mod(frequency - prediction + spacing / 2.0, spacing) - spacing / 2.0;
}

double evidence_weight(const Candidate& value) {
    return std::min(std::max(value.margin, 0.0) / std::max(value.control_score, 0.02), 16.0);
}

std::uint32_t rotate_right(std::uint32_t value, unsigned count) {
    return (value >> count) | (value << (32U - count));
}

std::string sha256(const std::string& input) {
    static constexpr std::array<std::uint32_t, 64> k{
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
    std::vector<unsigned char> bytes(input.begin(), input.end());
    const std::uint64_t bit_length = static_cast<std::uint64_t>(bytes.size()) * 8U;
    bytes.push_back(0x80U);
    while (bytes.size() % 64U != 56U) bytes.push_back(0U);
    for (int shift = 56; shift >= 0; shift -= 8) bytes.push_back(static_cast<unsigned char>(bit_length >> shift));
    std::array<std::uint32_t, 8> h{0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
                                   0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    for (std::size_t offset = 0; offset < bytes.size(); offset += 64U) {
        std::array<std::uint32_t, 64> w{};
        for (std::size_t i = 0; i < 16; ++i) {
            const std::size_t p = offset + i * 4U;
            w[i] = (static_cast<std::uint32_t>(bytes[p]) << 24U) |
                   (static_cast<std::uint32_t>(bytes[p + 1]) << 16U) |
                   (static_cast<std::uint32_t>(bytes[p + 2]) << 8U) | bytes[p + 3];
        }
        for (std::size_t i = 16; i < 64; ++i) {
            const std::uint32_t s0 = rotate_right(w[i-15],7) ^ rotate_right(w[i-15],18) ^ (w[i-15]>>3);
            const std::uint32_t s1 = rotate_right(w[i-2],17) ^ rotate_right(w[i-2],19) ^ (w[i-2]>>10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        auto a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], hh=h[7];
        for (std::size_t i = 0; i < 64; ++i) {
            const std::uint32_t s1=rotate_right(e,6)^rotate_right(e,11)^rotate_right(e,25);
            const std::uint32_t ch=(e&f)^((~e)&g);
            const std::uint32_t t1=hh+s1+ch+k[i]+w[i];
            const std::uint32_t s0=rotate_right(a,2)^rotate_right(a,13)^rotate_right(a,22);
            const std::uint32_t maj=(a&b)^(a&c)^(b&c);
            const std::uint32_t t2=s0+maj;
            hh=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
    }
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (auto value : h) out << std::setw(8) << value;
    return out.str();
}

bool tagged_digest(const std::string& value) {
    return value.size()==71 && value.compare(0,7,"sha256:")==0 &&
        value.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}

std::string segment_identity(const std::vector<std::size_t>& indexes,
                             const std::vector<Point>& points) {
    std::string material = "weighted_hough";
    material.push_back('\0');
    for (std::size_t index : indexes) {
        material += points[index].source->candidate_id;
        material.push_back('\0');
    }
    if (!indexes.empty()) material.pop_back();
    return "sha256:" + sha256(material);
}

bool is_deployment_profile(const Config& config) {
    const Config expected;
    return config.canonical_rf_hz==expected.canonical_rf_hz &&
        config.alias_spacing_hz==expected.alias_spacing_hz &&
        config.minimum_slope_hz_per_s==expected.minimum_slope_hz_per_s &&
        config.maximum_slope_hz_per_s==expected.maximum_slope_hz_per_s &&
        config.residual_gate_hz==expected.residual_gate_hz &&
        config.maximum_gap_s==expected.maximum_gap_s &&
        config.minimum_span_s==expected.minimum_span_s &&
        config.minimum_support==expected.minimum_support &&
        config.minimum_point_weight==expected.minimum_point_weight &&
        config.slope_bins==expected.slope_bins &&
        config.intercept_bins==expected.intercept_bins &&
        config.peak_candidates==expected.peak_candidates &&
        config.maximum_tracks_per_lane==expected.maximum_tracks_per_lane &&
        config.maximum_input_points==expected.maximum_input_points &&
        config.maximum_candidates_per_source_group==expected.maximum_candidates_per_source_group &&
        config.maximum_trajectory_hypotheses==expected.maximum_trajectory_hypotheses &&
        config.cross_lane_minimum_overlap_s==expected.cross_lane_minimum_overlap_s &&
        config.cross_lane_rate_gate_hz_per_s==expected.cross_lane_rate_gate_hz_per_s;
}

std::string tracklet_identity(const LaneKey& lane, const Segment& segment,
                              const std::vector<Point>& points, const Config& config) {
    if (!is_deployment_profile(config)) return {};
    std::ostringstream material;
    material << "{\"algorithm_version\":\"" << kAlgorithmVersion
             << "\",\"config_digest\":\"" << kDeploymentConfigDigest
             << "\",\"lane_key\":[" << lane.channel << ",\"" << lane.edge << "\"," 
             << lane.receiver_id << ',' << std::fixed << std::setprecision(1) << lane.actual_rf_hz
             << "],\"point_ids\":[";
    for (std::size_t offset = 0; offset < segment.indexes.size(); ++offset) {
        if (offset) material << ',';
        material << '\"' << points[segment.indexes[offset]].source->candidate_id << '\"';
    }
    material << "],\"segment_id\":\"" << segment.segment_id << "\"}";
    return "sha256:" + sha256(material.str());
}

std::vector<std::size_t> one_per_source(const std::vector<std::size_t>& indexes,
                                        const std::vector<Point>& points,
                                        const std::vector<double>& residuals) {
    std::map<std::string, std::size_t> best;
    for (std::size_t index : indexes) {
        const auto& point = points[index];
        std::string key = point.source->source_group_id;
        if (key.empty()) key = "time:" + std::to_string(point.source->support_center_utc_ns);
        auto found = best.find(key);
        const auto rank = std::make_tuple(-point.weight, std::abs(residuals[index]),
                                          point.source->candidate_id);
        if (found == best.end()) {
            best.emplace(std::move(key), index);
        } else {
            const std::size_t previous = found->second;
            const auto previous_rank = std::make_tuple(-points[previous].weight,
                std::abs(residuals[previous]), points[previous].source->candidate_id);
            if (rank < previous_rank) found->second = index;
        }
    }
    std::vector<std::size_t> result;
    result.reserve(best.size());
    for (const auto& item : best) result.push_back(item.second);
    std::sort(result.begin(), result.end(), [&](std::size_t a, std::size_t b) {
        return std::tie(points[a].time_s, points[a].source->candidate_id) <
               std::tie(points[b].time_s, points[b].source->candidate_id);
    });
    return result;
}

std::vector<std::vector<std::size_t>> split_contiguous(const std::vector<std::size_t>& indexes,
                                                        const std::vector<Point>& points,
                                                        double maximum_gap_s) {
    std::vector<std::vector<std::size_t>> result;
    for (std::size_t index : indexes) {
        if (result.empty() || points[index].time_s - points[result.back().back()].time_s > maximum_gap_s)
            result.emplace_back();
        result.back().push_back(index);
    }
    return result;
}

Segment fit_segment(const std::vector<std::size_t>& indexes, const std::vector<Point>& points,
                    double initial_slope, double initial_intercept, double spacing) {
    double sum_weight = 0.0;
    double weighted_time = 0.0;
    for (auto index : indexes) {
        const double weight = std::max(points[index].weight, std::numeric_limits<double>::epsilon());
        sum_weight += weight;
        weighted_time += weight * points[index].time_s;
    }
    const double t0 = weighted_time / sum_weight;
    double slope = initial_slope;
    double intercept_at_t0 = initial_intercept + initial_slope * t0;
    for (int iteration = 0; iteration < 4; ++iteration) {
        double sxx=0.0, sx=0.0, sw=0.0, sxy=0.0, sy=0.0;
        for (auto index : indexes) {
            const auto& point=points[index];
            const double weight=std::max(point.weight,std::numeric_limits<double>::epsilon());
            const double x=point.time_s-t0;
            const double prediction=intercept_at_t0+slope*x;
            const double lifted=point.frequency_hz-std::nearbyint((point.frequency_hz-prediction)/spacing)*spacing;
            sxx+=weight*x*x; sx+=weight*x; sw+=weight; sxy+=weight*x*lifted; sy+=weight*lifted;
        }
        const double determinant=sxx*sw-sx*sx;
        if (std::abs(determinant) <= std::numeric_limits<double>::epsilon()) {
            slope=0.0; intercept_at_t0=sy/sw;
        } else {
            slope=(sxy*sw-sx*sy)/determinant;
            intercept_at_t0=(sxx*sy-sx*sxy)/determinant;
        }
    }
    const double intercept=positive_mod(intercept_at_t0-slope*t0,spacing);
    double weighted_square=0.0, max_residual=0.0;
    for (auto index : indexes) {
        const double residual=circular_residual(points[index].frequency_hz,
                                                slope*points[index].time_s+intercept,spacing);
        weighted_square+=std::max(points[index].weight,std::numeric_limits<double>::epsilon())*residual*residual;
        max_residual=std::max(max_residual,std::abs(residual));
    }
    Segment result;
    result.indexes=indexes;
    result.segment_id=segment_identity(indexes,points);
    result.start_s=points[indexes.front()].time_s;
    result.end_s=points[indexes.back()].time_s;
    result.weighted_support=sum_weight;
    result.slope=slope;
    result.intercept=intercept;
    result.residual_rms=std::sqrt(weighted_square/sum_weight);
    result.residual_max=max_residual;
    return result;
}

struct FitCacheStats {
    std::size_t hits{};
    std::size_t misses{};
    std::size_t stores{};
    std::size_t capacity_fallbacks{};
    std::size_t maximum_retained_bytes{};
};

FitCacheStats g_fit_cache_stats;

std::uint64_t fit_double_bits(double value) {
    std::uint64_t bits{};
    std::memcpy(&bits,&value,sizeof(bits));
    return bits;
}

std::uint64_t fit_key_hash(const std::vector<std::size_t>& indexes,
                           std::uint64_t slope,std::uint64_t intercept,
                           std::uint64_t spacing) {
    std::uint64_t hash=UINT64_C(1469598103934665603);
    const auto add=[&](std::uint64_t value) {
        for (unsigned byte=0;byte<8U;++byte) {
            hash^=(value>>(byte*8U))&UINT64_C(0xff);
            hash*=UINT64_C(1099511628211);
        }
    };
    add(indexes.size());
    for (const std::size_t index:indexes) add(index);
    add(slope); add(intercept); add(spacing);
    return hash;
}

class ExactFitCache {
public:
    static constexpr std::size_t kMaximumRetainedBytes=8U*1024U*1024U;
    static constexpr std::size_t kSlots=4096U;

    ExactFitCache():entries_(kSlots),retained_bytes_(
        entries_.capacity()*sizeof(Entry)) {
        g_fit_cache_stats.maximum_retained_bytes=std::max(
            g_fit_cache_stats.maximum_retained_bytes,retained_bytes_);
    }

    Segment get(const std::vector<std::size_t>& indexes,
                const std::vector<Point>& points,double initial_slope,
                double initial_intercept,double spacing) {
        const std::uint64_t slope_bits=fit_double_bits(initial_slope);
        const std::uint64_t intercept_bits=fit_double_bits(initial_intercept);
        const std::uint64_t spacing_bits=fit_double_bits(spacing);
        const std::uint64_t hash=fit_key_hash(indexes,slope_bits,
            intercept_bits,spacing_bits);
        std::size_t empty=kSlots;
        for (std::size_t probe=0;probe<kSlots;++probe) {
            const std::size_t slot=(static_cast<std::size_t>(hash)+probe)&
                (kSlots-1U);
            const Entry& entry=entries_[slot];
            if (!entry.used) { empty=slot; break; }
            if (entry.hash==hash && entry.slope_bits==slope_bits &&
                entry.intercept_bits==intercept_bits &&
                entry.spacing_bits==spacing_bits &&
                entry.segment.indexes==indexes) {
                ++g_fit_cache_stats.hits;
                return entry.segment;
            }
        }
        ++g_fit_cache_stats.misses;
        Segment result=fit_segment(indexes,points,initial_slope,
            initial_intercept,spacing);
        const std::size_t minimum_dynamic=indexes.size()*sizeof(std::size_t)+
            result.segment_id.size()+1U;
        if (empty==kSlots || minimum_dynamic>
                kMaximumRetainedBytes-retained_bytes_) {
            ++g_fit_cache_stats.capacity_fallbacks;
            return result;
        }
        Entry& entry=entries_[empty];
        entry.hash=hash;
        entry.slope_bits=slope_bits;
        entry.intercept_bits=intercept_bits;
        entry.spacing_bits=spacing_bits;
        entry.segment=result;
        const std::size_t actual_dynamic=
            entry.segment.indexes.capacity()*sizeof(std::size_t)+
            entry.segment.segment_id.capacity()+1U;
        if (actual_dynamic>kMaximumRetainedBytes-retained_bytes_) {
            entry=Entry{};
            ++g_fit_cache_stats.capacity_fallbacks;
            return result;
        }
        entry.used=true;
        retained_bytes_+=actual_dynamic;
        ++g_fit_cache_stats.stores;
        g_fit_cache_stats.maximum_retained_bytes=std::max(
            g_fit_cache_stats.maximum_retained_bytes,retained_bytes_);
        return result;
    }

private:
    struct Entry {
        bool used{};
        std::uint64_t hash{};
        std::uint64_t slope_bits{};
        std::uint64_t intercept_bits{};
        std::uint64_t spacing_bits{};
        Segment segment;
    };

    std::vector<Entry> entries_;
    std::size_t retained_bytes_{};
};

std::vector<Segment> candidate_segments(const std::vector<Point>& points,
                                        const std::vector<bool>& available,
                                        double slope, double intercept, const Config& config,
                                        double spacing,ExactFitCache& cache) {
    std::vector<double> residuals(points.size());
    std::vector<std::size_t> raw;
    for (std::size_t i=0;i<points.size();++i) {
        residuals[i]=circular_residual(points[i].frequency_hz,slope*points[i].time_s+intercept,spacing);
        if (available[i] && points[i].weight>=config.minimum_point_weight &&
            std::abs(residuals[i])<=config.residual_gate_hz) raw.push_back(i);
    }
    std::vector<Segment> output;
    for (const auto& contiguous : split_contiguous(one_per_source(raw,points,residuals),points,
                                                    config.maximum_gap_s)) {
        if (contiguous.size()<config.minimum_support ||
            points[contiguous.back()].time_s-points[contiguous.front()].time_s<config.minimum_span_s) continue;
        const Segment initial=fit_segment(contiguous,points,slope,intercept,spacing);
        if (initial.slope<config.minimum_slope_hz_per_s || initial.slope>config.maximum_slope_hz_per_s) continue;
        std::vector<double> refined_residual(points.size());
        std::vector<std::size_t> refined_raw;
        for (std::size_t i=0;i<points.size();++i) {
            refined_residual[i]=circular_residual(points[i].frequency_hz,
                initial.slope*points[i].time_s+initial.intercept,spacing);
            if (available[i] && points[i].weight>=config.minimum_point_weight &&
                points[i].time_s>=initial.start_s && points[i].time_s<=initial.end_s &&
                std::abs(refined_residual[i])<=config.residual_gate_hz) refined_raw.push_back(i);
        }
        for (const auto& refined : split_contiguous(one_per_source(refined_raw,points,refined_residual),
                                                     points,config.maximum_gap_s)) {
            if (refined.size()>=config.minimum_support &&
                points[refined.back()].time_s-points[refined.front()].time_s>=config.minimum_span_s)
                output.push_back(cache.get(refined,points,initial.slope,
                    initial.intercept,spacing));
        }
    }
    return output;
}

bool better_segment(const Segment& a, const Segment& b) {
    return std::make_tuple(a.weighted_support,a.end_s-a.start_s,a.indexes.size(),-a.residual_rms,a.segment_id) >
           std::make_tuple(b.weighted_support,b.end_s-b.start_s,b.indexes.size(),-b.residual_rms,b.segment_id);
}

std::vector<Track> reconstruct_lane(const LaneKey& lane,
                                    std::vector<const Candidate*> candidates,
                                    const Config& config,
                                    const BinView* persistent_bins = nullptr) {
    std::sort(candidates.begin(),candidates.end(),[](const Candidate* a,const Candidate* b){
        return std::tie(a->support_center_utc_ns,a->measured_cfo_hz,a->candidate_id) <
               std::tie(b->support_center_utc_ns,b->measured_cfo_hz,b->candidate_id);
    });
    const std::int64_t reference=candidates.front()->support_center_utc_ns;
    const double scale=config.canonical_rf_hz/lane.actual_rf_hz;
    const double spacing=config.alias_spacing_hz*scale;
    std::vector<Point> points;
    points.reserve(candidates.size());
    for (const Candidate* item:candidates) points.push_back(Point{item,
        (item->support_center_utc_ns-reference)/kNsPerSecond,item->measured_cfo_hz*scale,
        evidence_weight(*item)});
    std::vector<bool> available(points.size());
    std::transform(points.begin(),points.end(),available.begin(),[&](const Point& p){return p.weight>=config.minimum_point_weight;});
    std::vector<Track> output;
    const double slope_step=(config.maximum_slope_hz_per_s-config.minimum_slope_hz_per_s)/
                            static_cast<double>(config.slope_bins-1);
    const double bin_width=spacing/static_cast<double>(config.intercept_bins);
    const detail::HoughBin hough_bin(spacing,bin_width,config.intercept_bins);
    constexpr std::size_t kMaximumBinCacheBytes=32U*1024U*1024U;
    std::vector<std::uint16_t> bin_indexes;
    const std::size_t initially_available=static_cast<std::size_t>(
        std::count(available.begin(),available.end(),true));
    if (!persistent_bins && initially_available>=config.minimum_support &&
        config.intercept_bins<=static_cast<std::size_t>(
            std::numeric_limits<std::uint16_t>::max())+1U &&
        (points.empty() || config.slope_bins<=
            std::numeric_limits<std::size_t>::max()/points.size())) {
        const std::size_t entries=config.slope_bins*points.size();
        if (entries<=kMaximumBinCacheBytes/sizeof(std::uint16_t)) {
            try {
                bin_indexes.resize(entries);
                for (std::size_t si=0;si<config.slope_bins;++si) {
                    const double slope=config.minimum_slope_hz_per_s+slope_step*si;
                    for (std::size_t index=0;index<points.size();++index) {
                        if (!available[index]) continue;
                        const std::size_t bin=hough_bin(points[index].frequency_hz-
                            slope*points[index].time_s);
                        bin_indexes[si*points.size()+index]=
                            static_cast<std::uint16_t>(bin);
                    }
                }
            } catch (const std::bad_alloc&) {
                bin_indexes.clear();
            }
        }
    }
    const BinView* bin_view=persistent_bins;
    ExactFitCache fit_cache;
    struct Peak { double value; std::size_t index; };
    auto better_peak=[](const Peak& a,const Peak& b){return a.value>b.value || (a.value==b.value && a.index>b.index);};
    for (std::size_t track_index=0;track_index<config.maximum_tracks_per_lane;++track_index) {
        std::vector<std::size_t> chosen;
        for (std::size_t i=0;i<available.size();++i) if (available[i]) chosen.push_back(i);
        if (chosen.size()<config.minimum_support) break;
        std::priority_queue<Peak,std::vector<Peak>,decltype(better_peak)> peaks(better_peak);
        std::vector<double> bins(config.intercept_bins);
        for (std::size_t si=0;si<config.slope_bins;++si) {
            std::fill(bins.begin(),bins.end(),0.0);
            const double slope=config.minimum_slope_hz_per_s+slope_step*si;
            if (!bin_view) {
                for (auto index:chosen) {
                    const std::size_t bin=bin_indexes.empty()
                        ?hough_bin(points[index].frequency_hz-slope*points[index].time_s)
                        :bin_indexes[si*points.size()+index];
                    bins[bin]+=points[index].weight;
                }
            } else {
                std::size_t chunk_index=0;
                for (auto index:chosen) {
                    while (chunk_index<bin_view->chunks->size() &&
                        index>=(*bin_view->chunks)[chunk_index].first_point+
                            (*bin_view->chunks)[chunk_index].point_count)
                        ++chunk_index;
                    if (chunk_index>=bin_view->chunks->size() ||
                        index<(*bin_view->chunks)[chunk_index].first_point)
                        throw std::logic_error("persistent bin cache has a gap");
                    const std::size_t bin=(*bin_view->chunks)[chunk_index].values[
                        si*(*bin_view->chunks)[chunk_index].point_count+
                        index-(*bin_view->chunks)[chunk_index].first_point];
                    bins[bin]+=points[index].weight;
                }
            }
            for (std::size_t bi=0;bi<config.intercept_bins;++bi) {
                Peak candidate{bins[bi],si*config.intercept_bins+bi};
                if (peaks.size()<config.peak_candidates) peaks.push(candidate);
                else if (better_peak(candidate,peaks.top())) {peaks.pop();peaks.push(candidate);}
            }
        }
        std::vector<Peak> ordered_peaks;
        while (!peaks.empty()) {ordered_peaks.push_back(peaks.top());peaks.pop();}
        std::sort(ordered_peaks.begin(),ordered_peaks.end(),better_peak);
        std::vector<Segment> hypotheses;
        for (const Peak& peak:ordered_peaks) {
            const std::size_t si=peak.index/config.intercept_bins;
            const std::size_t bi=peak.index%config.intercept_bins;
            const double slope=config.minimum_slope_hz_per_s+slope_step*si;
            const double intercept=(static_cast<double>(bi)+0.5)*bin_width;
            auto candidates_for_peak=candidate_segments(points,available,slope,
                intercept,config,spacing,fit_cache);
            hypotheses.insert(hypotheses.end(),candidates_for_peak.begin(),candidates_for_peak.end());
        }
        if (hypotheses.empty()) break;
        const Segment& segment=*std::max_element(hypotheses.begin(),hypotheses.end(),
            [](const Segment& a,const Segment& b){return better_segment(b,a);});
        Track track;
        track.segment_id=segment.segment_id;
        track.tracklet_id=tracklet_identity(lane,segment,points,config);
        track.lane=Lane{lane.channel,lane.edge,lane.receiver_id,lane.actual_rf_hz};
        track.reference_utc_ns=reference;
        track.normalized_rate_hz_per_s=segment.slope;
        track.normalized_intercept_hz=segment.intercept;
        track.residual_rms_hz=segment.residual_rms;
        track.residual_max_hz=segment.residual_max;
        track.weighted_support=segment.weighted_support;
        track.start_utc_ns=std::numeric_limits<std::int64_t>::max();
        track.end_utc_ns=std::numeric_limits<std::int64_t>::min();
        for (auto index:segment.indexes) {
            const auto& point=points[index];
            const int alias=static_cast<int>(std::nearbyint((point.frequency_hz-
                (segment.slope*point.time_s+segment.intercept))/spacing));
            track.points.push_back(TrackPoint{point.source->candidate_id,point.source->source_group_id,
                alias,point.frequency_hz,point.frequency_hz-alias*spacing});
            track.start_utc_ns=std::min(track.start_utc_ns,point.source->support_start_utc_ns);
            track.end_utc_ns=std::max(track.end_utc_ns,point.source->support_end_utc_ns);
        }
        output.push_back(std::move(track));
        for (std::size_t i=0;i<points.size();++i) {
            const double residual=circular_residual(points[i].frequency_hz,
                segment.slope*points[i].time_s+segment.intercept,spacing);
            if (points[i].time_s>=segment.start_s && points[i].time_s<=segment.end_s &&
                std::abs(residual)<=config.residual_gate_hz) available[i]=false;
        }
    }
    return output;
}

void validate(const std::vector<Candidate>& candidates,const Config& config) {
    if (candidates.empty()) throw std::invalid_argument("tracking input is empty");
    if (candidates.size()>config.maximum_input_points) throw std::invalid_argument("tracking input exceeds work bound");
    const std::array<double,10> config_values{config.canonical_rf_hz,config.alias_spacing_hz,
        config.minimum_slope_hz_per_s,config.maximum_slope_hz_per_s,config.residual_gate_hz,
        config.maximum_gap_s,config.minimum_span_s,config.minimum_point_weight,
        config.cross_lane_minimum_overlap_s,config.cross_lane_rate_gate_hz_per_s};
    if (std::any_of(config_values.begin(),config_values.end(),[](double v){return !std::isfinite(v);}) ||
        config.canonical_rf_hz<=0 || config.alias_spacing_hz<=0 || config.residual_gate_hz<=0 ||
        config.maximum_gap_s<=0 || config.minimum_span_s<=0 || config.minimum_point_weight<=0 ||
        config.minimum_slope_hz_per_s>=config.maximum_slope_hz_per_s || config.slope_bins<2 ||
        config.intercept_bins<1 || config.peak_candidates<1 || config.minimum_support<1 ||
        config.maximum_tracks_per_lane<1 || config.maximum_input_points<1 ||
        config.maximum_candidates_per_source_group<1 || config.maximum_trajectory_hypotheses<1 ||
        config.cross_lane_minimum_overlap_s<=0 || config.cross_lane_rate_gate_hz_per_s<=0)
        throw std::invalid_argument("invalid tracking config");
    std::set<std::string> ids;
    std::map<std::string,std::tuple<int,int,std::string,double>> sources;
    std::map<std::string,std::size_t> source_counts;
    for (const auto& c:candidates) {
        if (!tagged_digest(c.candidate_id) || !tagged_digest(c.source_group_id) ||
            !ids.insert(c.candidate_id).second)
            throw std::invalid_argument("candidate/source identities must be unique SHA-256 digests");
        const std::array<double,5> values{c.actual_rf_hz,c.measured_cfo_hz,c.exact_score,c.control_score,c.margin};
        if (std::any_of(values.begin(),values.end(),[](double v){return !std::isfinite(v);}) ||
            c.actual_rf_hz<=0 || c.channel<1 || c.receiver_id<0 ||
            (c.edge!="lower" && c.edge!="upper") ||
            c.support_start_utc_ns<=0 || c.support_start_utc_ns>c.support_center_utc_ns ||
            c.support_center_utc_ns>=c.support_end_utc_ns || c.margin<=0 ||
            std::abs(c.margin-(c.exact_score-c.control_score))>
                std::max(1e-12,1e-12*std::max(std::abs(c.margin),std::abs(c.exact_score-c.control_score))))
            throw std::invalid_argument("candidate geometry or scores are invalid");
        const auto binding=std::make_tuple(c.receiver_id,c.channel,c.edge,c.actual_rf_hz);
        auto inserted=sources.emplace(c.source_group_id,binding);
        if (!inserted.second && inserted.first->second!=binding)
            throw std::invalid_argument("source group spans multiple RF observations");
        if (++source_counts[c.source_group_id]>config.maximum_candidates_per_source_group)
            throw std::invalid_argument("source-group candidate fan-out exceeds work bound");
    }
}

bool same_double(double left,double right) {
    std::uint64_t left_bits=0,right_bits=0;
    static_assert(sizeof(left_bits)==sizeof(left));
    std::memcpy(&left_bits,&left,sizeof(left));
    std::memcpy(&right_bits,&right,sizeof(right));
    return left_bits==right_bits;
}

bool same_candidate(const Candidate& left,const Candidate& right) {
    return left.candidate_id==right.candidate_id &&
        left.source_group_id==right.source_group_id &&
        left.receiver_id==right.receiver_id && left.channel==right.channel &&
        left.edge==right.edge && same_double(left.actual_rf_hz,right.actual_rf_hz) &&
        left.support_start_utc_ns==right.support_start_utc_ns &&
        left.support_center_utc_ns==right.support_center_utc_ns &&
        left.support_end_utc_ns==right.support_end_utc_ns &&
        same_double(left.measured_cfo_hz,right.measured_cfo_hz) &&
        same_double(left.exact_score,right.exact_score) &&
        same_double(left.control_score,right.control_score) &&
        same_double(left.margin,right.margin);
}

bool same_config(const Config& left,const Config& right) {
    return same_double(left.canonical_rf_hz,right.canonical_rf_hz) &&
        same_double(left.alias_spacing_hz,right.alias_spacing_hz) &&
        same_double(left.minimum_slope_hz_per_s,right.minimum_slope_hz_per_s) &&
        same_double(left.maximum_slope_hz_per_s,right.maximum_slope_hz_per_s) &&
        same_double(left.residual_gate_hz,right.residual_gate_hz) &&
        same_double(left.maximum_gap_s,right.maximum_gap_s) &&
        same_double(left.minimum_span_s,right.minimum_span_s) &&
        left.minimum_support==right.minimum_support &&
        same_double(left.minimum_point_weight,right.minimum_point_weight) &&
        left.slope_bins==right.slope_bins &&
        left.intercept_bins==right.intercept_bins &&
        left.peak_candidates==right.peak_candidates &&
        left.maximum_tracks_per_lane==right.maximum_tracks_per_lane &&
        left.maximum_input_points==right.maximum_input_points &&
        left.maximum_candidates_per_source_group==right.maximum_candidates_per_source_group &&
        left.maximum_trajectory_hypotheses==right.maximum_trajectory_hypotheses &&
        same_double(left.cross_lane_minimum_overlap_s,right.cross_lane_minimum_overlap_s) &&
        same_double(left.cross_lane_rate_gate_hz_per_s,right.cross_lane_rate_gate_hz_per_s);
}

using LaneRows=std::map<LaneKey,std::vector<const Candidate*>>;

LaneRows ordered_lanes(const std::vector<Candidate>& candidates) {
    LaneRows lanes;
    for (const auto& candidate:candidates)
        lanes[{candidate.channel,candidate.edge,candidate.receiver_id,
            candidate.actual_rf_hz}].push_back(&candidate);
    for (auto& [lane,rows]:lanes) {
        (void)lane;
        std::sort(rows.begin(),rows.end(),[](const Candidate* left,
                                            const Candidate* right) {
            return std::tie(left->support_center_utc_ns,left->measured_cfo_hz,
                       left->candidate_id) <
                std::tie(right->support_center_utc_ns,right->measured_cfo_hz,
                       right->candidate_id);
        });
    }
    return lanes;
}

struct CachedLane {
    std::int64_t reference_utc_ns{};
    double scale{};
    double spacing{};
    double slope_step{};
    double bin_width{};
    std::vector<std::size_t> ordered_input_indexes;
    std::vector<BinChunk> chunks;
    std::size_t cached_points{};
};

bool exact_candidate_prefix(const std::vector<Candidate>& previous,
                            const std::vector<Candidate>& current) {
    if (previous.size()>current.size()) return false;
    for (std::size_t index=0;index<previous.size();++index)
        if (!same_candidate(previous[index],current[index])) return false;
    return true;
}

std::vector<std::size_t> input_indexes(const std::vector<Candidate>& candidates,
                                       const std::vector<const Candidate*>& rows) {
    std::vector<std::size_t> indexes;
    indexes.reserve(rows.size());
    for (const Candidate* row:rows)
        indexes.push_back(static_cast<std::size_t>(row-candidates.data()));
    return indexes;
}

bool exact_index_prefix(const std::vector<std::size_t>& previous,
                        const std::vector<std::size_t>& current) {
    return previous.size()<=current.size() &&
        std::equal(previous.begin(),previous.end(),current.begin());
}

bool cache_geometry_supported(const Config& config,std::size_t points) {
    return config.intercept_bins<=static_cast<std::size_t>(
            std::numeric_limits<std::uint16_t>::max())+1U &&
        (points==0 || config.slope_bins<=
            std::numeric_limits<std::size_t>::max()/points);
}

BinChunk make_bin_chunk(const LaneKey& lane,
                        const std::vector<const Candidate*>& rows,
                        std::size_t first,const Config& config,
                        const CachedLane& cached) {
    BinChunk chunk;
    chunk.first_point=first;
    chunk.point_count=rows.size()-first;
    if (!chunk.point_count) return chunk;
    if (!cache_geometry_supported(config,chunk.point_count))
        throw std::length_error("persistent tracking cache geometry unsupported");
    chunk.values.resize(config.slope_bins*chunk.point_count);
    const detail::HoughBin hough_bin(cached.spacing,cached.bin_width,
        config.intercept_bins);
    for (std::size_t si=0;si<config.slope_bins;++si) {
        const double slope=config.minimum_slope_hz_per_s+cached.slope_step*si;
        for (std::size_t local=0;local<chunk.point_count;++local) {
            const Candidate& candidate=*rows[first+local];
            if (evidence_weight(candidate)<config.minimum_point_weight) continue;
            const double time_s=(candidate.support_center_utc_ns-
                cached.reference_utc_ns)/kNsPerSecond;
            const double frequency_hz=candidate.measured_cfo_hz*cached.scale;
            const std::size_t bin=hough_bin(frequency_hz-slope*time_s);
            chunk.values[si*chunk.point_count+local]=
                static_cast<std::uint16_t>(bin);
        }
    }
    (void)lane;
    return chunk;
}

std::size_t add_saturating(std::size_t left,std::size_t right) {
    return right>std::numeric_limits<std::size_t>::max()-left ?
        std::numeric_limits<std::size_t>::max() : left+right;
}

std::size_t candidate_storage(const std::vector<Candidate>& candidates) {
    std::size_t bytes=candidates.capacity()*sizeof(Candidate);
    for (const Candidate& candidate:candidates) {
        bytes=add_saturating(bytes,candidate.candidate_id.capacity()+1U);
        bytes=add_saturating(bytes,candidate.source_group_id.capacity()+1U);
        bytes=add_saturating(bytes,candidate.edge.capacity()+1U);
    }
    return bytes;
}

std::size_t minimum_candidate_copy_storage(
    const std::vector<Candidate>& candidates) {
    std::size_t bytes=candidates.size()*sizeof(Candidate);
    for (const Candidate& candidate:candidates) {
        bytes=add_saturating(bytes,candidate.candidate_id.size()+1U);
        bytes=add_saturating(bytes,candidate.source_group_id.size()+1U);
        bytes=add_saturating(bytes,candidate.edge.size()+1U);
    }
    return bytes;
}

std::size_t bin_cells(const std::vector<const Candidate*>& rows,
                      std::size_t first,const Config& config) {
    std::size_t eligible=0;
    for (std::size_t index=first;index<rows.size();++index)
        if (evidence_weight(*rows[index])>=config.minimum_point_weight) ++eligible;
    if (eligible && config.slope_bins>
        std::numeric_limits<std::size_t>::max()/eligible)
        return std::numeric_limits<std::size_t>::max();
    return eligible*config.slope_bins;
}

std::size_t allocated_bin_cells(const std::vector<const Candidate*>& rows,
                                std::size_t first,const Config& config) {
    const std::size_t points=rows.size()-first;
    if (points && config.slope_bins>
        std::numeric_limits<std::size_t>::max()/points)
        return std::numeric_limits<std::size_t>::max();
    return points*config.slope_bins;
}

std::size_t minimum_cache_storage(const std::vector<Candidate>& candidates,
                                  const LaneRows& lanes,const Config& config) {
    std::size_t bytes=minimum_candidate_copy_storage(candidates);
    for (const auto& [key,rows]:lanes) {
        bytes=add_saturating(bytes,sizeof(CachedLane)+sizeof(LaneKey)+
            4U*sizeof(void*)+key.edge.size()+1U);
        bytes=add_saturating(bytes,rows.size()*sizeof(std::size_t));
        const std::size_t eligible=static_cast<std::size_t>(
            std::count_if(rows.begin(),rows.end(),[&](const Candidate* item) {
                return evidence_weight(*item)>=config.minimum_point_weight;
            }));
        if (eligible>=config.minimum_support) {
            if (!cache_geometry_supported(config,rows.size()))
                return std::numeric_limits<std::size_t>::max();
            const std::size_t cells=config.slope_bins*rows.size();
            if (cells>std::numeric_limits<std::size_t>::max()/
                sizeof(std::uint16_t))
                return std::numeric_limits<std::size_t>::max();
            bytes=add_saturating(bytes,sizeof(BinChunk));
            bytes=add_saturating(bytes,cells*sizeof(std::uint16_t));
        }
    }
    return bytes;
}

std::size_t lane_storage(const LaneKey& key,const CachedLane& lane) {
    std::size_t bytes=sizeof(CachedLane)+sizeof(LaneKey)+4U*sizeof(void*);
    bytes=add_saturating(bytes,key.edge.capacity()+1U);
    bytes=add_saturating(bytes,lane.ordered_input_indexes.capacity()*
        sizeof(std::size_t));
    bytes=add_saturating(bytes,lane.chunks.capacity()*sizeof(BinChunk));
    for (const BinChunk& chunk:lane.chunks)
        bytes=add_saturating(bytes,chunk.values.capacity()*
            sizeof(std::uint16_t));
    return bytes;
}

std::size_t cache_storage(const std::vector<Candidate>& candidates,
                          const std::map<LaneKey,CachedLane>& lanes) {
    std::size_t bytes=candidate_storage(candidates);
    for (const auto& [key,lane]:lanes)
        bytes=add_saturating(bytes,lane_storage(key,lane));
    return bytes;
}

template <typename CacheMap>
Result result_from_lanes(const LaneRows& lanes,const Config& config,
                         const CacheMap* cache) {
    Result result;
    for (const auto& [lane,rows]:lanes) {
        BinView view;
        const BinView* selected=nullptr;
        if (cache) {
            const auto found=cache->find(lane);
            if (found!=cache->end() && found->second.cached_points==rows.size() &&
                !found->second.chunks.empty()) {
                view.chunks=&found->second.chunks;
                selected=&view;
            }
        }
        auto tracks=reconstruct_lane(lane,rows,config,selected);
        result.tracks.insert(result.tracks.end(),
            std::make_move_iterator(tracks.begin()),
            std::make_move_iterator(tracks.end()));
    }
    result.config_digest=is_deployment_profile(config) ? kDeploymentConfigDigest : "";
    std::sort(result.tracks.begin(),result.tracks.end(),[](const Track& left,
                                                          const Track& right) {
        return std::tie(left.start_utc_ns,left.segment_id)<
            std::tie(right.start_utc_ns,right.segment_id);
    });
    std::set<std::string> used;
    for (const auto& track:result.tracks)
        for (const auto& point:track.points) used.insert(point.candidate_id);
    result.used_candidate_count=used.size();
    return result;
}

}  // namespace

Result reconstruct(const std::vector<Candidate>& candidates,const Config& config) {
    validate(candidates,config);
    const LaneRows lanes=ordered_lanes(candidates);
    Result result=result_from_lanes(lanes,config,
        static_cast<const std::map<LaneKey,CachedLane>*>(nullptr));
    result.input_candidate_count=candidates.size();
    std::cerr << "FIT_CACHE {\"maximum_retained_bytes_per_lane\":"
              << ExactFitCache::kMaximumRetainedBytes
              << ",\"maximum_observed_retained_bytes\":"
              << g_fit_cache_stats.maximum_retained_bytes
              << ",\"hits\":" << g_fit_cache_stats.hits
              << ",\"misses\":" << g_fit_cache_stats.misses
              << ",\"stores\":" << g_fit_cache_stats.stores
              << ",\"capacity_fallbacks\":"
              << g_fit_cache_stats.capacity_fallbacks << "}\n";
    return result;
}

struct Reconstructor::Impl {
    explicit Impl(std::size_t maximum):maximum_bytes(maximum) {
        statistics.maximum_cache_bytes=maximum;
    }

    std::size_t maximum_bytes;
    bool have_config{};
    Config config;
    std::vector<Candidate> candidates;
    std::map<LaneKey,CachedLane> lanes;
    ReconstructorStats statistics;

    void drop_cache() {
        have_config=false;
        std::vector<Candidate>().swap(candidates);
        lanes.clear();
        statistics.resident_cache_bytes=0;
        statistics.cached_lanes=0;
    }

    bool seed(const std::vector<Candidate>& current,const Config& next_config,
              const LaneRows& current_lanes) {
        if (minimum_cache_storage(current,current_lanes,next_config)>
            maximum_bytes) return false;
        try {
            std::vector<Candidate> snapshot=current;
            if (candidate_storage(snapshot)>maximum_bytes) return false;
            std::map<LaneKey,CachedLane> replacement;
            for (const auto& [key,rows]:current_lanes) {
                CachedLane lane;
                lane.reference_utc_ns=rows.front()->support_center_utc_ns;
                lane.scale=next_config.canonical_rf_hz/key.actual_rf_hz;
                lane.spacing=next_config.alias_spacing_hz*lane.scale;
                lane.slope_step=(next_config.maximum_slope_hz_per_s-
                    next_config.minimum_slope_hz_per_s)/
                    static_cast<double>(next_config.slope_bins-1U);
                lane.bin_width=lane.spacing/
                    static_cast<double>(next_config.intercept_bins);
                lane.ordered_input_indexes=input_indexes(current,rows);
                const std::size_t eligible=static_cast<std::size_t>(
                    std::count_if(rows.begin(),rows.end(),[&](const Candidate* item) {
                        return evidence_weight(*item)>=next_config.minimum_point_weight;
                    }));
                if (eligible>=next_config.minimum_support) {
                    lane.chunks.push_back(make_bin_chunk(key,rows,0,next_config,lane));
                    statistics.last_bin_cells_computed=add_saturating(
                        statistics.last_bin_cells_computed,
                        bin_cells(rows,0,next_config));
                    lane.cached_points=rows.size();
                }
                replacement.emplace(key,std::move(lane));
                if (cache_storage(snapshot,replacement)>maximum_bytes)
                    return false;
            }
            const std::size_t resident=cache_storage(snapshot,replacement);
            if (resident>maximum_bytes) return false;
            candidates.swap(snapshot);
            lanes.swap(replacement);
            config=next_config;
            have_config=true;
            statistics.resident_cache_bytes=resident;
            statistics.cached_lanes=lanes.size();
            return true;
        } catch (const std::bad_alloc&) {
            return false;
        } catch (const std::length_error&) {
            return false;
        }
    }

    bool prefix_valid(const std::vector<Candidate>& current,
                      const Config& next_config,const LaneRows& current_lanes,
                      bool& config_changed) const {
        config_changed=have_config && !same_config(config,next_config);
        if (!have_config || config_changed ||
            !exact_candidate_prefix(candidates,current)) return false;
        for (const auto& [key,old_lane]:lanes) {
            const auto found=current_lanes.find(key);
            if (found==current_lanes.end()) return false;
            const auto indexes=input_indexes(current,found->second);
            if (!exact_index_prefix(old_lane.ordered_input_indexes,indexes) ||
                old_lane.reference_utc_ns!=found->second.front()->support_center_utc_ns)
                return false;
            const double scale=next_config.canonical_rf_hz/key.actual_rf_hz;
            const double spacing=next_config.alias_spacing_hz*scale;
            const double slope_step=(next_config.maximum_slope_hz_per_s-
                next_config.minimum_slope_hz_per_s)/
                static_cast<double>(next_config.slope_bins-1U);
            const double bin_width=spacing/
                static_cast<double>(next_config.intercept_bins);
            if (!same_double(old_lane.scale,scale) ||
                !same_double(old_lane.spacing,spacing) ||
                !same_double(old_lane.slope_step,slope_step) ||
                !same_double(old_lane.bin_width,bin_width)) return false;
        }
        return true;
    }

    bool extend(const std::vector<Candidate>& current,const Config& next_config,
                const LaneRows& current_lanes,std::size_t& reused,
                std::size_t& extended) {
        if (minimum_cache_storage(current,current_lanes,next_config)>
            maximum_bytes) return false;
        try {
            for (const auto& [key,rows]:current_lanes) {
                auto found=lanes.find(key);
                if (found==lanes.end()) {
                    CachedLane lane;
                    lane.reference_utc_ns=rows.front()->support_center_utc_ns;
                    lane.scale=next_config.canonical_rf_hz/key.actual_rf_hz;
                    lane.spacing=next_config.alias_spacing_hz*lane.scale;
                    lane.slope_step=(next_config.maximum_slope_hz_per_s-
                        next_config.minimum_slope_hz_per_s)/
                        static_cast<double>(next_config.slope_bins-1U);
                    lane.bin_width=lane.spacing/
                        static_cast<double>(next_config.intercept_bins);
                    found=lanes.emplace(key,std::move(lane)).first;
                }
                CachedLane& lane=found->second;
                const std::size_t old_points=lane.ordered_input_indexes.size();
                const auto indexes=input_indexes(current,rows);
                if (indexes.size()==old_points) {
                    ++reused;
                } else {
                    ++extended;
                    const std::size_t eligible=static_cast<std::size_t>(
                        std::count_if(rows.begin(),rows.end(),[&](const Candidate* item) {
                            return evidence_weight(*item)>=
                                next_config.minimum_point_weight;
                        }));
                    if (eligible>=next_config.minimum_support) {
                        const std::size_t first=lane.cached_points;
                        if (first<rows.size()) {
                            const std::size_t allocated_cells=allocated_bin_cells(
                                rows,first,next_config);
                            if (allocated_cells==
                                    std::numeric_limits<std::size_t>::max() ||
                                allocated_cells>std::numeric_limits<std::size_t>::max()/
                                    sizeof(std::uint16_t)) return false;
                            std::size_t resident=cache_storage(candidates,lanes);
                            const std::size_t value_bytes=allocated_cells*
                                sizeof(std::uint16_t);
                            const std::size_t metadata_bytes=
                                (lane.chunks.size()==lane.chunks.capacity()) ?
                                (lane.chunks.capacity() ? 2U*lane.chunks.capacity() : 1U)*
                                    sizeof(BinChunk) : 0U;
                            if (add_saturating(add_saturating(resident,value_bytes),
                                    metadata_bytes)>maximum_bytes) return false;
                            BinChunk chunk=make_bin_chunk(key,rows,first,
                                next_config,lane);
                            if (add_saturating(resident,
                                    chunk.values.capacity()*sizeof(std::uint16_t))>
                                maximum_bytes) return false;
                            lane.chunks.push_back(std::move(chunk));
                            statistics.last_bin_cells_computed=add_saturating(
                                statistics.last_bin_cells_computed,
                                bin_cells(rows,first,next_config));
                            lane.cached_points=rows.size();
                        }
                    }
                }
                if (lane.ordered_input_indexes.capacity()<indexes.size()) {
                    const std::size_t resident=cache_storage(candidates,lanes);
                    if (add_saturating(resident,indexes.size()*sizeof(std::size_t))>
                        maximum_bytes) return false;
                    lane.ordered_input_indexes.reserve(indexes.size());
                }
                lane.ordered_input_indexes.insert(lane.ordered_input_indexes.end(),
                    indexes.begin()+static_cast<std::ptrdiff_t>(old_points),
                    indexes.end());
            }
            if (candidates.capacity()<current.size()) {
                std::size_t resident=cache_storage(candidates,lanes);
                const std::size_t new_objects=current.size()*sizeof(Candidate);
                if (add_saturating(resident,new_objects)>maximum_bytes) return false;
                candidates.reserve(current.size());
            }
            std::size_t new_string_bytes=0;
            for (std::size_t index=candidates.size();index<current.size();++index) {
                new_string_bytes=add_saturating(new_string_bytes,
                    current[index].candidate_id.size()+1U);
                new_string_bytes=add_saturating(new_string_bytes,
                    current[index].source_group_id.size()+1U);
                new_string_bytes=add_saturating(new_string_bytes,
                    current[index].edge.size()+1U);
            }
            if (add_saturating(cache_storage(candidates,lanes),new_string_bytes)>
                maximum_bytes) return false;
            candidates.insert(candidates.end(),
                current.begin()+static_cast<std::ptrdiff_t>(candidates.size()),
                current.end());
            const std::size_t resident=cache_storage(candidates,lanes);
            if (resident>maximum_bytes) return false;
            statistics.resident_cache_bytes=resident;
            statistics.cached_lanes=lanes.size();
            return true;
        } catch (const std::bad_alloc&) {
            return false;
        } catch (const std::length_error&) {
            return false;
        }
    }
};

Reconstructor::Reconstructor(std::size_t maximum_cache_bytes)
    :impl_(std::make_unique<Impl>(maximum_cache_bytes)) {
    if (!maximum_cache_bytes)
        throw std::invalid_argument("persistent tracking cache budget is zero");
}

Reconstructor::~Reconstructor()=default;
Reconstructor::Reconstructor(Reconstructor&&) noexcept=default;
Reconstructor& Reconstructor::operator=(Reconstructor&&) noexcept=default;

Result Reconstructor::reconstruct(const std::vector<Candidate>& current,
                                  const Config& next_config) {
    validate(current,next_config);
    const LaneRows current_lanes=ordered_lanes(current);
    impl_->statistics.last_reused_lanes=0;
    impl_->statistics.last_extended_lanes=0;
    impl_->statistics.last_bin_cells_computed=0;
    impl_->statistics.last_cold_fallback=false;
    bool config_changed=false;
    if (!impl_->prefix_valid(current,next_config,current_lanes,config_changed)) {
        if (!impl_->have_config) ++impl_->statistics.cold_starts;
        else if (config_changed) ++impl_->statistics.config_invalidations;
        else ++impl_->statistics.prefix_invalidations;
        impl_->statistics.last_cold_fallback=true;
        /* Release the invalid persistent cache before the stateless lane cache
         * is built; their allocation bounds must not overlap. */
        impl_->drop_cache();
        Result result=tracking::reconstruct(current,next_config);
        if (!impl_->seed(current,next_config,current_lanes)) {
            ++impl_->statistics.capacity_fallbacks;
            impl_->drop_cache();
        }
        return result;
    }
    std::size_t reused=0,extended=0;
    if (!impl_->extend(current,next_config,current_lanes,reused,extended)) {
        ++impl_->statistics.capacity_fallbacks;
        impl_->statistics.last_cold_fallback=true;
        impl_->drop_cache();
        return tracking::reconstruct(current,next_config);
    }
    impl_->statistics.last_reused_lanes=reused;
    impl_->statistics.last_extended_lanes=extended;
    Result result=result_from_lanes(current_lanes,next_config,&impl_->lanes);
    result.input_candidate_count=current.size();
    return result;
}

void Reconstructor::clear() {
    impl_->drop_cache();
    impl_->statistics.last_reused_lanes=0;
    impl_->statistics.last_extended_lanes=0;
    impl_->statistics.last_bin_cells_computed=0;
    impl_->statistics.last_cold_fallback=false;
}

ReconstructorStats Reconstructor::stats() const {
    return impl_->statistics;
}

}  // namespace leo::adaptive::tracking
