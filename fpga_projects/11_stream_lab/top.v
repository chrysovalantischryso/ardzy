`timescale 1ns / 1ps
// 11 Stream lab: AXI-Stream FIFO, width converter, CRC-32, arbiter, counter source and meter at work.
//   slot 0 info (project "AXIS"), slot 1 the stream lab (see streamlab.v)
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_s;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_s));
    ardzy_info #(.SLOT(0), .PROJECT("AXIS"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    streamlab #(.SLOT(1)) u_lab (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re), .bus_rdata(rd_s));
endmodule
