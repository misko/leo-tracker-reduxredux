#include "source_port.h"

#include <errno.h>
#include <limits.h>
#include <string.h>

#define LEO_SOURCE_ALL_CAPS (LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT | \
    LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX | \
    LEO_SOURCE_CAP_FREQUENCY_ATTESTATION | LEO_SOURCE_CAP_TARGET_ATTESTATION | \
    LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION | LEO_SOURCE_CAP_EXACT_GAP | \
    LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY)

#define LEO_SOURCE_ALL_TRANSITION_FLAGS \
    (LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED | \
     LEO_SOURCE_TRANSITION_TARGET_ATTESTED | \
     LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED | \
     LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY | \
     LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY)

#define LEO_SOURCE_ALL_BLOCK_FLAGS (LEO_SOURCE_BLOCK_OVERFLOW_BEFORE | \
    LEO_SOURCE_BLOCK_DISCONTINUITY | LEO_SOURCE_BLOCK_GAP_EXACT)

static int normalize(int status)
{
    return status > 0 ? -EIO : status;
}

static int valid_counter(uint32_t value)
{
    return value >= LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED &&
        value <= LEO_SOURCE_COUNTER_PROVIDER_EXACT;
}

static int valid_position_semantics(uint32_t value)
{
    return value == LEO_SOURCE_POSITION_COHERENT_CURRENT ||
        value == LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
}

static int valid_time(uint32_t value)
{
    return value <= LEO_SOURCE_TIME_DEVICE;
}

static int validate_capabilities(const leo_source_capabilities *c)
{
    if (!c || c->abi_version != LEO_SOURCE_PORT_ABI_VERSION ||
        c->sample_format != LEO_SOURCE_SAMPLE_FORMAT_CI16 ||
        (c->flags & ~LEO_SOURCE_ALL_CAPS) || !c->sample_rate_hz ||
        !c->receiver_count || c->receiver_count > 2U ||
        !c->maximum_samples_per_block || !valid_counter(c->counter_authority) ||
        !valid_position_semantics(c->position_semantics) ||
        !valid_time(c->time_authority))
        return -EPROTO;
    if (c->position_semantics == LEO_SOURCE_POSITION_COHERENT_CURRENT &&
        c->counter_authority != LEO_SOURCE_COUNTER_PROVIDER_EXACT)
        return -EPROTO;
    if ((c->flags & LEO_SOURCE_CAP_EXACT_GAP) &&
        c->counter_authority != LEO_SOURCE_COUNTER_PROVIDER_EXACT)
        return -EPROTO;
    if ((c->flags & LEO_SOURCE_CAP_COHERENT_RX) &&
        !(c->flags & LEO_SOURCE_CAP_SIMULTANEOUS_RX))
        return -EPROTO;
    if ((c->flags & LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION) &&
        !(c->flags & LEO_SOURCE_CAP_TARGET_ATTESTATION))
        return -EPROTO;
    if (!(c->flags & LEO_SOURCE_CAP_CANCEL) ||
        !(c->flags & LEO_SOURCE_CAP_SELECT) ||
        !(c->flags & LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY))
        return -EPROTO;
    if (c->time_authority == LEO_SOURCE_TIME_NONE &&
        c->minimum_time_uncertainty_ns)
        return -EPROTO;
    return 0;
}

static int valid_port(const leo_source_port *port)
{
    return port && port->abi_version == LEO_SOURCE_PORT_ABI_VERSION &&
        port->context && port->ops;
}

static int available(const leo_source_port *port)
{
    return port->fault_status ? port->fault_status : 0;
}

int leo_source_port_init(leo_source_port *port, void *context,
    const leo_source_ops *ops)
{
    leo_source_capabilities capabilities;
    int status;

    if (!port || !context || !ops || !ops->capabilities || !ops->position ||
        !ops->select || !ops->next || !ops->release || !ops->cancel)
        return -EINVAL;
    memset(&capabilities, 0, sizeof(capabilities));
    status = normalize(ops->capabilities(context, &capabilities));
    if (status)
        return status;
    status = validate_capabilities(&capabilities);
    if (status)
        return status;
    memset(port, 0, sizeof(*port));
    port->abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    port->context = context;
    port->ops = ops;
    port->capabilities = capabilities;
    return 0;
}

int leo_source_port_capabilities(const leo_source_port *port,
    leo_source_capabilities *capabilities)
{
    if (!valid_port(port) || !capabilities)
        return -EINVAL;
    *capabilities = port->capabilities;
    return 0;
}

