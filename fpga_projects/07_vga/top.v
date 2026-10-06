`timescale 1ns / 1ps
// 07 VGA: a 640 x 480 picture (320 x 240 pixels, 16 colours out of 64) on any VGA monitor.
//   slot 0 info (project "VGA6"), slot 1 registers, slots 2..11 the frame buffer
//   J6 pins 5/11/12/15 = red 1, red 0, green 1, green 0     J8 pins 5/11/12/15 = blue 1, blue 0, HSYNC, VSYNC
module top (
    output wire [1:0] red,
    output wire [1:0] green,
    output wire [1:0] blue,
    inout  wire       hsync,
    inout  wire       vsync,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_vga;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_vga));
    ardzy_info #(.SLOT(0), .PROJECT("VGA6"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire hs, vs, hs_i, vs_i;
    ardzy_vga #(.SLOT(1)) u_vga (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_vga), .red(red), .green(green), .blue(blue), .hsync(hs), .vsync(vs), .hs_in(hs_i), .vs_in(vs_i));
    IOBUF u_hs (.I(hs), .T(1'b0), .O(hs_i), .IO(hsync));
    IOBUF u_vs (.I(vs), .T(1'b0), .O(vs_i), .IO(vsync));
endmodule
