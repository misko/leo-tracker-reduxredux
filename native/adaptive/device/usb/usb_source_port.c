#include "usb_source_port.h"

#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

struct leo_usb_source_port {
    leo_usb_source *source;
    leo_usb_stream_info info;
    leo_usb_block leased;
    leo_source_port port;
    uintptr_t common_token;
    uint64_t watermark;
    uint64_t valid_floor;
    uint32_t watermark_valid;
    uint32_t have_valid_floor;
    int release_error;
    int faulted;
};

static uint32_t source_counter(uint32_t value)
{
    switch (value) {
    case LEO_USB_COUNTER_SOFTWARE_DELIVERED:
        return LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    case LEO_USB_COUNTER_PROVIDER_ESTIMATED:
        return LEO_SOURCE_COUNTER_PROVIDER_ESTIMATED;
    case LEO_USB_COUNTER_PROVIDER_EXACT:
        return LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    default:
        return LEO_SOURCE_COUNTER_NONE;
    }
}

static uint32_t source_time(uint32_t value)
{
    switch (value) {
    case LEO_USB_TIME_NONE: return LEO_SOURCE_TIME_NONE;
    case LEO_USB_TIME_HOST_MONOTONIC: return LEO_SOURCE_TIME_HOST_MONOTONIC;
    case LEO_USB_TIME_DEVICE: return LEO_SOURCE_TIME_DEVICE;
    default: return UINT32_MAX;
    }
}

static int adapter_capabilities(void *context,
    leo_source_capabilities *capabilities)
{
    struct leo_usb_source_port *adapter = context;
    uint32_t flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;

    if (adapter->info.receiver_count == 2U)
        flags |= LEO_SOURCE_CAP_SIMULTANEOUS_RX |
            LEO_SOURCE_CAP_COHERENT_RX;
    if (adapter->info.counter_authority == LEO_USB_COUNTER_PROVIDER_EXACT)
        flags |= LEO_SOURCE_CAP_EXACT_GAP;
    memset(capabilities, 0, sizeof(*capabilities));
    capabilities->abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    capabilities->sample_format = LEO_SOURCE_SAMPLE_FORMAT_CI16;
    capabilities->flags = flags;
    capabilities->sample_rate_hz = adapter->info.sample_rate_hz;
    capabilities->receiver_count = adapter->info.receiver_count;
    capabilities->maximum_samples_per_block =
        adapter->info.maximum_samples_per_block;
    capabilities->counter_authority =
        source_counter(adapter->info.counter_authority);
    capabilities->position_semantics =
        LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    capabilities->time_authority = source_time(adapter->info.time_authority);
    capabilities->minimum_time_uncertainty_ns =
        adapter->info.minimum_time_uncertainty_ns;
    return 0;
}