int leo_source_port_position(leo_source_port *port,
    leo_source_position *position)
{
    leo_source_position result;
    int status;

    if (!valid_port(port) || !position)
        return -EINVAL;
    if (available(port))
        return available(port);
    if (port->outstanding_lease)
        return -EBUSY;
    memset(&result, 0, sizeof(result));
    status = normalize(port->ops->position(port->context, &result));
    if (status)
        return status;
    if (result.counter_authority != port->capabilities.counter_authority ||
        result.semantics != port->capabilities.position_semantics) {
        port->fault_status = -EPROTO;
        return -EPROTO;
    }
    *position = result;
    return 0;
}

int leo_source_port_select(leo_source_port *port,
    const leo_source_selection *selection, leo_source_transition *transition)
{
    leo_source_transition result;
    uint64_t error;
    int status;

    if (!valid_port(port) || !selection || !transition ||
        !selection->requested_frequency_hz)
        return -EINVAL;
    if (available(port))
        return available(port);
    if (port->outstanding_lease)
        return -EBUSY;
    memset(&result, 0, sizeof(result));
    status = normalize(port->ops->select(port->context, selection, &result));
    if (status) {
        /* A failed provider call can still have changed a physical tuner. */
        port->fault_status = status;
        return status;
    }
    if ((result.flags & ~LEO_SOURCE_ALL_TRANSITION_FLAGS) ||
        !result.actual_frequency_hz ||
        !(result.flags & LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY)) {
        status = -EPROTO;
        goto invalid_after_select;
    }
    error = result.actual_frequency_hz >= selection->requested_frequency_hz ?
        result.actual_frequency_hz - selection->requested_frequency_hz :
        selection->requested_frequency_hz - result.actual_frequency_hz;
    if (error > selection->maximum_frequency_error_hz) {
        status = -ERANGE;
        goto invalid_after_select;
    }
    if ((result.flags & LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED) &&
        !(port->capabilities.flags & LEO_SOURCE_CAP_FREQUENCY_ATTESTATION))
        goto protocol_after_select;
    if ((result.flags & LEO_SOURCE_TRANSITION_TARGET_ATTESTED) &&
        (!(port->capabilities.flags & LEO_SOURCE_CAP_TARGET_ATTESTATION) ||
         result.selected_target_key != selection->target_key))
        goto protocol_after_select;
    if ((result.flags & LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED) &&
        (!(port->capabilities.flags & LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION) ||
         !result.profile_crc32))
        goto protocol_after_select;
    if (result.flags & LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY) {
        if (!(port->capabilities.flags &
                LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY) ||
            result.counter_authority != port->capabilities.counter_authority ||
            result.position_semantics != port->capabilities.position_semantics ||
            result.valid_start < result.previous_valid_end)
            goto protocol_after_select;
    } else if (result.counter_authority || result.position_semantics ||
        result.previous_valid_end || result.valid_start) {
        goto protocol_after_select;
    }
    if (result.flags & LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY) {
        if (!valid_time(result.time_authority) ||
            result.time_authority == LEO_SOURCE_TIME_NONE ||
            result.time_authority != port->capabilities.time_authority ||
            result.valid_start_time_ns < result.previous_valid_time_ns ||
            result.time_uncertainty_ns <
                port->capabilities.minimum_time_uncertainty_ns)
            goto protocol_after_select;
    } else if (result.time_authority || result.previous_valid_time_ns ||
        result.valid_start_time_ns || result.time_uncertainty_ns) {
        goto protocol_after_select;
    }
    *transition = result;
    return 0;

protocol_after_select:
    status = -EPROTO;
invalid_after_select:
    /* select may already have changed physical state. No later operation may
     * assume the preceding target remains active. */
    port->fault_status = status;
    return status;
}

static int validate_block(const leo_source_port *port,
    const leo_source_block *block)
{
    size_t bytes_per_sample;

    if (!block->ci16 || !block->samples_per_receiver ||
        block->samples_per_receiver > port->capabilities.maximum_samples_per_block ||
        block->receiver_count != port->capabilities.receiver_count ||
        (block->flags & ~LEO_SOURCE_ALL_BLOCK_FLAGS) ||
        block->counter_authority != port->capabilities.counter_authority ||
        block->end_coordinate < block->first_coordinate ||
        block->end_coordinate - block->first_coordinate !=
            block->samples_per_receiver || !block->lease_token)
        return -EPROTO;
    bytes_per_sample = (size_t)block->receiver_count * 4U;
    if (block->samples_per_receiver > SIZE_MAX / bytes_per_sample ||
        block->iq_bytes !=
            (size_t)block->samples_per_receiver * bytes_per_sample)
        return -EPROTO;
    if ((block->flags & LEO_SOURCE_BLOCK_GAP_EXACT) &&
        (!(port->capabilities.flags & LEO_SOURCE_CAP_EXACT_GAP) ||
         block->counter_authority != LEO_SOURCE_COUNTER_PROVIDER_EXACT))
        return -EPROTO;
    if (!(block->flags & LEO_SOURCE_BLOCK_GAP_EXACT) &&
        block->missing_samples_before)
        return -EPROTO;
    if (block->missing_samples_before &&
        !(block->flags & LEO_SOURCE_BLOCK_DISCONTINUITY))
        return -EPROTO;
    if (!valid_time(block->time_authority) ||
        (block->time_authority != LEO_SOURCE_TIME_NONE &&
         block->time_authority != port->capabilities.time_authority) ||
        (block->time_authority == LEO_SOURCE_TIME_NONE &&
         (block->first_time_ns || block->time_uncertainty_ns)) ||
        (block->time_authority != LEO_SOURCE_TIME_NONE &&
         block->time_uncertainty_ns <
            port->capabilities.minimum_time_uncertainty_ns))
        return -EPROTO;
    return 0;
}

