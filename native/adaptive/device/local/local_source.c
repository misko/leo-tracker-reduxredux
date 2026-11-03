#include "local_source.h"

#include "vendor/spf-scan-radio.h"

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

struct leo_local_source {
    struct leo_local_config config;
    struct leo_local_provider_ops provider;
    struct leo_local_owner *owner;
    void *capture;
    uint64_t previous_frame_end;
    uint64_t previous_buffer_sequence;
    uint64_t counter_anchor;
    uintptr_t outstanding_token;
    bool sequence_valid;
    bool primed;
    bool tuned;
    bool faulted;
};

struct leo_local_owner {
    struct leo_local_provider_ops provider;
    struct spf_scan_radio radio;
    int counter_fd;
    uint64_t counter_anchor;
    bool held;
};

static uint64_t read_le64(const void *wire)
{
    const uint8_t *p = wire;
    uint64_t value = 0;
    unsigned i;

    for (i = 0; i < 8; ++i)
        value |= (uint64_t)p[i] << (8U * i);
    return value;
}

static bool config_valid(const struct leo_local_config *config)
{
    uint32_t seen = 0;
    unsigned i;

    if (!config || !config->sample_rate_hz || !config->analog_bandwidth_hz ||
        !config->samples_per_block || (config->samples_per_block & 1U) ||
        (config->receiver_count != 1U && config->receiver_count != 2U) ||
        config->kernel_buffer_count < 4U || config->kernel_buffer_count > 64U ||
        !config->profile_count || config->profile_count > LEO_LOCAL_MAX_PROFILES)
        return false;
    for (i = 0; i < config->profile_count; ++i) {
        const struct leo_local_profile *profile = &config->profiles[i];

        if (profile->profile >= LEO_LOCAL_MAX_PROFILES || !profile->frequency_hz ||
            (seen & (UINT32_C(1) << profile->profile)))
            return false;
        seen |= UINT32_C(1) << profile->profile;
    }
    return true;
}

static bool provider_valid(const struct leo_local_provider_ops *provider)
{
    return provider && provider->capture_open && provider->capture_acquire &&
        provider->capture_cancel &&
        provider->capture_release && provider->capture_close && provider->counter_open &&
        provider->counter_close && provider->ioctl_call;
}

static int parse_block(struct leo_local_source *source,
    const struct leo_local_provider_block *provider_block,
    struct leo_local_block *block)
{
    uint64_t raw_counter, first, missing = 0, sequence = 0, skipped;
    size_t bytes_per_sample, expected;

    bytes_per_sample = source->config.receiver_count * 4U;
    if (source->config.samples_per_block > (SIZE_MAX - 8U) / bytes_per_sample)
        return -EOVERFLOW;
    expected = 8U + (size_t)source->config.samples_per_block * bytes_per_sample;
    if (!provider_block->raw || !provider_block->token ||
        provider_block->raw_bytes != expected)
        return -EIO;
    raw_counter = read_le64(provider_block->raw);
    if (raw_counter < 2U)
        return -ERANGE;
    first = raw_counter - 2U;
    if (first > UINT64_MAX - source->config.samples_per_block)
        return -EOVERFLOW;
    if (source->sequence_valid) {
        if (first < source->previous_frame_end)
            return -ERANGE;
        missing = first - source->previous_frame_end;
        skipped = missing / source->config.samples_per_block;
        if (source->previous_buffer_sequence > UINT64_MAX - 1U - skipped)
            return -EOVERFLOW;
        sequence = source->previous_buffer_sequence + 1U + skipped;
    }
    memset(block, 0, sizeof(*block));
    block->ci16 = (const uint8_t *)provider_block->raw + 8U;
    block->iq_bytes = expected - 8U;
    block->first_counter = first;
    block->end_counter = first + source->config.samples_per_block;
    block->buffer_sequence = sequence;
    block->missing_samples_before = missing;
    block->samples_per_receiver = source->config.samples_per_block;
    block->receiver_count = source->config.receiver_count;
    block->lease_token = provider_block->token;
    return 0;
}

