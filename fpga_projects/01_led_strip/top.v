`timescale 1ns / 1ps
// 01 LED strip: WS2812 / NeoPixel driver with exact timing from the FPGA.
//   slot 0 info (project "LEDS"), slot 1 LED strip registers, slot 2 pixel memory (1024 LEDs)
//   strip data on J7 pin 5 (j7[0]); the pin is also read back to check the real pulses
module top (
    inout  wire       ws_pin,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_ws;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_ws));
    ardzy_info #(.SLOT(0), .PROJECT("LEDS"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire dout, pin_in;
    ardzy_ws2812 #(.SLOT(1)) u_ws (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_ws), .dout(dout), .pin_in(pin_in));
    IOBUF u_pin (.I(dout), .T(1'b0), .O(pin_in), .IO(ws_pin));
endmodule
