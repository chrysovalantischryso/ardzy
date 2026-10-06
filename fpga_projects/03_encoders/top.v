`timescale 1ns / 1ps
// 03 Encoders: two quadrature encoders on J5 (A, B each), position, speed and error counts in hardware.
//   slot 0 info (project "QUAD"), slot 1 the encoder counters
//   encoder 0: A = J5 pin 5, B = J5 pin 11      encoder 1: A = J5 pin 12, B = J5 pin 15
//   pin test: the built-in generator drives encoder 0's pins (only when asked to, nothing connected)
module top (
    inout  wire [3:0] enc,        // {B1, A1, B0, A0}
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_q;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_q));
    ardzy_info #(.SLOT(0), .PROJECT("QUAD"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire [3:0] i;
    wire ga, gb, gd;
    ardzy_quad #(.SLOT(1), .N(2)) u_q (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_q), .a_in({i[2], i[0]}), .b_in({i[3], i[1]}), .gen_a(ga), .gen_b(gb), .gen_drive(gd));
    IOBUF u_a0 (.I(ga), .T(~gd), .O(i[0]), .IO(enc[0]));
    IOBUF u_b0 (.I(gb), .T(~gd), .O(i[1]), .IO(enc[1]));
    IOBUF u_a1 (.I(1'b0), .T(1'b1), .O(i[2]), .IO(enc[2]));
    IOBUF u_b1 (.I(1'b0), .T(1'b1), .O(i[3]), .IO(enc[3]));
endmodule
