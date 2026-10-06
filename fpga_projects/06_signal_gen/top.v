`timescale 1ns / 1ps
// 06 Signal generator (DDS): sine, triangle, sawtooth, square, sweeps.
//   slot 0 info (project "DDSG"), slot 1 the generator
//   J6 pin 5: sigma-delta DAC (add 1 kohm + 10 nF), J6 pin 11: 8-bit PWM DAC (1 kohm + 100 nF),
//   J6 pin 12: square sync at the frequency, J5 + J8 (8 pins): 8-bit value for an R-2R ladder
module top (
    output wire       sd,
    output wire       pwm,
    inout  wire       sync,
    output wire [7:0] par,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_dds;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_dds));
    ardzy_info #(.SLOT(0), .PROJECT("DDSG"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire so, si;
    ardzy_dds #(.SLOT(1)) u_dds (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_dds), .sd_out(sd), .pwm_out(pwm), .sync_out(so), .par_out(par), .sync_in(si));
    IOBUF u_sync (.I(so), .T(1'b0), .O(si), .IO(sync));
endmodule
