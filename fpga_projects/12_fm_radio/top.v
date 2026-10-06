`timescale 1ns / 1ps
// 12 FM radio: an FM stereo transmitter with RDS (your station name and text), AM, CW, RTTY, PSK and more.
//   slot 0 info (project "FMTX"), slot 1 the radio registers, slot 2 the RDS blocks, slots 3..6 the MPX capture
//   J9 pin 11: the RF output (a short wire of 10 to 20 cm as the antenna, or a filter for anything more)
module top (
    inout  wire       rf,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_radio;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_radio));
    ardzy_info #(.SLOT(0), .PROJECT("FMTX"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire rf_o, rf_i;
    ardzy_radio #(.SLOT(1)) u_radio (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_radio), .rf_out(rf_o), .rf_pin(rf_i));
    IOBUF u_rf (.I(rf_o), .T(1'b0), .O(rf_i), .IO(rf));
endmodule
