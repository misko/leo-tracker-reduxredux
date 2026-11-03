/* SPDX-License-Identifier: BSD-1-Clause */
#ifndef POWER_SCANNER_REGS_H
#define POWER_SCANNER_REGS_H
#include <stdint.h>
/* Proposed standalone block, AXI base assigned by the integrated build. */
#define PWR_IDENTITY 0x50575231u
#define PWR_ABI 0x00010000u
#define PWR_REG_ID 0x00u
#define PWR_REG_ABI 0x04u
#define PWR_REG_COMMAND 0x08u
#define PWR_REG_STATUS 0x0cu
#define PWR_REG_ACK_VISIT 0x10u
#define PWR_REG_ACK_CODE 0x14u
#define PWR_REG_ACK_COUNTER_LO 0x18u
#define PWR_REG_ACK_COUNTER_HI 0x1cu
#define PWR_REG_FAULT 0x20u
#define PWR_REG_CAPACITY 0x24u
#define PWR_REG_COUNTER_LO 0x28u
#define PWR_REG_COUNTER_HI 0x2cu
#define PWR_REG_WINDOW_SAMPLES 0x30u
#define PWR_REG_INPUT_BITS 0x34u
#define PWR_REG_RESULT_WORDS 0x38u
#define PWR_REG_RX_MASK 0x3cu
#define PWR_REG_START_LO 0x40u
/* Every shadow write through0x6c returns SLVERR while COMMAND_PENDING.
 * Poll acknowledgement before rewriting, including partial-byte writes. */
#define PWR_REG_START_HI 0x44u
#define PWR_REG_COUNT 0x48u
#define PWR_REG_SESSION 0x4cu
#define PWR_REG_GENERATION 0x50u
#define PWR_REG_VISIT_LO 0x54u
#define PWR_REG_VISIT_HI 0x58u
#define PWR_REG_TARGET 0x5cu
#define PWR_REG_PROFILE 0x60u
#define PWR_REG_SWEEP_LO 0x64u
#define PWR_REG_SWEEP_HI 0x68u
/* Set only after ADC12 sign-extension/scaling/bypass qualification. */
#define PWR_REG_ADC12_QUALIFIED 0x6cu
#define PWR_REG_DATAPATH_CAPS 0x70u
#define PWR_CAP_NATIVE_FACTOR1 1u
#define PWR_CAP_LEGACY_FPGA_FIR 2u
#define PWR_REG_RESULT_BASE 0x100u
#define PWR_CMD_COMMIT 1u
#define PWR_CMD_ABORT 2u
#define PWR_CMD_POP 4u
#define PWR_CMD_CLEAR_FAULT 8u
#define PWR_CMD_SNAPSHOT_COUNTER 16u
#define PWR_STATUS_COMMAND_PENDING 1u
#define PWR_STATUS_BUSY 2u
#define PWR_STATUS_RESULT_VALID 4u
#define PWR_STATUS_FAULT 8u
#define PWR_STATUS_STOP_ACK 16u
#define PWR_STATUS_COUNTER_PENDING 32u
#define PWR_STATUS_POP_PENDING 64u
#define PWR_STATUS_ABORT_PENDING 128u
#define PWR_STATUS_SNAPSHOT_PENDING PWR_STATUS_COUNTER_PENDING
#define PWR_STATUS_STOP_PENDING PWR_STATUS_ABORT_PENDING
#define PWR_FLAG_LATE 1u
#define PWR_FLAG_COUNTER_GAP 2u
#define PWR_FLAG_LAYOUT 4u
#define PWR_FLAG_ABORTED 8u
#define PWR_FLAG_BAD_COUNT 16u
#define PWR_FLAG_ARITHMETIC_OVERFLOW 32u
#define PWR_FLAG_CLIPPED 64u
#define PWR_FLAG_RESULT_PRESSURE 128u
#define PWR_RESULT_WORDS 36u
/* IQ origin is tagged at the pre-packer edge. All-four-lane bypass simulation
 * with the actual ADI packer + timestamp prefixes yields FIFO stamp=origin+1.
 * This geometry does not apply to other masks, decimation or firmware layouts. */
#define PWR_COUNTER_IDENTITY "prepack_preincrement_v1"
#define PWR_QUALIFIED_PAIRED_FIFO_TAG_OFFSET 1u
/* 36 little-endian words; fields are offsets within the result, not addresses. */
enum pwr_result_word {
 PWR_R_ID=0, PWR_R_ABI=1, PWR_R_FLAGS=2, PWR_R_COUNT=3,
 PWR_R_SESSION=4, PWR_R_GENERATION=5, PWR_R_VISIT_LO=6, PWR_R_VISIT_HI=7,
 PWR_R_TARGET=8, PWR_R_PROFILE=9, PWR_R_START_LO=10, PWR_R_START_HI=11,
 PWR_R_END_LO=12, PWR_R_END_HI=13, PWR_R_ENERGY0_LO=14, PWR_R_ENERGY0_HI=15,
 PWR_R_ENERGY1_LO=16, PWR_R_ENERGY1_HI=17,
 PWR_R_SUM_I0_LO=18, PWR_R_SUM_I0_HI=19, PWR_R_SUM_Q0_LO=20, PWR_R_SUM_Q0_HI=21,
 PWR_R_SUM_I1_LO=22, PWR_R_SUM_I1_HI=23, PWR_R_SUM_Q1_LO=24, PWR_R_SUM_Q1_HI=25,
 PWR_R_TAP_CLIP_I0=26, PWR_R_TAP_CLIP_Q0=27,
 PWR_R_TAP_CLIP_I1=28, PWR_R_TAP_CLIP_Q1=29,
 PWR_R_ADC12_CONTACT0=30, PWR_R_ADC12_CONTACT1=31,
 PWR_R_PEAK0=32, PWR_R_PEAK1=33, PWR_R_SWEEP_LO=34, PWR_R_SWEEP_HI=35
};
#endif