static void commit_block(struct leo_local_source *source, const struct leo_local_block *block)
{
    source->previous_frame_end = block->end_counter;
    source->previous_buffer_sequence = block->buffer_sequence;
    source->sequence_valid = true;
    if (block->end_counter > source->counter_anchor)
        source->counter_anchor = block->end_counter;
}

int leo_local_owner_acquire(const struct leo_local_config *config,
    const struct leo_local_provider_ops *provider, struct leo_local_owner **out)
{
    struct leo_local_owner *owner;
    int ret;
    if (!out || !config_valid(config) || !provider_valid(provider)) return -EINVAL;
    *out = NULL;
    owner = calloc(1, sizeof(*owner));
    if (!owner) return -ENOMEM;
    owner->provider = *provider;
    owner->counter_fd = owner->provider.counter_open();
    if (owner->counter_fd < 0) { ret = owner->counter_fd; goto fail; }
    ret = spf_scan_radio_init(&owner->radio, owner->counter_fd,
        owner->provider.ioctl_call);
    if (ret) goto fail_counter;
    owner->held = true;
    *out = owner;
    return 0;
fail_counter:
    (void)owner->provider.counter_close(owner->counter_fd);
fail:
    free(owner);
    return ret;
}

int leo_local_owner_release(struct leo_local_owner *owner, uint64_t counter_anchor,
    struct leo_local_restore_receipt *receipt)
{
    int close_status, ret = 0;
    if (!owner || !receipt) return -EINVAL;
    memset(receipt, 0, sizeof(*receipt));
    if (owner->radio.acquired)
        ret = leo_local_owner_deactivate(owner, counter_anchor, receipt);
    close_status = owner->provider.counter_close(owner->counter_fd);
    owner->held = false;
    free(owner);
    return ret ? ret : close_status;
}

int leo_local_owner_deactivate(struct leo_local_owner *owner,
    uint64_t counter_anchor, struct leo_local_restore_receipt *receipt)
{
    struct spf_scan_radio_release_receipt radio_receipt = { 0 };
    int ret;
    if (!owner || !receipt || !owner->held || !owner->radio.acquired)
        return -EINVAL;
    if (!counter_anchor) counter_anchor = owner->counter_anchor;
    ret = spf_scan_radio_release(&owner->radio, counter_anchor, &radio_receipt);
    receipt->frequency_hz = radio_receipt.frequency_hz;
    receipt->counter_before = radio_receipt.counter_before;
    receipt->counter_after = radio_receipt.counter_after;
    return ret;
}

int leo_local_owner_is_live(const struct leo_local_owner *owner)
{
    return owner && owner->held;
}

int leo_local_owner_is_active(const struct leo_local_owner *owner)
{
    return owner && owner->held && owner->radio.acquired &&
        !owner->radio.released;
}

int leo_local_source_open_owned(const struct leo_local_config *config,
    const struct leo_local_provider_ops *provider, struct leo_local_owner *owner,
    struct leo_local_source **out)
{
    struct spf_scan_radio_profile profiles[LEO_LOCAL_MAX_PROFILES];
    struct leo_local_source *source;
    unsigned i;
    int ret;

    if (!out || !owner || !config_valid(config) || !provider_valid(provider))
        return -EINVAL;
    *out = NULL;
    source = calloc(1, sizeof(*source));
    if (!source)
        return -ENOMEM;
    source->config = *config;
    source->provider = *provider;
    source->owner = owner;
    ret = spf_scan_radio_acquire(&owner->radio, config->sample_rate_hz,
        config->samples_per_block,
        config->receiver_count == 2U ? UINT32_C(0x0f) : UINT32_C(0x03));
    if (ret)
        goto fail_radio;
    for (i = 0; i < config->profile_count; ++i) {
        profiles[i].profile = config->profiles[i].profile;
        profiles[i].frequency_hz = config->profiles[i].frequency_hz;
        profiles[i].crc32 = config->profiles[i].crc32;
    }
    ret = spf_scan_radio_configure(&owner->radio, profiles, config->profile_count);
    if (ret)
        goto fail_radio;
    ret = source->provider.capture_open(source->provider.context, config,
        &source->capture);
    if (ret)
        goto fail_radio;
    *out = source;
    return 0;

fail_radio:
    free(source);
    return ret;
}

