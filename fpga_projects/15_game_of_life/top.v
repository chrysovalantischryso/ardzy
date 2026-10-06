`timescale 1ns / 1ps
// 15 Game of Life: slot 0 info (project "LIFE"), slot 1 the 64 x 64 life engine (see life.v)
//   LED 0 changes every 65536 generations (blinks fast while running)
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_life;
    wire [3:0]  wstrb, info_leds_n;
    wire        gen;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_life));
    ardzy_info #(.SLOT(0), .PROJECT("LIFE"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    life #(.SLOT(1)) u_life (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_life), .gen_led(gen));
    assign leds = {info_leds_n[3:1], ~gen};
endmodule
