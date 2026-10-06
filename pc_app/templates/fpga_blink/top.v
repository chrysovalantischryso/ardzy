// top: what the built-in toolchain builds (Build FPGA). The ARM gives the clock (FCLK0, 100 MHz).
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    ardzy_clock u_clock (.clk(clk), .rstn(rstn));      // from the Ardzy library
    blink u_blink (.clk(clk), .leds(leds));
endmodule