int leo_local_source_open(const struct leo_local_config *config,
    const struct leo_local_provider_ops *provider, struct leo_local_source **out)
{
    struct leo_local_restore_receipt ignored;
    struct leo_local_owner *owner = NULL;
    int ret = leo_local_owner_acquire(config, provider, &owner);
    if (!ret) ret = leo_local_source_open_owned(config, provider, owner, out);
    if (ret && owner) (void)leo_local_owner_release(owner, 0U, &ignored);
    return ret;
}

int leo_local_source_prime(struct leo_local_source *source,
    struct leo_local_prime_receipt *receipt)
{
    struct leo_local_provider_block provider_block = { 0 };
    struct leo_local_block block;
    uint64_t snapshot;
    int release_ret, ret;

    if (!source || !receipt || source->primed || source->faulted ||
        source->outstanding_token)
        return -EINVAL;
    ret = source->provider.capture_acquire(source->provider.context,
        source->capture, &provider_block);
    if (ret)
        return ret;
    ret = parse_block(source, &provider_block, &block);
    release_ret = source->provider.capture_release(source->provider.context,
        source->capture, provider_block.token);
    if (ret || release_ret) {
        source->faulted = true;
        return ret ? ret : release_ret;
    }
    commit_block(source, &block);
    ret = spf_scan_radio_snapshot(&source->owner->radio, block.end_counter, &snapshot);
    if (ret) {
        source->faulted = true;
        return ret;
    }
    source->counter_anchor = snapshot;
    source->primed = true;
    receipt->discarded_first_counter = block.first_counter;
    receipt->discarded_end_counter = block.end_counter;
    receipt->coherent_counter = snapshot;
    return 0;
}

int leo_local_source_recall(struct leo_local_source *source, uint32_t profile,
    struct leo_local_transition *transition)
{
    struct spf_scan_radio_receipt receipt;
    int ret;

    if (!source || !transition || !source->primed || source->faulted ||
        source->outstanding_token)
        return -EINVAL;
    ret = spf_scan_radio_recall(&source->owner->radio, profile, source->counter_anchor,
        &receipt);
    if (ret) {
        source->faulted = true;
        return ret;
    }
    source->counter_anchor = receipt.counter_after;
    source->tuned = true;
    transition->profile = receipt.profile;
    transition->frequency_hz = receipt.frequency_hz;
    transition->profile_crc32 = receipt.profile_crc32;
    transition->previous_valid_end = receipt.counter_before;
    transition->valid_start = receipt.counter_after;
    return 0;
}

int leo_local_source_snapshot(struct leo_local_source *source, uint64_t *counter)
{
    int ret;

    if (!source || !counter || !source->primed || source->faulted ||
        source->outstanding_token)
        return -EINVAL;
    ret = spf_scan_radio_snapshot(&source->owner->radio, source->counter_anchor, counter);
    if (ret) {
        source->faulted = true;
        return ret;
    }
    source->counter_anchor = *counter;
    return 0;
}

int leo_local_source_describe(const struct leo_local_source *source,
    struct leo_local_config *config)
{
    if (!source || !config)
        return -EINVAL;
    *config = source->config;
    return 0;
}

