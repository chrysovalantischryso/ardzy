`timescale 1ns / 1ps
// 10 RISC-V: a third processor in the FPGA (RV32I, 16 KB RAM), programmed from Python on the ARM.
//   slot 0 info (project "RV32"), slot 1 the RISC-V registers, slots 2..5 its 16 KB RAM
//   The RISC-V drives the 4 LEDs and J8 (GPIO out, 4 pins) and reads J5 (GPIO in, 4 pins).
module top (
    output wire [3:0] gpio_out,
    input  wire [3:0] gpio_in,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_rv;
    wire [3:0]  wstrb, info_leds_n, rv_leds;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_rv));
    ardzy_info #(.SLOT(0), .PROJECT("RV32"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(info_leds_n));
    ardzy_rv32_system #(.SLOT(1)) u_rv (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_rv), .leds(rv_leds), .gpio_out(gpio_out), .gpio_in(gpio_in));
    assign leds = ~rv_leds;                     // the LEDs belong to the RISC-V program (active low)
endmodule
