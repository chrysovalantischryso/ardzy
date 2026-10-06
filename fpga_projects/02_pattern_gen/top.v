`timescale 1ns / 1ps
// 02 Pattern generator: plays a table of up to 1024 steps on 16 pins (J5, J6, J7, J8), up to 100 MHz.
//   slot 0 info (project "PATG"), slot 1 registers, slot 2 the table
module top (
    inout  wire [15:0] pins,      // bit 0..3 = J5, 4..7 = J6, 8..11 = J7, 12..15 = J8
    output wire [3:0]  leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_pat;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_pat));
    ardzy_info #(.SLOT(0), .PROJECT("PATG"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire [15:0] o, oe, i;
    ardzy_pattern #(.SLOT(1), .W(16)) u_pat (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_pat), .pin_out(o), .pin_oe(oe), .pin_in(i));
    genvar k;
    generate for (k = 0; k < 16; k = k + 1) begin : io
        IOBUF u (.I(o[k]), .T(~oe[k]), .O(i[k]), .IO(pins[k]));
    end endgenerate
endmodule
