`timescale 1ns / 1ps
// 14 FIR filter lab: slot 0 info (project "FIR1"), slot 1 the filter (see fir_lab.v)
//   LED 0 lights while the filter works (dim at low sample rates, bright when it is busy all the time)
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_fir;
    wire [3:0]  wstrb, info_leds_n;
    wire        busy;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_fir));
    ardzy_info #(.SLOT(0), .PROJECT("FIR1"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    fir_lab #(.SLOT(1)) u_fir (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_fir), .busy_led(busy));
    assign leds = {info_leds_n[3:1], ~busy};
endmodule
