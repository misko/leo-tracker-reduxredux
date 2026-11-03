#include "../../../native/adaptive/application/recorded_bundle.hpp"
#include "../../../native/adaptive/runtime/sha256.hpp"

#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

using namespace leo::adaptive;
using namespace leo::adaptive::application;

namespace {
constexpr const char* analysis =
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const std::string valid_tsv =
    "FORMAT\tleo-recorded-ds9/v1\n"
    "SESSION\tscan-fw-unit\t17387150650040770497\t12478478914259975484\t"
    "7500000\t2\t7500000\t"
    "5b8755586b9a84444ea3caf1bcb5cb0f6c6d80b7c9e3087666331608883de2bd\t"
    "fd3600ac892ca639aee514a947ec4b6de051571674631355a2f05da2460cf6aa\t"
    "2e0cc5446d88cc8bd56794ed10c5d27931654ed1a7ed09ee12a42bba710246c6\n"
    "TIMING\t1\t1239228236987690\t1239228602925352\t1247641617019\t"
    "1790557997116690851\t1790557997482631802\t365940951\n"
    "TARGET\t0\t0\t1\tlower\t960000000\t960000000\t10710000000\t"
    "959687500\t959687500\t-820312.5\t820312.5\t0\n"
    "VISIT\t301\t0\t0\t120\t1\t11\t0\t960000000\t960000000\t"
    "1247949281424\t1247949281424\t1247949437197\t1247949437197\t"
    "1247950337197\t"
    "40c56065e9d1f6b8e188e1d19a0be4b5663b12a1c074578c894979012b4a199d\t"
    "3530f06a807aec4f0d94cf1a7b58de928d6dc433d3310b70de1c5763d3364a6a\t"
    "7200000\traw/visit-000301.ci16\n";

void sparse(const std::string& path, std::uint64_t bytes) {
    std::ofstream output(path, std::ios::binary);
    assert(output);
    if (bytes) {
        output.seekp(static_cast<std::streamoff>(bytes - 1U));
        output.put('\0');
    }
    assert(output.good());
}

void write(const std::string& path, const std::string& bytes) {
    std::ofstream output(path, std::ios::binary);
    output.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    assert(output.good());
}

std::string replace_one(std::string value, const std::string& old,
                        const std::string& replacement) {
    const auto at = value.find(old);
    assert(at != std::string::npos);
    value.replace(at, old.size(), replacement);
    return value;
}

struct Fixture {
    std::string root, native, raw, outside;
    Fixture() {
        const char* temporary = std::getenv("TMPDIR");
        std::string pattern = std::string(temporary ? temporary : "/var/tmp") +
            "/leo-recorded-bundle-test-XXXXXX";
        std::vector<char> writable(pattern.begin(), pattern.end());
        writable.push_back('\0');
        assert(mkdtemp(writable.data()));
        root = writable.data(); native = root + "/native.tsv";
        assert(mkdir((root + "/raw").c_str(), 0700) == 0);
        raw = root + "/raw/visit-000301.ci16";
        outside = root + "-outside.ci16";
        sparse(raw, 7200000U); sparse(outside, 7200000U); write(native, valid_tsv);
    }
    ~Fixture() {
        (void)unlink((root + "/raw/escape.ci16").c_str());
        (void)unlink(raw.c_str()); (void)rmdir((root + "/raw").c_str());
        (void)unlink(native.c_str()); (void)rmdir(root.c_str());
        (void)unlink(outside.c_str());
    }
    RecordedBundleStatus read(const std::string& body, RecordedBundle& output) {
        write(native, body);
        return read_recorded_bundle(native, sha256(body), analysis, output);
    }
};

void valid_bundle_is_value_owned_and_consistent() {
    Fixture fixture; RecordedBundle bundle;
    assert(fixture.read(valid_tsv, bundle) == RecordedBundleStatus::ok);
    assert(bundle.session_id == "scan-fw-unit" && bundle.sample_rate_hz == 7500000U &&
        bundle.receiver_count == 2U && bundle.targets.size() == 1U &&
        bundle.plan_rows.size() == 1U && bundle.raw_files.size() == 1U);
    assert(bundle.timing.exact_counter && bundle.timing.counter == 1247641617019ULL &&
        bundle.timing_bracket_width_ns == 365940951ULL);
    char* resolved_raw = realpath(fixture.raw.c_str(), nullptr);
    assert(resolved_raw);
    const std::string expected_raw(resolved_raw);
    std::free(resolved_raw);
    assert(bundle.plan_rows[0].visit == 301U && bundle.plan_rows[0].target_index == 0U &&
        bundle.raw_files[0].visit == 301U &&
        bundle.raw_files[0].canonical_path == expected_raw);
    assert(bundle.corrected_geometry.target_count == 1U &&
        bundle.corrected_geometry.targets[0].target_key == bundle.targets[0].target_key &&
        bundle.corrected_geometry.targets[0].tuned_if_hz ==
            bundle.targets[0].actual_tuned_if_hz);
    assert(bundle.ingest_authority.profile_authority ==
        ingest::ProfileAuthority::historical_metadata &&
        bundle.ingest_authority.targets.size() == 1U &&
        bundle.ingest_authority.targets[0].profile == bundle.targets[0].target_key &&
        bundle.ingest_authority.targets[0].tuning_frequency_hz ==
            bundle.corrected_geometry.targets[0].tuned_if_hz &&
        bundle.ingest_authority.analysis_digest == analysis);
    leo_scanner_visit_authority visit{};
    visit.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    visit.session = bundle.scanner_session; visit.generation = bundle.generation;
    visit.visit = bundle.plan_rows[0].visit; visit.target_index = 0; visit.target_key = 0;
    visit.actual_frequency_hz = bundle.plan_rows[0].expected_actual_frequency_hz;
    visit.selection_counter = bundle.plan_rows[0].selection_counter;
    visit.transition_previous_valid_end = bundle.plan_rows[0].transition_previous_valid_end;
    visit.transition_valid_start = bundle.plan_rows[0].transition_valid_start;
    visit.valid_start = bundle.plan_rows[0].valid_start;
    visit.valid_end = bundle.plan_rows[0].valid_end;
    visit.transition_flags = bundle.plan_rows[0].expected_transition_flags;
    visit.sample_rate_hz = bundle.sample_rate_hz; visit.receiver_count = 2;
    visit.dwell_ms = 120; visit.probe_stride_ms = 120;
    leo_scanner_detector_geometry geometry{};
    assert(derive_corrected_geometry(&bundle.corrected_geometry, &visit, &geometry) == 0);
    assert(geometry.receiver_center_hz[0] == -312500.0 &&
        geometry.receiver_center_hz[1] == -312500.0 &&
        geometry.residual_cfo_min_hz == -800000.0 &&
        geometry.residual_cfo_max_hz == 800000.0);
}

void hash_is_checked_before_rows() {
    Fixture fixture; RecordedBundle output; output.session_id = "unchanged";
    write(fixture.native, "not a TSV\n");
    assert(read_recorded_bundle(fixture.native, std::string(64, 'a'), analysis, output) ==
        RecordedBundleStatus::digest_mismatch);
    assert(output.session_id == "unchanged");
    assert(read_recorded_bundle(fixture.native, "A" + std::string(63, 'a'), analysis,
        output) == RecordedBundleStatus::invalid_argument);
}

void malformed_authority_is_rejected() {
    struct Case { std::string old, replacement; RecordedBundleStatus status; };
    const std::array<Case, 12> cases{{
        {"leo-recorded-ds9/v1", "leo-recorded-ds9/v2", RecordedBundleStatus::malformed},
        {"\t7500000\t2\t", "\t07500000\t2\t", RecordedBundleStatus::malformed},
        {"TIMING\t1\t", "TIMING\t0\t", RecordedBundleStatus::malformed},
        {"1239228236987690\t1239228602925352", "18446744073709551615\t1239228602925352", RecordedBundleStatus::malformed},
        {"\t365940951\nTARGET", "\t365940950\nTARGET", RecordedBundleStatus::malformed},
        {"\t-820312.5\t", "\tnan\t", RecordedBundleStatus::malformed},
        {"\t960000000\t960000000\t10710000000", "\t960000000\t960000001\t10710000000", RecordedBundleStatus::malformed},
        {"\t820312.5\t0\nVISIT", "\t820312.5\t1\nVISIT", RecordedBundleStatus::malformed},
        {"\t120\t1\t11\t0\t", "\t120\t1\t15\t0\t", RecordedBundleStatus::malformed},
        {"\t1247950337197\t", "\t1247950337196\t", RecordedBundleStatus::malformed},
        {"\t7200000\traw/", "\t7199999\traw/", RecordedBundleStatus::malformed},
        {"raw/visit-000301.ci16", "../escape.ci16", RecordedBundleStatus::unsafe_path},
    }};
    for (const auto& item : cases) {
        Fixture fixture; RecordedBundle output;
        assert(fixture.read(replace_one(valid_tsv, item.old, item.replacement), output) ==
            item.status);
    }
}

void symlink_escape_and_size_bound_are_rejected() {
    Fixture fixture; RecordedBundle output;
    assert(symlink(fixture.outside.c_str(), (fixture.root + "/raw/escape.ci16").c_str()) == 0);
    const auto escaped = replace_one(valid_tsv, "raw/visit-000301.ci16",
        "raw/escape.ci16");
    assert(fixture.read(escaped, output) == RecordedBundleStatus::unsafe_path);
    sparse(fixture.native, 16U * 1024U * 1024U + 1U);
    assert(read_recorded_bundle(fixture.native, std::string(64, 'a'), analysis, output) ==
        RecordedBundleStatus::file_too_large);
}

void read_external(const char* path, const char* digest, std::size_t visits) {
    RecordedBundle bundle;
    assert(read_recorded_bundle(path, digest, analysis, bundle) == RecordedBundleStatus::ok);
    assert(bundle.plan_rows.size() == visits && bundle.raw_files.size() == visits);
}
}

int main(int argc, char** argv) {
    valid_bundle_is_value_owned_and_consistent();
    hash_is_checked_before_rows();
    malformed_authority_is_rejected();
    symlink_escape_and_size_bound_are_rejected();
    if (argc == 7) {
        read_external(argv[1], argv[2], static_cast<std::size_t>(std::stoul(argv[3])));
        read_external(argv[4], argv[5], static_cast<std::size_t>(std::stoul(argv[6])));
    } else assert(argc == 1);
    std::puts("recorded bundle reader tests passed");
}
