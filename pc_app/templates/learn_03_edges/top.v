// Lesson 3: edges, synchronizers and debouncing. A "button" (a bit the ARM sets, or a real button on
// J1 pin 5 to GND) is brought into the clock domain with two flip-flops, cleaned up (debounced) and its
// presses are counted. Each press toggles LED 0; LED 1 shows the button itself.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    input  wire       button_n              // J1 pin 5: a button to GND (the pin has a pull-up: 1 = released)
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl[0]: a "button" pressed by software  ctrl[1]: use the pin too
    wire [63:0] status;                     // status 0: presses counted  status 1: raw changes seen (bounces)
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire raw = ctrl[0] | (ctrl[1] & ~button_n);

    // 1. Synchronizer: an input that changes at any moment can catch a flip-flop "half way" (metastability).
    //    Two flip-flops in a row give it a whole clock to settle.
    reg s1 = 1'b0, s2 = 1'b0;
    always @(posedge clk) begin s1 <= raw; s2 <= s1; end

    // 2. Debounce: a real button bounces for a few milliseconds. Accept a new level only after it has been
    //    stable for 5 ms (500 000 clocks).
    reg [18:0] stable = 19'd0;
    reg clean = 1'b0;
    reg [31:0] bounces = 32'd0;
    reg s2_last = 1'b0;
    always @(posedge clk) begin
        s2_last <= s2;
        if (s2 != s2_last) bounces <= bounces + 1'b1;
        if (s2 == clean) stable <= 19'd0;
        else if (stable == 19'd499_999) begin clean <= s2; stable <= 19'd0; end
        else stable <= stable + 1'b1;
    end

    // 3. Edge detector: "pressed now and not pressed one clock ago" = a rising edge, high for exactly 1 clock.
    reg clean_last = 1'b0;
    wire press = clean & ~clean_last;
    reg [31:0] presses = 32'd0;
    reg toggle = 1'b0;
    always @(posedge clk) begin
        clean_last <= clean;
        if (press) begin presses <= presses + 1'b1; toggle <= ~toggle; end
    end

    assign leds = ~{2'b00, clean, toggle};
    assign status = {bounces, presses};
endmodule
