// ardzy_io_top: the pin-control design for the built-in open toolchain (no Vivado, no IP cores).
// Same address map and registers as the Vivado build (build.tcl):
//   0x4120_0000  GPIO (AXI GPIO compatible): ch1 = j1..j8, ch2 = j9, LEDs, TP1, board ID, I2C
//   0x43C0_0000  ardzy_ctl: pin functions, PWM, measuring, UART, logic analyzer, DNA, fans
// The ARM side (PS7 + AXI bridge) comes from the Ardzy library (pc_app/fpga/hdl/ardzy_axi.v).
`timescale 1ns / 1ps
module ardzy_io_top (
    inout  wire [48:0] pins,
    output wire        fan_pwm,
    input  wire [5:0]  fan_tach
);
    wire clk, rstn;
    wire [31:0] awaddr, wdata, araddr, rdata;
    wire [3:0]  awlen, wstrb, arlen;
    wire [1:0]  awsize, awburst, arsize, arburst, bresp, rresp;
    wire [11:0] awid, arid, bid, rid;
    wire awvalid, awready, wlast, wvalid, wready, bvalid, bready, arvalid, arready, rlast, rvalid, rready;
    ardzy_ps7 u_ps7 (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready));
    ardzy_io_core u_core (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .pins(pins), .fan_pwm(fan_pwm), .fan_tach(fan_tach));
endmodule

// everything except the PS7 (so it can be simulated with an AXI3 test master)
module ardzy_io_core (
    input wire clk, input wire rstn,
    input wire [31:0] awaddr, input wire [3:0] awlen, input wire [1:0] awsize, input wire [1:0] awburst,
    input wire [11:0] awid, input wire awvalid, output wire awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wlast, input wire wvalid, output wire wready,
    output wire [11:0] bid, output wire [1:0] bresp, output wire bvalid, input wire bready,
    input wire [31:0] araddr, input wire [3:0] arlen, input wire [1:0] arsize, input wire [1:0] arburst,
    input wire [11:0] arid, input wire arvalid, output wire arready,
    output wire [11:0] rid, output wire [31:0] rdata, output wire [1:0] rresp, output wire rlast,
    output wire rvalid, input wire rready,
    inout  wire [48:0] pins,
    output wire        fan_pwm,
    input  wire [5:0]  fan_tach
);
    // AXI4-Lite
    wire [31:0] l_awaddr, l_wdata, l_araddr, l_rdata;
    wire [3:0]  l_wstrb;
    wire l_awvalid, l_awready, l_wvalid, l_wready, l_bvalid, l_bready, l_arvalid, l_arready, l_rvalid, l_rready;
    ardzy_axi3_lite u_bridge (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .m_awaddr(l_awaddr), .m_awvalid(l_awvalid), .m_awready(l_awready),
        .m_wdata(l_wdata), .m_wstrb(l_wstrb), .m_wvalid(l_wvalid), .m_wready(l_wready),
        .m_bvalid(l_bvalid), .m_bready(l_bready),
        .m_araddr(l_araddr), .m_arvalid(l_arvalid), .m_arready(l_arready),
        .m_rdata(l_rdata), .m_rvalid(l_rvalid), .m_rready(l_rready));

    wire [31:0] g_awaddr, g_wdata, g_araddr, g_rdata, c_awaddr, c_wdata, c_araddr, c_rdata;
    wire [3:0]  g_wstrb, c_wstrb;
    wire g_awvalid, g_awready, g_wvalid, g_wready, g_bvalid, g_bready, g_arvalid, g_arready, g_rvalid, g_rready;
    wire c_awvalid, c_awready, c_wvalid, c_wready, c_bvalid, c_bready, c_arvalid, c_arready, c_rvalid, c_rready;
    ardzy_lite_mux #(.BASE0(32'h4120_0000), .MASK0(32'hFFFF_0000), .BASE1(32'h43C0_0000), .MASK1(32'hFFFF_0000)) u_mux (
        .clk(clk), .rstn(rstn),
        .awaddr(l_awaddr), .awvalid(l_awvalid), .awready(l_awready),
        .wdata(l_wdata), .wstrb(l_wstrb), .wvalid(l_wvalid), .wready(l_wready),
        .bvalid(l_bvalid), .bready(l_bready),
        .araddr(l_araddr), .arvalid(l_arvalid), .arready(l_arready),
        .rdata(l_rdata), .rvalid(l_rvalid), .rready(l_rready),
        .s0_awaddr(g_awaddr), .s0_awvalid(g_awvalid), .s0_awready(g_awready),
        .s0_wdata(g_wdata), .s0_wstrb(g_wstrb), .s0_wvalid(g_wvalid), .s0_wready(g_wready),
        .s0_bvalid(g_bvalid), .s0_bready(g_bready),
        .s0_araddr(g_araddr), .s0_arvalid(g_arvalid), .s0_arready(g_arready),
        .s0_rdata(g_rdata), .s0_rvalid(g_rvalid), .s0_rready(g_rready),
        .s1_awaddr(c_awaddr), .s1_awvalid(c_awvalid), .s1_awready(c_awready),
        .s1_wdata(c_wdata), .s1_wstrb(c_wstrb), .s1_wvalid(c_wvalid), .s1_wready(c_wready),
        .s1_bvalid(c_bvalid), .s1_bready(c_bready),
        .s1_araddr(c_araddr), .s1_arvalid(c_arvalid), .s1_arready(c_arready),
        .s1_rdata(c_rdata), .s1_rvalid(c_rvalid), .s1_rready(c_rready));

    wire [31:0] g1_o, g1_t, g1_i;
    wire [16:0] g2_o, g2_t, g2_i;
    ardzy_gpio #(.W1(32), .W2(17)) u_gpio (
        .clk(clk), .rstn(rstn),
        .awaddr(g_awaddr), .awvalid(g_awvalid), .awready(g_awready),
        .wdata(g_wdata), .wstrb(g_wstrb), .wvalid(g_wvalid), .wready(g_wready),
        .bvalid(g_bvalid), .bready(g_bready),
        .araddr(g_araddr), .arvalid(g_arvalid), .arready(g_arready),
        .rdata(g_rdata), .rvalid(g_rvalid), .rready(g_rready),
        .gpio1_o(g1_o), .gpio1_t(g1_t), .gpio1_i(g1_i), .gpio2_o(g2_o), .gpio2_t(g2_t), .gpio2_i(g2_i));

    wire [1:0] c_bresp, c_rresp;
    ardzy_ctl #(.DNA_CLK_MODE(0)) u_ctl (
        .s_axi_aclk(clk), .s_axi_aresetn(rstn),
        .s_axi_awaddr(c_awaddr[15:0]), .s_axi_awprot(3'd0), .s_axi_awvalid(c_awvalid), .s_axi_awready(c_awready),
        .s_axi_wdata(c_wdata), .s_axi_wstrb(c_wstrb), .s_axi_wvalid(c_wvalid), .s_axi_wready(c_wready),
        .s_axi_bresp(c_bresp), .s_axi_bvalid(c_bvalid), .s_axi_bready(c_bready),
        .s_axi_araddr(c_araddr[15:0]), .s_axi_arprot(3'd0), .s_axi_arvalid(c_arvalid), .s_axi_arready(c_arready),
        .s_axi_rdata(c_rdata), .s_axi_rresp(c_rresp), .s_axi_rvalid(c_rvalid), .s_axi_rready(c_rready),
        .gpio1_o(g1_o), .gpio1_t(g1_t), .gpio1_i(g1_i), .gpio2_o(g2_o), .gpio2_t(g2_t), .gpio2_i(g2_i),
        .pins(pins), .fan_pwm(fan_pwm), .fan_tach(fan_tach));
endmodule
