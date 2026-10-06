// Lesson 1: logic gates. The ARM sets three inputs a, b, c; the FPGA computes four functions of them
// and shows them on the LEDs. Nothing here has a clock: it is pure logic, the answer changes as soon as the
// inputs change (a few nanoseconds later).
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds                  // the board's 4 LEDs (active low: 0 = on)
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // register 0, written by the ARM at 0x4120_0000
    wire [31:0] status;                     // register 0, read by the ARM at 0x4120_0080
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire a = ctrl[0];                       // three inputs, from the ARM
    wire b = ctrl[1];
    wire c = ctrl[2];

    wire f_and  = a & b;                    // 1 only when a AND b are 1
    wire f_or   = a | b;                    // 1 when a OR b (or both) is 1
    wire f_xor  = a ^ b;                    // 1 when a and b are DIFFERENT
    wire f_maj  = (a & b) | (a & c) | (b & c);   // 1 when at least two of three are 1 (majority vote)

    wire [3:0] f = {f_maj, f_xor, f_or, f_and};
    assign leds   = ~f;                     // invert: the LED pins are active low
    assign status = {28'd0, f};             // the ARM can read the answers back
endmodule
