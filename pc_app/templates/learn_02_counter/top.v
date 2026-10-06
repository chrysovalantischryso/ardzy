// Lesson 2: the clock and a counter. A 32-bit counter adds 1 at every rising edge of the 100 MHz clock.
// Its bits toggle at 50 MHz, 25 MHz, 12.5 MHz ... each bit half as fast as the one before. Bits 23 to 26
// are slow enough to see (about 6, 3, 1.5 and 0.75 blinks per second). The ARM chooses which bits light the LEDs.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: which bit drives LED 0 (the LEDs show bits n .. n+3)
    wire [63:0] status;                     // status 0: the counter, status 1: rising edges of bit 26
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [31:0] count = 32'd0;               // a register: it keeps its value between clock edges
    always @(posedge clk)                   // at every rising edge of the clock ...
        count <= count + 1'b1;              // ... the counter takes its old value + 1

    wire [4:0] n = (ctrl[4:0] > 5'd28) ? 5'd28 : ctrl[4:0];
    assign leds = ~count[n +: 4];           // 4 bits, starting at bit n (default 0: too fast to see!)

    reg [31:0] blinks = 32'd0;              // count how often bit 26 goes from 0 to 1
    reg last26 = 1'b0;
    always @(posedge clk) begin
        last26 <= count[26];
        if (count[26] && !last26) blinks <= blinks + 1'b1;
    end
    assign status = {blinks, count};
endmodule
