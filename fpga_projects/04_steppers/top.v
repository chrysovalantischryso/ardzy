`timescale 1ns / 1ps
// 04 Steppers: two step/dir axes with acceleration for stepper motor drivers (A4988, DRV8825, TMC2208).
//   slot 0 info (project "STEP"), slot 1 the axes
//   axis 0: STEP = J8 pin 5, DIR = J8 pin 11      axis 1: STEP = J8 pin 12, DIR = J8 pin 15
module top (
    inout  wire [1:0] step,       // read back at the pad to count the real pulses
    output wire [1:0] dir,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_s;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_s));
    ardzy_info #(.SLOT(0), .PROJECT("STEP"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire [1:0] so, si;
    ardzy_stepper #(.SLOT(1), .N(2)) u_s (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_s), .step_out(so), .dir_out(dir), .step_in(si));
    IOBUF u_s0 (.I(so[0]), .T(1'b0), .O(si[0]), .IO(step[0]));
    IOBUF u_s1 (.I(so[1]), .T(1'b0), .O(si[1]), .IO(step[1]));
endmodule