static int adapter_position(void *context, leo_source_position *position)
{
    struct leo_usb_source_port *adapter = context;
    if (adapter->faulted) return -EIO;
    if (!adapter->watermark_valid) return -ENODATA;
    memset(position, 0, sizeof(*position));
    position->coordinate = adapter->watermark;
    position->counter_authority =
        source_counter(adapter->info.counter_authority);
    position->semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

static int adapter_select(void *context, const leo_source_selection *selection,
    leo_source_transition *transition)
{
    struct leo_usb_source_port *adapter = context;
    leo_usb_provider_retune receipt;
    uint64_t error;
    int status;

    if (adapter->faulted) return -EIO;
    if (!adapter->watermark_valid) return -ENODATA;
    memset(&receipt, 0, sizeof(receipt));
    status = leo_usb_source_retune(adapter->source,
        selection->requested_frequency_hz, &receipt);
    if (status) return status;
    if (!(receipt.flags & LEO_USB_RETUNE_VALID_COUNTER) ||
        source_counter(receipt.counter_authority) !=
            source_counter(adapter->info.counter_authority) ||
        receipt.valid_counter < adapter->watermark) {
        adapter->faulted = 1;
        return -EPROTO;
    }
    error = receipt.actual_frequency_hz >= selection->requested_frequency_hz ?
        receipt.actual_frequency_hz - selection->requested_frequency_hz :
        selection->requested_frequency_hz - receipt.actual_frequency_hz;
    if (error > selection->maximum_frequency_error_hz) {
        adapter->faulted = 1;
        return -ERANGE;
    }
    memset(transition, 0, sizeof(*transition));
    transition->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    transition->counter_authority =
        source_counter(receipt.counter_authority);
    transition->position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    transition->actual_frequency_hz = receipt.actual_frequency_hz;
    transition->previous_valid_end = adapter->watermark;
    transition->valid_start = receipt.valid_counter;
    /* A USB receipt has only a post-retune valid time. It cannot represent the
     * preceding valid-end time required by the common transition contract. */
    adapter->valid_floor = receipt.valid_counter;
    adapter->have_valid_floor = 1U;
    return 0;
}

static int release_after_mapping_error(struct leo_usb_source_port *adapter,
    int error)
{
    int release_status = leo_usb_source_release(adapter->source,
        &adapter->leased);
    adapter->faulted = 1;
    if (release_status) {
        /* USB source release is terminal and clears its token even on failure.
         * Retain explicit adapter ownership until abandon, then source close. */
        adapter->release_error = release_status;
        return release_status;
    }
    return error ? error : -EPROTO;
}

static int adapter_next(void *context, leo_source_block *block)
{
    struct leo_usb_source_port *adapter = context;
    uint64_t end;
    int status;

    if (adapter->faulted) return -EIO;
    if (adapter->common_token || adapter->leased.lease_token) return -EBUSY;
    memset(&adapter->leased, 0, sizeof(adapter->leased));
    status = leo_usb_source_next(adapter->source, &adapter->leased);
    if (status) return status;
    if (adapter->leased.samples_per_receiver >
            UINT64_MAX - adapter->leased.first_counter)
        return release_after_mapping_error(adapter, -EOVERFLOW);
    end = adapter->leased.first_counter +
        adapter->leased.samples_per_receiver;
    if (adapter->leased.counter_authority !=
            adapter->info.counter_authority ||
        adapter->leased.receiver_count != adapter->info.receiver_count ||
        (adapter->have_valid_floor &&
            adapter->leased.first_counter < adapter->valid_floor))
        return release_after_mapping_error(adapter, -EPROTO);
    memset(block, 0, sizeof(*block));
    block->ci16 = adapter->leased.ci16;
    block->iq_bytes = adapter->leased.iq_bytes;
    block->samples_per_receiver = adapter->leased.samples_per_receiver;
    block->receiver_count = adapter->leased.receiver_count;
    if (adapter->leased.flags & LEO_USB_BLOCK_OVERFLOW_BEFORE)
        block->flags |= LEO_SOURCE_BLOCK_OVERFLOW_BEFORE;
    if (adapter->leased.flags & LEO_USB_BLOCK_DISCONTINUITY)
        block->flags |= LEO_SOURCE_BLOCK_DISCONTINUITY;
    if (adapter->leased.flags & LEO_USB_BLOCK_GAP_EXACT)
        block->flags |= LEO_SOURCE_BLOCK_GAP_EXACT;
    block->counter_authority =
        source_counter(adapter->leased.counter_authority);
    block->time_authority = source_time(adapter->leased.time_authority);
    block->first_coordinate = adapter->leased.first_counter;
    block->end_coordinate = end;
    block->stream_ordinal = adapter->leased.stream_ordinal;
    block->first_time_ns = adapter->leased.first_time_ns;
    block->time_uncertainty_ns = adapter->leased.time_uncertainty_ns;
    block->missing_samples_before = adapter->leased.missing_samples_before;
    block->buffer_sequence = adapter->leased.buffer_sequence;
    block->lease_token = adapter->leased.lease_token;
    adapter->common_token = block->lease_token;
    adapter->watermark = end;
    adapter->watermark_valid = 1U;
    adapter->have_valid_floor = 0U;
    return 0;
}

static int adapter_release(void *context, leo_source_block *block)
{
    struct leo_usb_source_port *adapter = context;
    int status;

    if (!adapter->common_token ||
        block->lease_token != adapter->common_token)
        return -EINVAL;
    if (!adapter->leased.lease_token)
        return adapter->release_error ? adapter->release_error : -EIO;
    status = leo_usb_source_release(adapter->source, &adapter->leased);
    if (status) {
        adapter->release_error = status;
        adapter->faulted = 1;
        return status;
    }
    adapter->common_token = 0;
    return 0;
}

static int adapter_cancel(void *context)
{
    struct leo_usb_source_port *adapter = context;
    return leo_usb_source_cancel(adapter->source);
}

static const leo_source_ops operations = {
    .capabilities = adapter_capabilities,
    .position = adapter_position,
    .select = adapter_select,
    .next = adapter_next,
    .release = adapter_release,
    .cancel = adapter_cancel,
};

int leo_usb_source_port_create(leo_usb_source *source,
    leo_usb_source_port **output)
{
    struct leo_usb_source_port *adapter;
    int status;

    if (!source || !output) return -EINVAL;
    *output = NULL;
    adapter = calloc(1, sizeof(*adapter));
    if (!adapter) return -ENOMEM;
    status = leo_usb_source_get_stream_info(source, &adapter->info);
    if (status) goto fail;
    if (!(adapter->info.capability_flags &
            LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY)) {
        status = -ENOTSUP;
        goto fail;
    }
    if (!source_counter(adapter->info.counter_authority) ||
        source_time(adapter->info.time_authority) == UINT32_MAX) {
        status = -EPROTO;
        goto fail;
    }
    adapter->source = source;
    adapter->watermark = adapter->info.delivered_watermark;
    adapter->watermark_valid = adapter->info.watermark_valid;
    status = leo_source_port_init(&adapter->port, adapter, &operations);
    if (status) goto fail;
    *output = adapter;
    return 0;
fail:
    free(adapter);
    return status;
}

leo_source_port *leo_usb_source_port_get(leo_usb_source_port *adapter)
{
    return adapter ? &adapter->port : NULL;
}

int leo_usb_source_port_destroy(leo_usb_source_port *adapter)
{
    if (!adapter) return -EINVAL;
    if (adapter->port.outstanding_lease || adapter->common_token ||
        adapter->leased.lease_token || adapter->release_error)
        return -EBUSY;
    free(adapter);
    return 0;
}

int leo_usb_source_port_abandon_lease(leo_usb_source_port *adapter)
{
    if (!adapter || !adapter->release_error || adapter->leased.lease_token)
        return -EINVAL;
    if (adapter->common_token) {
        if (adapter->port.outstanding_lease != adapter->common_token)
            return -EINVAL;
    } else if (adapter->port.outstanding_lease) return -EINVAL;
    free(adapter);
    return 0;
}
