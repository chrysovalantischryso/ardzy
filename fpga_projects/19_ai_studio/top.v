`timescale 1ns / 1ps
// 19 AI Studio: slot 0 info (project "AIST"), slot 1 the DDR network engine (see mlp_ddr.v): the networks'
// weights stream from the board's DDR memory through the four HP ports.
//   LED 0 lights while a network runs
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_nn;
    wire [3:0]  wstrb, info_leds_n;
    wire        busy;
    wire [159:0] dr_araddr;
    wire [19:0]  dr_arlen;
    wire [4:0]   dr_arvalid, dr_arready, dr_rvalid, dr_rlast, dr_rready;
    wire [319:0] dr_rdata;
    wire [9:0]   dr_rresp;
    // its own 75 MHz clock (100 MHz was too fast on the chip for the DDR paths; FCLK0 stays 100 for other projects)
    ardzy_bus_ddr #(.CLK_DIV(12)) u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
        .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_nn),
        .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid), .dr_arready(dr_arready), .dr_rdata(dr_rdata),
        .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp), .dr_rready(dr_rready));
    ardzy_info #(.SLOT(0), .PROJECT("AIST"), .VERSION(1), .CLOCK_HZ(75_000_000)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    mlp_ddr #(.SLOT(1), .NP(2)) u_nn (     // 2 HP ports (HP0, HP2): 4 crowd the PS edge too much to route
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_nn), .busy_led(busy),
        .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid), .dr_arready(dr_arready), .dr_rdata(dr_rdata),
        .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp), .dr_rready(dr_rready));
    assign leds = {info_leds_n[3:1], ~busy};
endmodule
