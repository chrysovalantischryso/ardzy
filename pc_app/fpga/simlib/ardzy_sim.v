// Ardzy simulation models: used ONLY when you press Simulate in the app (Icarus Verilog on the PC).
// They take the place of the parts the real chip gives (the ARM, its clock and bus, Xilinx primitives),
// so a design simulates exactly as written. The real ones are in fpga/hdl and are used to build the FPGA.
//
// From a testbench, talk to your design like the ARM does (u_soc / u_bus = the instance names in your top):
//   dut.u_soc.write_ctrl(0, 32'd5);          ctrl[0] = 5          (Python: MMIO(0x41200000).write(0, 5))
//   dut.u_soc.read_status(0, value);         value = status[0]    (Python: .read(0x80))
//   dut.u_bus.write(16'h1004, 32'd7);        slot 1, register 1   (Python: MMIO(0x43C00000).write(0x1004, 7))
//   dut.u_bus.read(16'h1004, value);
`timescale 1ns / 1ps

// ---------------------------------------------------------------- ARM side
module ardzy_soc #(parameter N_CTRL = 4, parameter N_STAT = 4) (
    output reg                  clk = 1'b0,
    output reg                  rstn = 1'b0,
    output reg [32*N_CTRL-1:0]  ctrl = {32*N_CTRL{1'b0}},
    input  wire [32*N_STAT-1:0] status
);
    always #5 clk = ~clk;                               // FCLK0, 100 MHz
    initial begin #100 rstn = 1'b1; end                 // reset for the first 100 ns
    task write_ctrl(input integer n, input [31:0] value);
        begin @(posedge clk); ctrl[32*n +: 32] <= value; @(posedge clk); end
    endtask
    task read_status(input integer n, output [31:0] value);
        begin @(posedge clk); value = status[32*n +: 32]; end
    endtask
endmodule

module ardzy_clock (output reg clk = 1'b0, output reg rstn = 1'b0);
    always #5 clk = ~clk;
    initial begin #100 rstn = 1'b1; end
endmodule

module ardzy_bus (
    output reg         clk = 1'b0,
    output reg         rstn = 1'b0,
    output reg  [15:0] bus_addr = 16'd0,
    output reg  [31:0] bus_wdata = 32'd0,
    output reg  [3:0]  bus_wstrb = 4'd0,
    output reg         bus_we = 1'b0,
    output reg         bus_re = 1'b0,
    input  wire [31:0] bus_rdata
);
    always #5 clk = ~clk;
    initial begin #100 rstn = 1'b1; end
    // address = byte address in the 64 KB window: slot * 16'h1000 + 4 * register
    task write(input [15:0] addr, input [31:0] data);
        begin
            @(posedge clk); bus_addr <= addr; bus_wdata <= data; bus_wstrb <= 4'hF; bus_we <= 1'b1;
            @(posedge clk); bus_we <= 1'b0; bus_wstrb <= 4'h0;
        end
    endtask
    task read(input [15:0] addr, output [31:0] data);
        begin
            @(posedge clk); bus_addr <= addr; bus_re <= 1'b1;
            @(posedge clk); bus_re <= 1'b0;
            repeat (3) @(posedge clk);                      // blocks answer within two clocks
            data = bus_rdata;
        end
    endtask
endmodule

// ---------------------------------------------------------------- Xilinx primitives
module BUFG (input I, output O); assign O = I; endmodule
module BUFGCE (input I, input CE, output O); assign O = I & CE; endmodule
module BUFH (input I, output O); assign O = I; endmodule
module IBUF (input I, output O); assign O = I; endmodule
module OBUF (input I, output O); assign O = I; endmodule
module OBUFT (input I, input T, output O); assign O = T ? 1'bz : I; endmodule
module IOBUF (inout IO, input I, input T, output O); assign IO = T ? 1'bz : I; assign O = IO; endmodule

module ODDR #(parameter DDR_CLK_EDGE = "OPPOSITE_EDGE", parameter INIT = 1'b0, parameter SRTYPE = "SYNC") (
    output reg Q = 1'b0, input C, input CE, input D1, input D2, input R, input S);
    reg d2_hold = 1'b0;
    always @(posedge C) if (R) Q <= 1'b0; else if (S) Q <= 1'b1; else if (CE) begin Q <= D1; d2_hold <= D2; end
    always @(negedge C) if (!R && !S && CE) Q <= (DDR_CLK_EDGE == "OPPOSITE_EDGE") ? D2 : d2_hold;
endmodule

module IDDR #(parameter DDR_CLK_EDGE = "OPPOSITE_EDGE", parameter SRTYPE = "SYNC") (
    output reg Q1 = 1'b0, output reg Q2 = 1'b0, input C, input CE, input D, input R, input S);
    reg neg = 1'b0;
    always @(negedge C) neg <= D;
    always @(posedge C) if (R) begin Q1 <= 1'b0; Q2 <= 1'b0; end else if (CE) begin Q1 <= D; Q2 <= neg; end
endmodule

// clock tiles: the output clocks follow the parameters; LOCKED goes high after 1 us
module MMCME2_BASE #(
    parameter real CLKIN1_PERIOD = 10.0, parameter real CLKFBOUT_MULT_F = 10.0, parameter integer DIVCLK_DIVIDE = 1,
    parameter real CLKOUT0_DIVIDE_F = 10.0, parameter integer CLKOUT1_DIVIDE = 10, parameter integer CLKOUT2_DIVIDE = 10,
    parameter integer CLKOUT3_DIVIDE = 10, parameter integer CLKOUT4_DIVIDE = 10, parameter integer CLKOUT5_DIVIDE = 10,
    parameter integer CLKOUT6_DIVIDE = 10, parameter real CLKOUT0_PHASE = 0.0, parameter real CLKFBOUT_PHASE = 0.0,
    parameter real CLKOUT0_DUTY_CYCLE = 0.5, parameter BANDWIDTH = "OPTIMIZED", parameter STARTUP_WAIT = "FALSE",
    parameter real REF_JITTER1 = 0.0, parameter CLKOUT4_CASCADE = "FALSE") (
    input CLKIN1, input CLKFBIN, input RST, input PWRDWN,
    output reg CLKOUT0 = 1'b0, output CLKOUT0B, output reg CLKOUT1 = 1'b0, output CLKOUT1B, output reg CLKOUT2 = 1'b0, output CLKOUT2B,
    output reg CLKOUT3 = 1'b0, output CLKOUT3B, output reg CLKOUT4 = 1'b0, output reg CLKOUT5 = 1'b0, output reg CLKOUT6 = 1'b0,
    output reg CLKFBOUT = 1'b0, output CLKFBOUTB, output reg LOCKED = 1'b0);
    localparam real VCO = CLKIN1_PERIOD * DIVCLK_DIVIDE / CLKFBOUT_MULT_F;     // ns
    assign CLKOUT0B = ~CLKOUT0; assign CLKOUT1B = ~CLKOUT1; assign CLKOUT2B = ~CLKOUT2; assign CLKOUT3B = ~CLKOUT3; assign CLKFBOUTB = ~CLKFBOUT;
    always @(posedge RST) LOCKED = 1'b0;
    always @(negedge RST) begin #1000; LOCKED = 1'b1; end
    initial begin #1000; if (!RST) LOCKED = 1'b1; end
    always begin #(VCO * CLKOUT0_DIVIDE_F / 2.0); CLKOUT0 = ~CLKOUT0; end
    always begin #(VCO * CLKOUT1_DIVIDE / 2.0); CLKOUT1 = ~CLKOUT1; end
    always begin #(VCO * CLKOUT2_DIVIDE / 2.0); CLKOUT2 = ~CLKOUT2; end
    always begin #(VCO * CLKOUT3_DIVIDE / 2.0); CLKOUT3 = ~CLKOUT3; end
    always begin #(VCO * CLKOUT4_DIVIDE / 2.0); CLKOUT4 = ~CLKOUT4; end
    always begin #(VCO * CLKOUT5_DIVIDE / 2.0); CLKOUT5 = ~CLKOUT5; end
    always begin #(VCO * CLKOUT6_DIVIDE / 2.0); CLKOUT6 = ~CLKOUT6; end
    always begin #(CLKIN1_PERIOD / 2.0); CLKFBOUT = ~CLKFBOUT; end
endmodule

module PLLE2_BASE #(
    parameter real CLKIN1_PERIOD = 10.0, parameter integer CLKFBOUT_MULT = 10, parameter integer DIVCLK_DIVIDE = 1,
    parameter integer CLKOUT0_DIVIDE = 10, parameter integer CLKOUT1_DIVIDE = 10, parameter integer CLKOUT2_DIVIDE = 10,
    parameter integer CLKOUT3_DIVIDE = 10, parameter integer CLKOUT4_DIVIDE = 10, parameter integer CLKOUT5_DIVIDE = 10,
    parameter real CLKOUT0_PHASE = 0.0, parameter real CLKOUT0_DUTY_CYCLE = 0.5, parameter BANDWIDTH = "OPTIMIZED",
    parameter STARTUP_WAIT = "FALSE", parameter real REF_JITTER1 = 0.0, parameter real CLKFBOUT_PHASE = 0.0) (
    input CLKIN1, input CLKFBIN, input RST, input PWRDWN,
    output reg CLKOUT0 = 1'b0, output reg CLKOUT1 = 1'b0, output reg CLKOUT2 = 1'b0, output reg CLKOUT3 = 1'b0,
    output reg CLKOUT4 = 1'b0, output reg CLKOUT5 = 1'b0, output reg CLKFBOUT = 1'b0, output reg LOCKED = 1'b0);
    localparam real VCO = CLKIN1_PERIOD * DIVCLK_DIVIDE / CLKFBOUT_MULT;
    always @(posedge RST) LOCKED = 1'b0;
    always @(negedge RST) begin #1000; LOCKED = 1'b1; end
    initial begin #1000; if (!RST) LOCKED = 1'b1; end
    always begin #(VCO * CLKOUT0_DIVIDE / 2.0); CLKOUT0 = ~CLKOUT0; end
    always begin #(VCO * CLKOUT1_DIVIDE / 2.0); CLKOUT1 = ~CLKOUT1; end
    always begin #(VCO * CLKOUT2_DIVIDE / 2.0); CLKOUT2 = ~CLKOUT2; end
    always begin #(VCO * CLKOUT3_DIVIDE / 2.0); CLKOUT3 = ~CLKOUT3; end
    always begin #(VCO * CLKOUT4_DIVIDE / 2.0); CLKOUT4 = ~CLKOUT4; end
    always begin #(VCO * CLKOUT5_DIVIDE / 2.0); CLKOUT5 = ~CLKOUT5; end
    always begin #(CLKIN1_PERIOD / 2.0); CLKFBOUT = ~CLKFBOUT; end
endmodule
