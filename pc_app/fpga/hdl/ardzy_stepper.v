// Ardzy FPGA library: ardzy_stepper, step/dir pulse generators with acceleration (stepper motor drivers
// such as A4988, DRV8825, TMC2208).
//
// Every 1 us each axis adds its speed to a 40-bit phase; every overflow is one step. The speed rises by
// ACCEL every microsecond up to VMAX, and falls again so the axis stops exactly at TARGET (the steps
// taken while speeding up are counted and the same number is kept for slowing down).
// Speed unit: steps per microsecond * 2^40 (blocks.py converts from steps per second).
// Registers, axis n at word 16*n:
//   +0 TARGET     position to go to (signed); writing it starts the move
//   +1 POSITION   where the axis is (signed); write sets it (only while standing still)
//   +2 VMAX_LO    top speed, bits 31..0       +3 VMAX_HI  top speed, bits 39..32
//   +4 ACCEL      speed change per microsecond
//   +5 VSTART     start / stop speed
//   +6 STATUS     (read) [0] moving [1] direction (1 = up) [2] slowing down [3] waiting for the direction pin
//   +7 SPEED      (read) speed now, bits 39..8
//   +8 PULSE      step pulse length in clocks (default 200 = 2 us)
//   +9 STOP       write 1: slow down and stop; 2: stop at once
//   +10 PIN_STEPS (read) steps seen at the STEP pin (read back at the pad); write clears
//   +11 DIR_SETUP clocks between a direction change and the first step (default 500 = 5 us)
//   +12 ACC_STEPS (read) steps kept for slowing down
// Global: word 64 ID "STEP"
`timescale 1ns / 1ps
module ardzy_stepper #(parameter [3:0] SLOT = 4'd0, parameter N = 2) (
    input  wire         clk,
    input  wire         rstn,
    input  wire [15:0]  bus_addr,
    input  wire [31:0]  bus_wdata,
    input  wire         bus_we,
    input  wire         bus_re,
    output reg  [31:0]  bus_rdata = 32'd0,
    output wire [N-1:0] step_out,
    output wire [N-1:0] dir_out,
    input  wire [N-1:0] step_in            // the STEP pins read back at the pad
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    reg [6:0] tc = 7'd0;
    wire tick = (tc == 7'd99);                           // every 1 us
    always @(posedge clk) tc <= tick ? 7'd0 : tc + 1'b1;

    wire [N*32-1:0] r_target, r_pos, r_accel, r_vstart, r_status, r_speed, r_pulse, r_pins, r_dset, r_acc;
    wire [N*40-1:0] r_vmax;
    genvar n;
    generate for (n = 0; n < N; n = n + 1) begin : ax
        reg signed [31:0] target = 32'sd0, pos = 32'sd0;
        reg [39:0] vmax = 40'd1099511627, inc = 40'd0, phase = 40'd0;   // vmax default 1000 steps/s
        reg [31:0] accel = 32'd1100, vstart = 32'd109951163;            // 1000 steps/s^2, 100 steps/s
        reg [31:0] acc_steps = 32'd0, pin_steps = 32'd0;
        reg [15:0] pulse = 16'd200, pc = 16'd0;
        reg [15:0] dir_setup = 16'd500, dsc = 16'd0;
        reg        moving = 1'b0, dir = 1'b1, decel = 1'b0, stop_req = 1'b0, starting = 1'b0;
        reg [2:0]  ps = 3'd0;
        wire wsel = bus_we && sel && (idx[9:4] == n);
        wire [3:0] wr = idx[3:0];
        assign step_out[n] = (pc != 16'd0);
        assign dir_out[n] = dir;

        // The tick's arithmetic is spread over 4 clocks (registered stages), so the 40-bit math meets
        // 100 MHz: stage 1 at the tick, stage 2 one clock later, stage 3, then the update (tk[2]).
        reg [2:0]  tk = 3'd0;
        reg [40:0] s_sum = 41'd0;
        reg signed [32:0] s_rem = 33'sd0, s_rema = 33'sd0;
        reg [39:0] s_incp = 40'd0, s_incm = 40'd0, vsa = 40'd0;
        reg        s_step = 1'b0, s_remle0 = 1'b0, s_cap = 1'b0, s_low = 1'b0, s_below = 1'b0, s_slow = 1'b0, s_zero = 1'b0;
        // Once slowing down has started it stays on (dlatch): between two steps the distance left is one more
        // than the steps kept for slowing, which would otherwise switch back to speeding up. It is dropped
        // only when the target moves further away.
        reg        dlatch = 1'b0;
        wire signed [32:0] rem = dir ? ({target[31], target} - {pos[31], pos}) : ({pos[31], pos} - {target[31], target});
        wire signed [31:0] pos_next = s_step ? (dir ? pos + 32'sd1 : pos - 32'sd1) : pos;

        always @(posedge clk) begin
            tk <= {tk[1:0], tick & moving};
            vsa <= {8'd0, vstart} + {8'd0, accel};
            if (tick) begin                                                 // stage 1
                s_sum <= {1'b0, phase} + {1'b0, inc};
                s_rem <= rem;
                s_incp <= inc + {8'd0, accel};
                s_incm <= inc - {8'd0, accel};
            end
            if (tk[0]) begin                                                // stage 2
                s_step <= s_sum[40];
                s_rema <= s_sum[40] ? s_rem - 33'sd1 : s_rem;
                s_remle0 <= (s_rem <= 0);
                s_cap <= (s_incp > vmax);
                s_low <= (inc <= vsa);
                s_below <= (inc < vmax);
            end
            if (tk[1]) begin                                                // stage 3
                s_slow <= stop_req || s_remle0 || (s_rema <= $signed({1'b0, acc_steps}))
                          || (dlatch && (s_rema <= $signed({1'b0, acc_steps}) + 33'sd1));
                s_zero <= (s_rema == 33'sd0);
            end
        end

        always @(posedge clk) begin
            ps <= {ps[1:0], step_in[n]};
            if (ps[1] && !ps[2]) pin_steps <= pin_steps + 1'b1;
            if (pc != 16'd0) pc <= pc - 1'b1;

            if (moving && tk[2]) begin                                     // stage 4: update
                phase <= s_sum[39:0];
                pos <= pos_next;
                if (s_step) pc <= pulse;
                decel <= s_slow;
                dlatch <= s_slow;
                if (s_step && s_zero) begin                                 // arrived
                    moving <= 1'b0; inc <= 40'd0; decel <= 1'b0; dlatch <= 1'b0;
                end else if (s_slow) begin
                    if (s_low) begin
                        if (stop_req || s_remle0) begin                     // stopped (asked to, or target is behind)
                            moving <= 1'b0; inc <= 40'd0; decel <= 1'b0;
                            if (stop_req) begin target <= pos_next; stop_req <= 1'b0; end
                        end else inc <= {8'd0, vstart};                    // crawl the last steps
                    end else inc <= s_incm;
                    if (s_step && acc_steps != 32'd0) acc_steps <= acc_steps - 1'b1;
                end else if (s_below) begin
                    inc <= s_cap ? vmax : s_incp;
                    if (s_step) acc_steps <= acc_steps + 1'b1;
                end
            end else if (!moving) begin
                // start a move: set the direction pin, wait DIR_SETUP, then go
                if (starting) begin
                    if (dsc == 16'd0) begin
                        starting <= 1'b0; moving <= 1'b1; inc <= {8'd0, vstart}; phase <= 40'd0; acc_steps <= 32'd0; dlatch <= 1'b0;
                    end else dsc <= dsc - 1'b1;
                end else if (target != pos && !stop_req) begin
                    starting <= 1'b1;
                    dsc <= (dir != (target > pos)) ? dir_setup : 16'd2;
                    dir <= (target > pos);
                end else stop_req <= 1'b0;
            end

            if (wsel) case (wr)
                4'd0: target <= bus_wdata;
                4'd1: if (!moving && !starting) begin pos <= bus_wdata; target <= bus_wdata; end
                4'd2: vmax[31:0] <= bus_wdata;
                4'd3: vmax[39:32] <= bus_wdata[7:0];
                4'd4: accel <= bus_wdata;
                4'd5: vstart <= bus_wdata;
                4'd8: pulse <= (bus_wdata[15:0] < 16'd10) ? 16'd10 : bus_wdata[15:0];
                4'd9: if (bus_wdata[1]) begin moving <= 1'b0; starting <= 1'b0; inc <= 40'd0; target <= pos; decel <= 1'b0; end
                      else if (bus_wdata[0]) begin if (moving) stop_req <= 1'b1; else begin starting <= 1'b0; target <= pos; end end
                4'd10: pin_steps <= 32'd0;
                4'd11: dir_setup <= bus_wdata[15:0];
                default: ;
            endcase
            if (!rstn) begin moving <= 1'b0; starting <= 1'b0; stop_req <= 1'b0; inc <= 40'd0; target <= pos; end
        end
        assign r_target[n*32 +: 32] = target;
        assign r_pos[n*32 +: 32] = pos;
        assign r_vmax[n*40 +: 40] = vmax;
        assign r_accel[n*32 +: 32] = accel;
        assign r_vstart[n*32 +: 32] = vstart;
        assign r_status[n*32 +: 32] = {28'd0, starting, decel, dir, moving};
        assign r_speed[n*32 +: 32] = inc[39:8];
        assign r_pulse[n*32 +: 32] = {16'd0, pulse};
        assign r_pins[n*32 +: 32] = pin_steps;
        assign r_dset[n*32 +: 32] = {16'd0, dir_setup};
        assign r_acc[n*32 +: 32] = acc_steps;
    end endgenerate

    wire [5:0] ra = idx[9:4];
    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx == 10'd64) bus_rdata <= 32'h53544550;          // "STEP"
        else if (ra >= N) bus_rdata <= 32'd0;
        else case (idx[3:0])
            4'd0: bus_rdata <= r_target[ra*32 +: 32];
            4'd1: bus_rdata <= r_pos[ra*32 +: 32];
            4'd2: bus_rdata <= r_vmax[ra*40 +: 32];
            4'd3: bus_rdata <= {24'd0, r_vmax[ra*40 + 32 +: 8]};
            4'd4: bus_rdata <= r_accel[ra*32 +: 32];
            4'd5: bus_rdata <= r_vstart[ra*32 +: 32];
            4'd6: bus_rdata <= r_status[ra*32 +: 32];
            4'd7: bus_rdata <= r_speed[ra*32 +: 32];
            4'd8: bus_rdata <= r_pulse[ra*32 +: 32];
            4'd10: bus_rdata <= r_pins[ra*32 +: 32];
            4'd11: bus_rdata <= r_dset[ra*32 +: 32];
            4'd12: bus_rdata <= r_acc[ra*32 +: 32];
            default: bus_rdata <= 32'd0;
        endcase
    end
endmodule
