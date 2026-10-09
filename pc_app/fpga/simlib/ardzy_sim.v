// Ardzy simulation models: used ONLY when you press Simulate in the app (Icarus Verilog on the PC).
// They take the place of the parts the real chip gives (the ARM, its clock and bus, Xilinx primitives),
// so a design simulates exactly as written. The real ones are in fpga/hdl and are used to build the FPGA.
//
// From a testbench, talk to your design like the ARM does (u_soc / u_bus = the instance names in your top):
//   dut.u_soc.write_ctrl(0, 32'd5);          ctrl[0] = 5          (Python: MMIO(0x41200000).write(0, 5))
//   dut.u_soc.read_status(0, value);         value = status[0]    (Python: .read(0x80))
//   dut.u_bus.write(16'h1004, 32'd7);        slot 1, register 1   (Python: MMIO(0x43C00000).write(0x1004, 7))
//   dut.u_bus.read(16'h1004, value);
//   dut.u_bus.ddr_write(32'h00100000, 64'h1122334455667788);   the fake DDR of ardzy_bus_ddr (designs that read the DDR)
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

// ---------------------------------------------------------------- ARM side with the DDR read ports (ardzy_ddr.v)
// ardzy_bus_ddr = ardzy_bus + the HP ports: the same write/read tasks, a clock of 900 / CLK_DIV MHz like the
// real MMCM (100 MHz when CLK_DIV = 0), and a fake DDR that answers every read burst. Fill it from a testbench:
//   dut.u_bus.ddr_write(32'h0010_0000, 64'h0807060504030201);    // 8 bytes at a DDR address
// (the fake DDR keeps 1 MB: the address wraps around every 1 MB; a page table in the design still works)
module ardzy_sim_ddr #(parameter NP = 5, parameter WORDS = 131072, parameter LATENCY = 6) (
    input  wire clk,
    input  wire [NP * 32 - 1:0] dr_araddr, input wire [NP * 4 - 1:0] dr_arlen, input wire [NP - 1:0] dr_arvalid,
    output reg  [NP - 1:0] dr_arready = {NP{1'b1}}, output reg [NP * 64 - 1:0] dr_rdata = {NP * 64{1'b0}},
    output reg  [NP - 1:0] dr_rvalid = {NP{1'b0}}, output reg [NP - 1:0] dr_rlast = {NP{1'b0}},
    output wire [NP * 2 - 1:0] dr_rresp, input wire [NP - 1:0] dr_rready
);
    reg [63:0] mem [0:WORDS - 1];
    integer i;
    initial for (i = 0; i < WORDS; i = i + 1) mem[i] = 64'd0;
    assign dr_rresp = {NP * 2{1'b0}};                        // always OKAY
    task write(input [31:0] addr, input [63:0] data);
        mem[(addr >> 3) % WORDS] = data;
    endtask
    // one burst at a time per port: address, LATENCY clocks of waiting (like the DDR), then len + 1 beats
    reg [31:0] addr [0:NP - 1];
    reg [4:0]  left [0:NP - 1];
    reg [7:0]  wait_n [0:NP - 1];
    reg        busy [0:NP - 1];
    integer p;
    initial for (p = 0; p < NP; p = p + 1) begin busy[p] = 1'b0; left[p] = 0; wait_n[p] = 0; addr[p] = 0; end
    always @(posedge clk)
        for (p = 0; p < NP; p = p + 1) begin
            if (!busy[p]) begin
                if (dr_arvalid[p] && dr_arready[p]) begin
                    addr[p] <= dr_araddr[p * 32 +: 32]; left[p] <= dr_arlen[p * 4 +: 4] + 5'd1; wait_n[p] <= LATENCY;
                    busy[p] <= 1'b1; dr_arready[p] <= 1'b0;
                end
            end else if (wait_n[p] != 0) begin
                wait_n[p] <= wait_n[p] - 8'd1;
            end else if (!dr_rvalid[p] || dr_rready[p]) begin
                if (left[p] != 0) begin
                    dr_rdata[p * 64 +: 64] <= mem[(addr[p] >> 3) % WORDS];
                    dr_rvalid[p] <= 1'b1; dr_rlast[p] <= (left[p] == 5'd1);
                    addr[p] <= addr[p] + 32'd8; left[p] <= left[p] - 5'd1;
                end else begin
                    dr_rvalid[p] <= 1'b0; dr_rlast[p] <= 1'b0; busy[p] <= 1'b0; dr_arready[p] <= 1'b1;
                end
            end
        end
endmodule

module ardzy_bus_ddr #(parameter CLK_DIV = 0) (
    output reg         clk = 1'b0,
    output reg         rstn = 1'b0,
    output reg  [15:0] bus_addr = 16'd0,
    output reg  [31:0] bus_wdata = 32'd0,
    output reg  [3:0]  bus_wstrb = 4'd0,
    output reg         bus_we = 1'b0,
    output reg         bus_re = 1'b0,
    input  wire [31:0] bus_rdata,
    input  wire [5 * 32 - 1:0] dr_araddr, input wire [5 * 4 - 1:0] dr_arlen, input wire [4:0] dr_arvalid,
    output wire [4:0] dr_arready, output wire [5 * 64 - 1:0] dr_rdata, output wire [4:0] dr_rvalid,
    output wire [4:0] dr_rlast, output wire [9:0] dr_rresp, input wire [4:0] dr_rready
);
    localparam real HALF = CLK_DIV ? CLK_DIV * 1000.0 / 1800.0 : 5.0;      // ns: 900 / CLK_DIV MHz, or 100 MHz
    always #(HALF) clk = ~clk;
    initial begin #100 rstn = 1'b1; end
    ardzy_sim_ddr u_ddr (.clk(clk), .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid),
        .dr_arready(dr_arready), .dr_rdata(dr_rdata), .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp),
        .dr_rready(dr_rready));
    task ddr_write(input [31:0] addr, input [63:0] data);
        u_ddr.write(addr, data);
    endtask
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
            repeat (3) @(posedge clk);
            data = bus_rdata;
        end
    endtask