int leo_local_source_next(struct leo_local_source *source, struct leo_local_block *block)
{
    struct leo_local_provider_block provider_block = { 0 };
    int release_ret, ret;

    if (!source || !block || !source->primed || !source->tuned || source->faulted ||
        source->outstanding_token)
        return -EINVAL;
    ret = source->provider.capture_acquire(source->provider.context,
        source->capture, &provider_block);
    if (ret)
        return ret;
    ret = parse_block(source, &provider_block, block);
    if (ret) {
        release_ret = source->provider.capture_release(source->provider.context,
            source->capture, provider_block.token);
        source->faulted = true;
        return ret ? ret : release_ret;
    }
    commit_block(source, block);
    source->outstanding_token = block->lease_token;
    return 0;
}

int leo_local_source_cancel(struct leo_local_source *source)
{
    if (!source)
        return -EINVAL;
    if (!source->provider.capture_cancel)
        return -ENOTSUP;
    return source->provider.capture_cancel(source->provider.context, source->capture);
}

int leo_local_source_release(struct leo_local_source *source,
    struct leo_local_block *block)
{
    int ret;

    if (!source || !block || !source->outstanding_token ||
        block->lease_token != source->outstanding_token)
        return -EINVAL;
    ret = source->provider.capture_release(source->provider.context,
        source->capture, source->outstanding_token);
    if (ret) {
        source->faulted = true;
        return ret;
    }
    source->outstanding_token = 0;
    memset(block, 0, sizeof(*block));
    return 0;
}

int leo_local_block_clip(const struct leo_local_block *block,
    uint64_t valid_start, uint64_t valid_end, struct leo_local_slice *slice)
{
    uint64_t first, end, samples;
    size_t bytes_per_sample;

    if (!block || !slice || !block->ci16 || !block->samples_per_receiver ||
        (block->receiver_count != 1U && block->receiver_count != 2U) ||
        valid_end < valid_start || block->end_counter < block->first_counter)
        return -EINVAL;
    first = block->first_counter > valid_start ? block->first_counter : valid_start;
    end = block->end_counter < valid_end ? block->end_counter : valid_end;
    if (end <= first)
        return -ENODATA;
    samples = end - first;
    if (samples > UINT32_MAX || first - block->first_counter > UINT32_MAX)
        return -EOVERFLOW;
    bytes_per_sample = block->receiver_count * 4U;
    if (block->iq_bytes != (size_t)block->samples_per_receiver * bytes_per_sample)
        return -EINVAL;
    memset(slice, 0, sizeof(*slice));
    slice->sample_offset = (uint32_t)(first - block->first_counter);
    slice->samples_per_receiver = (uint32_t)samples;
    slice->receiver_count = block->receiver_count;
    slice->first_counter = first;
    slice->ci16 = (const uint8_t *)block->ci16 +
        (size_t)slice->sample_offset * bytes_per_sample;
    slice->iq_bytes = (size_t)slice->samples_per_receiver * bytes_per_sample;
    return 0;
}

int leo_local_source_close_preserve_owner(struct leo_local_source *source,
    struct leo_local_owner **owner)
{
    int first_error = 0, ret;

    if (!source || !owner)
        return -EINVAL;
    *owner = NULL;
    if (source->outstanding_token) {
        ret = source->provider.capture_release(source->provider.context,
            source->capture, source->outstanding_token);
        if (ret && !first_error)
            first_error = ret;
        source->outstanding_token = 0;
    }
    if (source->capture) {
        ret = source->provider.capture_close(source->provider.context,
            source->capture);
        if (ret && !first_error)
            first_error = ret;
    }
    source->owner->counter_anchor = source->counter_anchor;
    *owner = source->owner;
    free(source);
    return first_error;
}

int leo_local_source_close(struct leo_local_source *source,
    struct leo_local_restore_receipt *receipt)
{
    struct leo_local_owner *owner = NULL;
    int ret, release_status;
    if (!source || !receipt) return -EINVAL;
    memset(receipt, 0, sizeof(*receipt));
    ret = leo_local_source_close_preserve_owner(source, &owner);
    release_status = owner ? leo_local_owner_release(owner, 0U, receipt) : 0;
    return ret ? ret : release_status;
}
