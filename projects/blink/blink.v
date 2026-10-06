// blink: the 4 LEDs count in binary, about 1.5 steps per second.
// Clock = FCLK0 from the ARM side (100 MHz).
// The board's LEDs are ACTIVE LOW (LED from 3.3 V via 220 ohm to the FPGA pin):
// a 0 on the pin lights the LED, so the counter is inverted on the way out.
module blink (
    input  wire       clk,
    output wire [3:0] leds
);
    reg [29:0] cnt = 0;
    always @(posedge clk) cnt <= cnt + 1'b1;
    assign leds = ~cnt[29:26];
endmodule