int leo_source_port_next(leo_source_port *port, leo_source_block *block)
{
    leo_source_block result;
    int status;

    if (!valid_port(port) || !block)
        return -EINVAL;
    if (available(port))
        return available(port);
    if (port->outstanding_lease)
        return -EBUSY;
    memset(&result, 0, sizeof(result));
    status = normalize(port->ops->next(port->context, &result));
    if (status)
        return status;
    status = validate_block(port, &result);
    if (status) {
        if (result.lease_token) {
            port->outstanding_lease = result.lease_token;
            port->retained_block = result;
            {
                const int release_status = normalize(
                    port->ops->release(port->context, &port->retained_block));
                if (release_status) {
                    port->fault_status = release_status;
                    return release_status;
                }
            }
            port->outstanding_lease = 0;
            memset(&port->retained_block, 0, sizeof(port->retained_block));
        }
        port->fault_status = status;
        return status;
    }
    port->outstanding_lease = result.lease_token;
    port->retained_block = result;
    *block = result;
    return 0;
}

int leo_source_port_release(leo_source_port *port, leo_source_block *block)
{
    int status;

    if (!valid_port(port) || !block)
        return -EINVAL;
    if (!port->outstanding_lease ||
        block->lease_token != port->outstanding_lease)
        return -EINVAL;
    status = normalize(port->ops->release(port->context,
        &port->retained_block));
    if (status) {
        port->fault_status = status;
        return status;
    }
    port->outstanding_lease = 0;
    memset(&port->retained_block, 0, sizeof(port->retained_block));
    memset(block, 0, sizeof(*block));
    return 0;
}

int leo_source_port_cleanup(leo_source_port *port)
{
    int status;

    if (!valid_port(port))
        return -EINVAL;
    if (!port->outstanding_lease)
        return 0;
    status = normalize(port->ops->release(port->context,
        &port->retained_block));
    if (status) {
        port->fault_status = status;
        return status;
    }
    port->outstanding_lease = 0;
    memset(&port->retained_block, 0, sizeof(port->retained_block));
    return 0;
}

int leo_source_port_cancel(leo_source_port *port)
{
    if (!valid_port(port))
        return -EINVAL;
    /* Do not inspect or mutate outstanding_lease here: cancel may race next. */
    return normalize(port->ops->cancel(port->context));
}

int leo_source_block_clip(const leo_source_block *block, uint64_t valid_start,
    uint64_t valid_end, leo_source_slice *slice)
{
    uint64_t first, end, samples, offset;
    size_t bytes_per_sample;

    if (!block || !slice || !block->ci16 || !block->samples_per_receiver ||
        !block->receiver_count || block->receiver_count > 2U ||
        valid_end < valid_start || block->end_coordinate < block->first_coordinate)
        return -EINVAL;
    bytes_per_sample = (size_t)block->receiver_count * 4U;
    if (block->samples_per_receiver > SIZE_MAX / bytes_per_sample ||
        block->iq_bytes !=
            (size_t)block->samples_per_receiver * bytes_per_sample ||
        block->end_coordinate - block->first_coordinate !=
            block->samples_per_receiver)
        return -EINVAL;
    first = block->first_coordinate > valid_start ?
        block->first_coordinate : valid_start;
    end = block->end_coordinate < valid_end ? block->end_coordinate : valid_end;
    if (end <= first)
        return -ENODATA;
    samples = end - first;
    offset = first - block->first_coordinate;
    if (samples > UINT32_MAX || offset > UINT32_MAX)
        return -EOVERFLOW;
    memset(slice, 0, sizeof(*slice));
    slice->ci16 = (const int16_t *)((const unsigned char *)block->ci16 +
        (size_t)offset * bytes_per_sample);
    slice->iq_bytes = (size_t)samples * bytes_per_sample;
    slice->first_coordinate = first;
    slice->sample_offset = (uint32_t)offset;
    slice->samples_per_receiver = (uint32_t)samples;
    slice->receiver_count = block->receiver_count;
    return 0;
}
