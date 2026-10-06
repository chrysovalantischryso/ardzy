// Lesson 10: your own instrument. A DDS (direct digital synthesis) oscillator: a 32-bit phase grows by a step
// every clock and its top bits address a sine table (the library's ardzy_sine_rom). The ARM sets the step, reads
// samples and prints them for the app's Plotter. The same idea makes the signal generator of project 06 and the
// FM radio's carrier.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [63:0] ctrl;                       // ctrl 0: phase step per clock   ctrl 1: [15:0] amplitude, [17:16] wave
    wire [63:0] status;                     // status 0: the wave now (signed 16 bit)   status 1: the phase
    ardzy_soc #(.N_CTRL(2), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [31:0] phase = 32'd0;
    always @(posedge clk) phase <= phase + ctrl[31:0];         // frequency = step / 2^32 x 100 MHz

    wire signed [15:0] sine;
    ardzy_sine_rom rom (.clk(clk), .a(phase[31:22]), .q(sine)); // 1024 points per period

    wire signed [15:0] tri_w = phase[31] ? (16'sd32767 - $signed({1'b0, phase[30:16]}) * 2) : (-16'sd32767 + $signed({1'b0, phase[30:16]}) * 2);
    wire signed [15:0] saw = $signed(phase[31:16]);
    wire signed [15:0] sq  = phase[31] ? -16'sd32767 : 16'sd32767;
    reg  signed [15:0] wave;
    always @(*) case (ctrl[49:48])
        2'd0: wave = sine;
        2'd1: wave = tri_w;
        2'd2: wave = saw;
        default: wave = sq;
    endcase
    wire signed [31:0] scaled = wave * $signed({1'b0, ctrl[47:32]});
    reg signed [15:0] out = 16'sd0;
    always @(posedge clk) out <= scaled >>> 15;
    assign status = {phase, {16{out[15]}}, out};
    assign leds = ~(4'b0001 << phase[31:30]);                    // a light that goes round once per period
endmodule
