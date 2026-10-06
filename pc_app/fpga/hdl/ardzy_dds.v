// Ardzy FPGA library: ardzy_dds, signal generator (direct digital synthesis).
//
// A 32-bit phase grows by FREQ every clock: frequency = FREQ * 100 MHz / 2^32 (0.023 Hz steps).
// Outputs, all at the same time:
//   sd_out   1-bit sigma-delta DAC: add an RC low-pass (1 kohm + 10 nF) for a clean analog signal
//   pwm_out  8-bit PWM DAC, 390.6 kHz carrier (RC low-pass: 1 kohm + 100 nF)
//   sync_out square wave at the frequency (the phase's top bit): for a scope trigger or a clock
//   par_out  8-bit sample for an R-2R resistor ladder
// Registers (word index):
//   0 CTRL      [0] outputs on  [1] sweep running  [2] sweep repeats (else stops at SWEEP_STOP)
//   1 FREQ      phase step (frequency); also where a sweep starts
//   2 WAVE      0 sine, 1 triangle, 2 sawtooth, 3 square
//   3 AMP       amplitude 0..65535 (65535 = full scale)
//   4 OFFSET    signed, added after the amplitude (-32768..32767)
//   5 DUTY      square wave high part, 0..65535 (32768 = 50 %)
//   6 SWEEP_STOP   phase step where a sweep ends
//   7 SWEEP_STEP   added to the phase step every SWEEP_RATE clocks (signed: sweeps down when negative)
//   8 SWEEP_RATE   clocks between sweep steps
//   9 PHASE     write: set the phase now
//  10 SAMPLE    (read) the output value now (signed 16 bit)
//  11 MEAS_HZ   (read) frequency measured at the sync pin over the last second
//  12 FREQ_NOW  (read) the phase step now (changes during a sweep)
//  13 ID        "DDSG"
`timescale 1ns / 1ps
module ardzy_dds #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg         sd_out = 1'b0,
    output reg         pwm_out = 1'b0,
    output reg         sync_out = 1'b0,
    output reg  [7:0]  par_out = 8'd0,
    input  wire        sync_in               // sync pin read back at the pad
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    reg [2:0]  ctrl = 3'b001;
    reg [31:0] freq = 32'd42950, fnow = 32'd42950;        // 1 kHz
    reg [1:0]  wave = 2'd0;
    reg [15:0] amp = 16'd65535, duty = 16'd32768;
    reg signed [15:0] offset = 16'sd0;
    reg [31:0] sw_stop = 32'd0, sw_rate = 32'd100000, swc = 32'd0;
    reg signed [31:0] sw_step = 32'sd0;
    reg [31:0] phase = 32'd0;

    // stage 1: sine table (1 clock) and the other waves from the phase
    wire signed [15:0] sine;
    ardzy_sine_rom u_rom (.clk(clk), .a(phase[31:22]), .q(sine));
    reg [31:0] ph1 = 32'd0;
    always @(posedge clk) ph1 <= phase;
    wire [15:0] tri_u = ph1[31] ? ~ph1[30:15] : ph1[30:15];
    wire signed [15:0] tri_s = tri_u ^ 16'h8000;
    wire signed [15:0] saw_s = ph1[31:16] ^ 16'h8000;
    wire signed [15:0] sq_s  = (ph1[31:16] < duty) ? 16'sd32767 : -16'sd32767;
    reg signed [15:0] w2 = 16'sd0;
    reg signed [32:0] m3 = 33'sd0;
    reg signed [17:0] s4 = 18'sd0;
    reg signed [15:0] sample = 16'sd0;
    always @(posedge clk) begin
        case (wave)                                            // stage 2
            2'd0: w2 <= sine;
            2'd1: w2 <= tri_s;
            2'd2: w2 <= saw_s;
            default: w2 <= sq_s;
        endcase
        m3 <= w2 * $signed({1'b0, amp});                       // stage 3: amplitude (DSP)
        s4 <= (m3 >>> 16) + offset;                            // stage 4: offset
        sample <= (s4 > 18'sd32767) ? 16'sd32767 : (s4 < -18'sd32768 ? -16'sd32768 : s4[15:0]);
    end

    // outputs
    wire [15:0] u = sample ^ 16'h8000;                         // 0..65535, middle = 32768
    reg [16:0] sd_acc = 17'd0;
    reg [7:0]  pc = 8'd0;
    always @(posedge clk) begin
        sd_acc <= {1'b0, sd_acc[15:0]} + {1'b0, u};
        sd_out <= ctrl[0] & sd_acc[16];
        pc <= pc + 1'b1;
        pwm_out <= ctrl[0] & (pc < u[15:8]);
        sync_out <= ctrl[0] & ph1[31];
        par_out <= ctrl[0] ? u[15:8] : 8'd128;
    end

    // frequency meter at the sync pin: rising edges per second
    reg [2:0]  ms = 3'd0;
    reg [26:0] gc = 27'd0;
    reg [31:0] edges = 32'd0, meas = 32'd0;
    always @(posedge clk) begin
        ms <= {ms[1:0], sync_in};
        if (gc == 27'd99_999_999) begin gc <= 27'd0; meas <= edges + (ms[1] & ~ms[2]); edges <= 32'd0; end
        else begin gc <= gc + 1'b1; if (ms[1] & ~ms[2]) edges <= edges + 1'b1; end
    end

    // phase, sweep and registers
    always @(posedge clk) begin
        phase <= phase + fnow;
        if (ctrl[1]) begin
            if (swc + 1'b1 >= sw_rate) begin
                swc <= 32'd0;
                if ((sw_step >= 0) ? (fnow >= sw_stop) : (fnow <= sw_stop)) begin
                    if (ctrl[2]) fnow <= freq; else ctrl[1] <= 1'b0;
                end else fnow <= fnow + sw_step;
            end else swc <= swc + 1'b1;
        end
        if (!rstn) begin
            ctrl <= 3'b001; freq <= 32'd42950; fnow <= 32'd42950; wave <= 2'd0; amp <= 16'd65535; offset <= 16'sd0; duty <= 16'd32768;
        end else if (bus_we && sel) case (idx)
            10'd0: begin ctrl <= bus_wdata[2:0]; if (bus_wdata[1] && !ctrl[1]) begin fnow <= freq; swc <= 32'd0; end end
            10'd1: begin freq <= bus_wdata; fnow <= bus_wdata; end
            10'd2: wave <= bus_wdata[1:0];
            10'd3: amp <= bus_wdata[15:0];
            10'd4: offset <= bus_wdata[15:0];
            10'd5: duty <= bus_wdata[15:0];
            10'd6: sw_stop <= bus_wdata;
            10'd7: sw_step <= bus_wdata;
            10'd8: sw_rate <= (bus_wdata == 0) ? 32'd1 : bus_wdata;
            10'd9: phase <= bus_wdata;
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {29'd0, ctrl};
                10'd1: bus_rdata <= freq;
                10'd2: bus_rdata <= {30'd0, wave};
                10'd3: bus_rdata <= {16'd0, amp};
                10'd4: bus_rdata <= {{16{offset[15]}}, offset};
                10'd5: bus_rdata <= {16'd0, duty};
                10'd6: bus_rdata <= sw_stop;
                10'd7: bus_rdata <= sw_step;
                10'd8: bus_rdata <= sw_rate;
                10'd9: bus_rdata <= phase;
                10'd10: bus_rdata <= {{16{sample[15]}}, sample};
                10'd11: bus_rdata <= meas;
                10'd12: bus_rdata <= fnow;
                10'd13: bus_rdata <= 32'h44445347;         // "DDSG"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
