`timescale 1ns / 1ps
// 13 SHA-256 miner: slot 0 info (project "SHA2"), slot 1 the miner (see sha_miner.v)
//   LED 0 blinks while mining, LED 1 lights when a hash with enough zero bits was found;
//   LEDs 2 and 3 are the info block's (the ARM can set them).
module top (
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_sha;
    wire [3:0]  wstrb, info_leds_n;
    wire        mining, found;
    reg  [24:0] blink = 25'd0;
    always @(posedge clk) blink <= blink + 1'b1;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_sha));
    ardzy_info #(.SLOT(0), .PROJECT("SHA2"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    sha_miner #(.SLOT(1), .NU(3)) u_sha (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_sha), .mining_led(mining), .found_led(found));
    assign leds = {info_leds_n[3:2], ~found, ~(mining & blink[24])};      // active low
endmodule
