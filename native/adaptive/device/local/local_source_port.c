#include "local_source_port.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>

struct leo_local_source_port {
    leo_local_source *source;
    leo_local_config config;
    leo_local_block leased;
    leo_source_port port;
};

static int adapter_capabilities(void *context,
    leo_source_capabilities *capabilities)
{
    struct leo_local_source_port *adapter = context;
    uint32_t flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION |
        LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;

    if (adapter->config.receiver_count == 2U)
        flags |= LEO_SOURCE_CAP_SIMULTANEOUS_RX |
            LEO_SOURCE_CAP_COHERENT_RX;
    memset(capabilities, 0, sizeof(*capabilities));
    capabilities->abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    capabilities->sample_format = LEO_SOURCE_SAMPLE_FORMAT_CI16;
    capabilities->flags = flags;
    capabilities->sample_rate_hz = adapter->config.sample_rate_hz;
    capabilities->receiver_count = adapter->config.receiver_count;
    capabilities->maximum_samples_per_block =
        adapter->config.samples_per_block;
    capabilities->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    capabilities->position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    capabilities->time_authority = LEO_SOURCE_TIME_NONE;
    return 0;
}

static int adapter_position(void *context, leo_source_position *position)
{
    struct leo_local_source_port *adapter = context;
    uint64_t counter = 0;
    int status = leo_local_source_snapshot(adapter->source, &counter);

    if (status)
        return status;
    position->coordinate = counter;
    position->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    position->semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    return 0;
}

static int configured_target(const struct leo_local_source_port *adapter,
    uint32_t target_key, uint64_t frequency_hz)
{
    uint32_t index;

    for (index = 0; index < adapter->config.profile_count; ++index) {
        const leo_local_profile *profile = &adapter->config.profiles[index];
        if (profile->profile == target_key &&
            profile->frequency_hz == frequency_hz)
            return 1;
    }
    return 0;
}

static int adapter_select(void *context, const leo_source_selection *selection,
    leo_source_transition *transition)
{
    struct leo_local_source_port *adapter = context;
    leo_local_transition local;
    int status;

    if (!configured_target(adapter, selection->target_key,
            selection->requested_frequency_hz))
        return -ENOENT;
    memset(&local, 0, sizeof(local));
    status = leo_local_source_recall(adapter->source, selection->target_key,
        &local);
    if (status)
        return status;
    if (local.profile != selection->target_key || !local.frequency_hz ||
        !local.profile_crc32 || local.valid_start < local.previous_valid_end)
        return -EPROTO;
    memset(transition, 0, sizeof(*transition));
    transition->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    transition->selected_target_key = local.profile;
    transition->profile_crc32 = local.profile_crc32;
    transition->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    transition->position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    transition->actual_frequency_hz = local.frequency_hz;
    transition->previous_valid_end = local.previous_valid_end;
    transition->valid_start = local.valid_start;
    return 0;
}

static int adapter_next(void *context, leo_source_block *block)
{
    struct leo_local_source_port *adapter = context;
    int status;

    if (adapter->leased.lease_token)
        return -EBUSY;
    memset(&adapter->leased, 0, sizeof(adapter->leased));
    status = leo_local_source_next(adapter->source, &adapter->leased);
    if (status)
        return status;
    /* Map every successful lease. The common wrapper validates the configured
     * shape and retains this block if cleanup fails. */
    memset(block, 0, sizeof(*block));
    block->ci16 = adapter->leased.ci16;
    block->iq_bytes = adapter->leased.iq_bytes;
    block->samples_per_receiver = adapter->leased.samples_per_receiver;
    block->receiver_count = adapter->leased.receiver_count;
    block->flags = LEO_SOURCE_BLOCK_GAP_EXACT;
    if (adapter->leased.missing_samples_before) {
        block->flags |= LEO_SOURCE_BLOCK_DISCONTINUITY;
        block->missing_samples_before = adapter->leased.missing_samples_before;
    }
    block->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    block->time_authority = LEO_SOURCE_TIME_NONE;
    block->first_coordinate = adapter->leased.first_counter;
    block->end_coordinate = adapter->leased.end_counter;
    block->buffer_sequence = adapter->leased.buffer_sequence;
    block->lease_token = adapter->leased.lease_token;
    return 0;
}

static int adapter_release(void *context, leo_source_block *block)
{
    struct leo_local_source_port *adapter = context;

    if (!adapter->leased.lease_token ||
        block->lease_token != adapter->leased.lease_token)
        return -EINVAL;
    return leo_local_source_release(adapter->source, &adapter->leased);
}

static int adapter_cancel(void *context)
{
    struct leo_local_source_port *adapter = context;

    return leo_local_source_cancel(adapter->source);
}

static const leo_source_ops operations = {
    .capabilities = adapter_capabilities,
    .position = adapter_position,
    .select = adapter_select,
    .next = adapter_next,
    .release = adapter_release,
    .cancel = adapter_cancel,
};

static int valid_config(const leo_local_config *config)
{
    uint32_t index;

    if (!config || !config->sample_rate_hz || !config->samples_per_block ||
        !config->receiver_count || config->receiver_count > 2U ||
        !config->profile_count || config->profile_count > LEO_LOCAL_MAX_PROFILES)
        return 0;
    for (index = 0; index < config->profile_count; ++index) {
        if (config->profiles[index].profile >= LEO_LOCAL_MAX_PROFILES ||
            !config->profiles[index].frequency_hz ||
            !config->profiles[index].crc32)
            return 0;
    }
    return 1;
}

int leo_local_source_port_create(leo_local_source *source,
    const leo_local_config *config, leo_local_source_port **output)
{
    struct leo_local_source_port *adapter;
    int status;

    if (!source || !valid_config(config) || !output)
        return -EINVAL;
    *output = NULL;
    adapter = calloc(1, sizeof(*adapter));
    if (!adapter)
        return -ENOMEM;
    adapter->source = source;
    adapter->config = *config;
    status = leo_source_port_init(&adapter->port, adapter, &operations);
    if (status) {
        free(adapter);
        return status;
    }
    *output = adapter;
    return 0;
}

leo_source_port *leo_local_source_port_get(leo_local_source_port *adapter)
{
    return adapter ? &adapter->port : NULL;
}

int leo_local_source_port_destroy(leo_local_source_port *adapter)
{
    if (!adapter)
        return -EINVAL;
    if (adapter->port.outstanding_lease || adapter->leased.lease_token)
        return -EBUSY;
    free(adapter);
    return 0;
}

int leo_local_source_port_abandon_lease(leo_local_source_port *adapter)
{
    if (!adapter || !adapter->port.outstanding_lease ||
        adapter->port.outstanding_lease != adapter->leased.lease_token)
        return -EINVAL;
    /* leo_local_source_release retains its own token on failure. The adapter
     * owns no provider resource beyond that caller-owned source token. */
    free(adapter);
    return 0;
}
