// Lesson 4: PWM (pulse width modulation). A pin can only be 0 or 1, but switched fast enough the eye (or a
// motor, or a filter) sees the average. Each LED gets its own 8-bit brightness: a counter runs 0..255 and the
// LED is on while the counter is below the brightness. 100 MHz / 256 / 16 = 24 kHz: no flicker.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    output wire       pwm_pin               // J1 pin 11: the PWM of LED 0, for a scope or a logic analyzer
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: brightness of LED 3, 2, 1, 0 (one byte each)
    wire [31:0] status;                     // status: clocks LED 0 was on during the last 1024 periods
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [3:0] pre = 4'd0;                   // divide the clock by 16
    reg [7:0] ramp = 8'd0;                  // the PWM counter: 0, 1, ... 255, 0, ...
    always @(posedge clk) begin
        pre <= pre + 1'b1;
        if (pre == 4'd15) ramp <= ramp + 1'b1;
    end

    wire [3:0] on;
    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : ch
        assign on[i] = ramp < ctrl[8 * i +: 8];      // on while the counter is below the brightness
    end endgenerate
    assign leds = ~on;
    assign pwm_pin = on[0];

    // measure: how many clocks was LED 0 on during 1024 PWM periods (= the duty cycle x 4 194 304)
    reg [21:0] window = 22'd0;
    reg [31:0] high = 32'd0, high_last = 32'd0;
    always @(posedge clk) begin
        window <= window + 1'b1;
        if (window == 22'h3FFFFF) begin high_last <= high + on[0]; high <= 32'd0; end
        else if (on[0]) high <= high + 1'b1;
    end
    assign status = high_last;
endmodule
