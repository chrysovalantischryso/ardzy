// __NAME__: the EBAZ4205's two LEDs blink, made by the FPGA (no program needed).
// Press Build FPGA, then Upload. The clock comes from the ARM side (FCLK0, 100 MHz).
// The LEDs are on when their pin is 0. Your pins: leds.xdc (every pin of the board: ardzy_pins.xdc).
// The Ethernet is kept by the Ardzy build itself, in every design for this board.
module top (
    output wire led_green_n,
    output wire led_red_n
);
    wire clk, rstn;
    ardzy_clock u_clock (.clk(clk), .rstn(rstn));      // from the Ardzy library
    reg [26:0] cnt = 0;
    always @(posedge clk) cnt <= cnt + 1'b1;           // 2^27 / 100 MHz = 1.3 s per round
    assign led_green_n = ~cnt[26];                     // on half the time
    assign led_red_n = cnt[26] | ~cnt[23];             // short flashes while green is off
endmodule
