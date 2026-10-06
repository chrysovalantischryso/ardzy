`timescale 1ns / 1ps
// 16 AI in the FPGA: slot 0 info (project "NNET"), slot 1 the neural network engine (see nn_engine.v)
//   LED 0 lights while the network is thinking (a short flash for every digit)
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_nn;
    wire [3:0]  wstrb, info_leds_n;
    wire        busy;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_nn));
    ardzy_info #(.SLOT(0), .PROJECT("NNET"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    nn_engine #(.SLOT(1)) u_nn (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_nn), .busy_led(busy));
    assign leds = {info_leds_n[3:1], ~busy};
endmodule