endmodule

// the PS part alone (for designs that use ardzy_ps7_ddr directly): its clock and the fake DDR; the AXI GP port idles
module ardzy_ps7_ddr #(parameter CLK_DIV = 0) (
    output reg         clk = 1'b0,
    output reg         rstn = 1'b0,
    output wire [31:0] awaddr, output wire [3:0] awlen, output wire [1:0] awsize, output wire [1:0] awburst,
    output wire [11:0] awid, output wire awvalid, input wire awready,
    output wire [31:0] wdata, output wire [3:0] wstrb, output wire wlast, output wire wvalid, input wire wready,
    input wire [11:0] bid, input wire [1:0] bresp, input wire bvalid, output wire bready,
    output wire [31:0] araddr, output wire [3:0] arlen, output wire [1:0] arsize, output wire [1:0] arburst,
    output wire [11:0] arid, output wire arvalid, input wire arready,
    input wire [11:0] rid, input wire [31:0] rdata, input wire [1:0] rresp, input wire rlast,
    input wire rvalid, output wire rready,
    input  wire [5 * 32 - 1:0] dr_araddr, input wire [5 * 4 - 1:0] dr_arlen, input wire [4:0] dr_arvalid,
    output wire [4:0] dr_arready, output wire [5 * 64 - 1:0] dr_rdata, output wire [4:0] dr_rvalid,
    output wire [4:0] dr_rlast, output wire [9:0] dr_rresp, input wire [4:0] dr_rready
);
    localparam real HALF = CLK_DIV ? CLK_DIV * 1000.0 / 1800.0 : 5.0;
    always #(HALF) clk = ~clk;
    initial begin #100 rstn = 1'b1; end
    assign {awaddr, awlen, awsize, awburst, awid, awvalid, wdata, wstrb, wlast, wvalid, bready} = 0;
    assign {araddr, arlen, arsize, arburst, arid, arvalid} = 0;
    assign rready = 1'b1;
    ardzy_sim_ddr u_ddr (.clk(clk), .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid),
        .dr_arready(dr_arready), .dr_rdata(dr_rdata), .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp),
        .dr_rready(dr_rready));
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
