// SPDX-License-Identifier: GPL-2.0
//
// DSP-backed exact normalized-score reducer for the production TRACK_ONE
// contract.  The coefficient energy Eh is constant for every lag in one job,
// so comparing |C|^2/(Ex*Eh) is exactly equivalent to comparing |C|^2/Ex.
// A single unsigned 77x38 multiplier is shared by both component squares and
// both ratio cross-products.  This keeps the exact first-wins decision while
// moving the wide product out of slice logic on resource-constrained Zynq-7010.

`timescale 1ns/1ps

module starlink_pss_exact_track_reducer #(
  parameter integer RATE_MULTIPLIER = 4
) (
  input  wire                i_clk,
  input  wire                i_reset,

  input  wire                i_tuple_valid,
  output wire                o_tuple_ready,
  input  wire                i_tuple_first,
  input  wire                i_tuple_last,
  input  wire                i_include_eh,
  input  wire         [31:0] i_request_id,
  input  wire         [63:0] i_center_index,
  input  wire         [63:0] i_center_timestamp,
  input  wire signed [$clog2(64 * RATE_MULTIPLIER + 1)-1:0] i_lag,
  input  wire         [63:0] i_timestamp,
  input  wire         [31:0] i_coefficient_generation,
  input  wire signed  [47:0] i_c_re,
  input  wire signed  [47:0] i_c_im,
  input  wire signed  [47:0] i_ex,
  input  wire signed  [47:0] i_eh,
  input  wire          [8:0] i_saturation_events,

  output reg                 o_result_valid,
  input  wire                i_result_ready,
  output wire                o_result_score_valid,
  output wire                o_result_includes_eh,
  output wire         [31:0] o_result_request_id,
  output wire         [63:0] o_result_center_index,
  output wire         [63:0] o_result_center_timestamp,
  output wire signed [$clog2(64 * RATE_MULTIPLIER + 1)-1:0] o_result_lag,
  output wire         [63:0] o_result_timestamp,
  output wire         [31:0] o_result_coefficient_generation,
  output wire signed  [47:0] o_result_c_re,
  output wire signed  [47:0] o_result_c_im,
  output wire signed  [47:0] o_result_ex,
  output wire signed  [47:0] o_result_eh,
  output wire          [8:0] o_result_saturation_events,
  output wire         [76:0] o_result_score_numerator,
  output wire         [68:0] o_result_score_denominator,

  output reg          [31:0] o_processed_job_count,
  output reg          [31:0] o_emitted_result_count,
  output reg          [31:0] o_invalid_tuple_count,
  output reg          [31:0] o_bound_error_count,
  output reg          [31:0] o_protocol_error_count
);

  localparam integer LAG_WIDTH = $clog2(64 * RATE_MULTIPLIER + 1);
  localparam signed [LAG_WIDTH-1:0] FIRST_LAG =
      -30 * RATE_MULTIPLIER;
  localparam signed [LAG_WIDTH-1:0] LAST_LAG =
      30 * RATE_MULTIPLIER;

  generate
    if ((RATE_MULTIPLIER != 1) && (RATE_MULTIPLIER != 2) &&
        (RATE_MULTIPLIER != 4)) begin : g_invalid_rate_multiplier
      initial $fatal(1, "RATE_MULTIPLIER must be 1, 2, or 4");
    end
  endgenerate

  localparam [3:0] STATE_IDLE              = 4'd0;
  localparam [3:0] STATE_SQUARE_RE_WAIT    = 4'd1;
  localparam [3:0] STATE_SQUARE_RE_CAPTURE = 4'd2;
  localparam [3:0] STATE_SQUARE_IM_WAIT    = 4'd3;
  localparam [3:0] STATE_SQUARE_IM_CAPTURE = 4'd4;
  localparam [3:0] STATE_PREPARE           = 4'd5;
  localparam [3:0] STATE_LEFT_WAIT         = 4'd6;
  localparam [3:0] STATE_LEFT_CAPTURE      = 4'd7;
  localparam [3:0] STATE_RIGHT_WAIT        = 4'd8;
  localparam [3:0] STATE_RIGHT_COMPARE     = 4'd9;
  localparam [3:0] STATE_DECIDE            = 4'd10;
  localparam [3:0] STATE_ACCEPT            = 4'd11;
  localparam [3:0] STATE_ACCEPT_BAD        = 4'd12;
  localparam [3:0] STATE_OUTPUT            = 4'd13;

  function automatic [31:0] increment_saturating_32;
    input [31:0] value;
    begin
      increment_saturating_32 = (&value) ? value : value + 1'b1;
    end
  endfunction

  reg [3:0] state;
  reg job_active;
  reg drop_until_last;
  reg signed [LAG_WIDTH-1:0] expected_lag;
  reg current_is_better;

  // Datapath payload registers deliberately have no reset.  State and valid
  // bits quarantine them until written, reducing reset/control-set pressure.
  reg [76:0] multiply_a;
  reg [37:0] multiply_b;
  (* use_dsp = "yes" *) reg [114:0] multiply_product;

  // The explicit output register enables the DSP cascade's PREG stage.  No
  // reset is needed because each consuming state is reached only after the
  // corresponding operands have spent a complete cycle at the multiplier.
  always @(posedge i_clk)
    multiply_product <= multiply_a * multiply_b;

  reg [75:0] real_square;
  reg [76:0] current_magnitude_squared;
  reg [37:0] current_ex;
  reg [114:0] left_cross_product;

  reg winner_valid;
  reg [76:0] winner_magnitude_squared;
  reg [37:0] winner_ex;
  reg [31:0] winner_request_id;
  reg [63:0] winner_center_index;
  reg [63:0] winner_center_timestamp;
  reg signed [LAG_WIDTH-1:0] winner_lag;
  reg [63:0] winner_timestamp;
  reg [31:0] winner_coefficient_generation;
  reg signed [47:0] winner_c_re;
  reg signed [47:0] winner_c_im;
  reg signed [47:0] winner_eh;
  reg [8:0] winner_saturation_events;

  wire [47:0] absolute_c_re_wide = i_c_re[47] ?
      (~i_c_re[47:0] + 48'd1) : i_c_re[47:0];
  wire [47:0] absolute_c_im_wide = i_c_im[47] ?
      (~i_c_im[47:0] + 48'd1) : i_c_im[47:0];
  wire [37:0] absolute_c_re = absolute_c_re_wide[37:0];
  wire [37:0] absolute_c_im = absolute_c_im_wide[37:0];

  wire correlation_bound_legal =
      (i_c_re[47:38] == {10{i_c_re[38]}}) &&
      (i_c_im[47:38] == {10{i_c_im[38]}});
  wire energy_bound_legal =
      !(|i_ex[47:38]) && !(|i_eh[47:31]);
  wire tuple_score_legal =
      (i_ex > 48'sd0) && (i_eh > 48'sd0) &&
      (i_saturation_events == 9'd0) &&
      correlation_bound_legal && energy_bound_legal;

  wire expected_last = (i_lag == LAST_LAG);
  wire tuple_position_legal = !i_include_eh && (!job_active ?
      (i_tuple_first && !i_tuple_last && (i_lag == FIRST_LAG)) :
      (!i_tuple_first && (i_lag == expected_lag) &&
       (i_tuple_last == expected_last)));

  assign o_tuple_ready =
      ((state == STATE_IDLE) && drop_until_last) ||
      (state == STATE_ACCEPT) || (state == STATE_ACCEPT_BAD);

  assign o_result_score_valid = winner_valid;
  assign o_result_includes_eh = 1'b0;
  assign o_result_request_id = winner_request_id;
  assign o_result_center_index = winner_center_index;
  assign o_result_center_timestamp = winner_center_timestamp;
  assign o_result_lag = winner_lag;
  assign o_result_timestamp = winner_timestamp;
  assign o_result_coefficient_generation = winner_coefficient_generation;
  assign o_result_c_re = winner_c_re;
  assign o_result_c_im = winner_c_im;
  assign o_result_ex = {10'd0, winner_ex};
  assign o_result_eh = winner_eh;
  assign o_result_saturation_events = winner_saturation_events;
  assign o_result_score_numerator = winner_magnitude_squared;
  assign o_result_score_denominator = {31'd0, winner_ex};

  always @(posedge i_clk) begin
    if (i_reset) begin
      state <= STATE_IDLE;
      job_active <= 1'b0;
      drop_until_last <= 1'b0;
      expected_lag <= FIRST_LAG;
      current_is_better <= 1'b0;
      winner_valid <= 1'b0;
      o_result_valid <= 1'b0;
      o_processed_job_count <= 32'd0;
      o_emitted_result_count <= 32'd0;
      o_invalid_tuple_count <= 32'd0;
      o_bound_error_count <= 32'd0;
      o_protocol_error_count <= 32'd0;
    end else begin
      case (state)
        STATE_IDLE: begin
          if (drop_until_last) begin
            if (i_tuple_valid && o_tuple_ready && i_tuple_last)
              drop_until_last <= 1'b0;
          end else if (i_tuple_valid) begin
            if (!tuple_position_legal) begin
              o_protocol_error_count <=
                  increment_saturating_32(o_protocol_error_count);
              job_active <= 1'b0;
              winner_valid <= 1'b0;
              drop_until_last <= !i_tuple_last;
              state <= STATE_ACCEPT_BAD;
            end else begin
              if (!job_active) begin
                job_active <= 1'b1;
                winner_valid <= 1'b0;
              end
              if (!i_tuple_last)
                expected_lag <= i_lag + 1'b1;
              current_ex <= i_ex[37:0];
              multiply_a <= {39'd0, absolute_c_re};
              multiply_b <= absolute_c_re;
              state <= STATE_SQUARE_RE_WAIT;
            end
          end
        end

        STATE_SQUARE_RE_WAIT: begin
          state <= STATE_SQUARE_RE_CAPTURE;
        end

        STATE_SQUARE_RE_CAPTURE: begin
          real_square <= multiply_product[75:0];
          multiply_a <= {39'd0, absolute_c_im};
          multiply_b <= absolute_c_im;
          state <= STATE_SQUARE_IM_WAIT;
        end

        STATE_SQUARE_IM_WAIT: begin
          state <= STATE_SQUARE_IM_CAPTURE;
        end

        STATE_SQUARE_IM_CAPTURE: begin
          current_magnitude_squared <=
              {1'b0, real_square} + {1'b0, multiply_product[75:0]};
          state <= STATE_PREPARE;
        end

        STATE_PREPARE: begin
          if (!tuple_score_legal) begin
            current_is_better <= 1'b0;
            o_invalid_tuple_count <=
                increment_saturating_32(o_invalid_tuple_count);
            if (!correlation_bound_legal || !energy_bound_legal)
              o_bound_error_count <=
                  increment_saturating_32(o_bound_error_count);
            state <= STATE_DECIDE;
          end else if (i_tuple_first || !winner_valid) begin
            current_is_better <= 1'b1;
            state <= STATE_DECIDE;
          end else begin
            // current/Ex_current > winner/Ex_winner iff the left exact
            // cross-product is strictly larger than the right one.
            multiply_a <= current_magnitude_squared;
            multiply_b <= winner_ex;
            state <= STATE_LEFT_WAIT;
          end
        end

        STATE_LEFT_WAIT: begin
          state <= STATE_LEFT_CAPTURE;
        end

        STATE_LEFT_CAPTURE: begin
          left_cross_product <= multiply_product;
          multiply_a <= winner_magnitude_squared;
          multiply_b <= current_ex;
          state <= STATE_RIGHT_WAIT;
        end

        STATE_RIGHT_WAIT: begin
          state <= STATE_RIGHT_COMPARE;
        end

        STATE_RIGHT_COMPARE: begin
          current_is_better <= left_cross_product > multiply_product;
          state <= STATE_DECIDE;
        end

        STATE_DECIDE: begin
          if (current_is_better) begin
            winner_valid <= 1'b1;
            winner_magnitude_squared <= current_magnitude_squared;
            winner_ex <= current_ex;
            winner_request_id <= i_request_id;
            winner_center_index <= i_center_index;
            winner_center_timestamp <= i_center_timestamp;
            winner_lag <= i_lag;
            winner_timestamp <= i_timestamp;
            winner_coefficient_generation <= i_coefficient_generation;
            winner_c_re <= i_c_re;
            winner_c_im <= i_c_im;
            winner_eh <= i_eh;
            winner_saturation_events <= i_saturation_events;
          end

          if (i_tuple_last) begin
            if (!current_is_better && !winner_valid) begin
              winner_request_id <= i_request_id;
              winner_center_index <= i_center_index;
              winner_center_timestamp <= i_center_timestamp;
              winner_lag <= {LAG_WIDTH{1'b0}};
              winner_timestamp <= 64'd0;
              winner_coefficient_generation <= i_coefficient_generation;
              winner_c_re <= 48'sd0;
              winner_c_im <= 48'sd0;
              winner_ex <= 38'd0;
              winner_eh <= 48'sd0;
              winner_saturation_events <= 9'd0;
              winner_magnitude_squared <= 77'd0;
            end
            o_processed_job_count <=
                increment_saturating_32(o_processed_job_count);
          end
          state <= STATE_ACCEPT;
        end

        STATE_ACCEPT: begin
          if (i_tuple_valid && o_tuple_ready) begin
            if (i_tuple_last) begin
              job_active <= 1'b0;
              o_result_valid <= 1'b1;
              state <= STATE_OUTPUT;
            end else begin
              state <= STATE_IDLE;
            end
          end
        end

        STATE_ACCEPT_BAD: begin
          if (i_tuple_valid && o_tuple_ready)
            state <= STATE_IDLE;
        end

        STATE_OUTPUT: begin
          if (o_result_valid && i_result_ready) begin
            o_result_valid <= 1'b0;
            o_emitted_result_count <=
                increment_saturating_32(o_emitted_result_count);
            state <= STATE_IDLE;
          end
        end

        default: begin
          state <= STATE_IDLE;
          job_active <= 1'b0;
          drop_until_last <= 1'b0;
          winner_valid <= 1'b0;
          o_result_valid <= 1'b0;
        end
      endcase
    end
  end

endmodule
