// Ardzy FPGA library: the DDR read ports. Like ardzy_bus (the ARM's register bus), plus 5 ports through which
// the FPGA reads the board's DDR memory by itself (DMA): port 0 = ACP (sees the ARM's caches, so data the ARM just
// wrote is always right), ports 1..4 = HP0..HP3 (straight to the DDR controller, the fastest; the ARM's caches
// must be written back first). Only reading: the FPGA can not change Linux's memory through these.
//
//   ardzy_bus_ddr  = ardzy_bus + dr_* ports      ardzy_ps7_ddr  = ardzy_ps7 + the same ports
//   CLK_DIV: 0 = FCLK0 as the clock (100 MHz); else an own clock of 900 MHz / CLK_DIV (12 = 75 MHz)
// Wired up: HP0 and HP2 only (dr_ ports 1 and 3): with all four HP ports the many wires at the PS edge did not
// route. The others (ACP, HP1, HP3) only get their valid inputs held at 0 and never answer.
// (generated from ardzy_bus.v / ardzy_axi.v, so the register bus works exactly like in every other project)
`timescale 1ns / 1ps

module ardzy_ps7_ddr #(parameter CLK_DIV = 0) (
    output wire        clk,          // FCLK0 (100 MHz after boot; the Ardzy app can change it)
    output wire        rstn,         // synchronous, active low
    // AXI3 master (GP0): the ARM writes / reads 0x4000_0000 .. 0x7FFF_FFFF here
    output wire [31:0] awaddr, output wire [3:0] awlen, output wire [1:0] awsize, output wire [1:0] awburst,
    output wire [11:0] awid, output wire awvalid, input wire awready,
    output wire [31:0] wdata, output wire [3:0] wstrb, output wire wlast, output wire wvalid, input wire wready,
    input wire [11:0] bid, input wire [1:0] bresp, input wire bvalid, output wire bready,
    output wire [31:0] araddr, output wire [3:0] arlen, output wire [1:0] arsize, output wire [1:0] arburst,
    output wire [11:0] arid, output wire arvalid, input wire arready,
    input wire [11:0] rid, input wire [31:0] rdata, input wire [1:0] rresp, input wire rlast,
    input wire rvalid, output wire rready,
    // DDR read ports (ACP = coherent with the ARM's caches; HP0..HP3 = straight to the DDR controller), each:
    // AR channel (address, beats - 1 of 8 bytes, valid / ready) and R channel (64-bit data, valid, last, ready)
    input  wire [5 * 32 - 1:0] dr_araddr, input wire [5 * 4 - 1:0] dr_arlen, input wire [4:0] dr_arvalid,
    output wire [4:0] dr_arready, output wire [5 * 64 - 1:0] dr_rdata, output wire [4:0] dr_rvalid,
    output wire [4:0] dr_rlast, output wire [9:0] dr_rresp, input wire [4:0] dr_rready
);
    wire [3:0] fclk, fclk_rstn;
    // CLK_DIV = 0: clk = FCLK0 (100 MHz). Otherwise the design makes its own clock, 900 MHz / CLK_DIV
    // (12: 75 MHz), with an MMCM from FCLK0; the PS's ports run on it too, so nothing crosses clocks.
    // FCLK0 itself is not changed: the next project finds it as it was.
    wire locked;
    generate if (CLK_DIV == 0) begin : direct
        BUFG u_bufg (.I(fclk[0]), .O(clk));
        assign locked = 1'b1;
    end else begin : own
        wire f0, fb_o, fb_i, c_o;
        BUFG u_bin (.I(fclk[0]), .O(f0));
        MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(CLK_DIV)) u_mmcm (
            .CLKIN1(f0), .CLKFBIN(fb_i), .CLKFBOUT(fb_o), .RST(~fclk_rstn[0]), .PWRDWN(1'b0), .CLKOUT0(c_o), .LOCKED(locked));
        BUFG u_bfb (.I(fb_o), .O(fb_i));
        BUFG u_bufg (.I(c_o), .O(clk));
    end endgenerate
    reg [2:0] rs = 3'b000;
    always @(posedge clk) rs <= {rs[1:0], fclk_rstn[0] & locked};
    assign rstn = rs[2];

    PS7 u_ps7 (
        .FCLKCLK(fclk), .FCLKRESETN(fclk_rstn), .FCLKCLKTRIGN(4'b0000),
        .MAXIGP0ACLK(clk),
        .SAXIACPARVALID(1'b0), .SAXIACPAWVALID(1'b0), .SAXIACPWVALID(1'b0),
        .SAXIHP0ACLK(clk), .SAXIHP0ARADDR(dr_araddr[32 +: 32]), .SAXIHP0ARLEN(dr_arlen[4 +: 4]), .SAXIHP0ARSIZE(2'd3), .SAXIHP0ARBURST(2'd1),
        .SAXIHP0ARCACHE(4'b0011), .SAXIHP0ARID(6'd0), .SAXIHP0RDISSUECAP1EN(1'b0), .SAXIHP0WRISSUECAP1EN(1'b0), .SAXIHP0ARPROT(3'd0), .SAXIHP0ARQOS(4'd0), .SAXIHP0ARLOCK(2'd0),
        .SAXIHP0ARVALID(dr_arvalid[1]), .SAXIHP0ARREADY(dr_arready[1]), .SAXIHP0RDATA(dr_rdata[64 +: 64]), .SAXIHP0RVALID(dr_rvalid[1]),
        .SAXIHP0RLAST(dr_rlast[1]), .SAXIHP0RRESP(dr_rresp[2 +: 2]), .SAXIHP0RREADY(dr_rready[1]),
        .SAXIHP0AWVALID(1'b0), .SAXIHP0WVALID(1'b0), .SAXIHP0BREADY(1'b1),
        .SAXIHP1ARVALID(1'b0), .SAXIHP1AWVALID(1'b0), .SAXIHP1WVALID(1'b0),
        .SAXIHP2ACLK(clk), .SAXIHP2ARADDR(dr_araddr[96 +: 32]), .SAXIHP2ARLEN(dr_arlen[12 +: 4]), .SAXIHP2ARSIZE(2'd3), .SAXIHP2ARBURST(2'd1),
        .SAXIHP2ARCACHE(4'b0011), .SAXIHP2ARID(6'd0), .SAXIHP2RDISSUECAP1EN(1'b0), .SAXIHP2WRISSUECAP1EN(1'b0), .SAXIHP2ARPROT(3'd0), .SAXIHP2ARQOS(4'd0), .SAXIHP2ARLOCK(2'd0),
        .SAXIHP2ARVALID(dr_arvalid[3]), .SAXIHP2ARREADY(dr_arready[3]), .SAXIHP2RDATA(dr_rdata[192 +: 64]), .SAXIHP2RVALID(dr_rvalid[3]),
        .SAXIHP2RLAST(dr_rlast[3]), .SAXIHP2RRESP(dr_rresp[6 +: 2]), .SAXIHP2RREADY(dr_rready[3]),
        .SAXIHP2AWVALID(1'b0), .SAXIHP2WVALID(1'b0), .SAXIHP2BREADY(1'b1),
        .SAXIHP3ARVALID(1'b0), .SAXIHP3AWVALID(1'b0), .SAXIHP3WVALID(1'b0),
        .MAXIGP0AWADDR(awaddr), .MAXIGP0AWLEN(awlen), .MAXIGP0AWSIZE(awsize), .MAXIGP0AWBURST(awburst),
        .MAXIGP0AWID(awid), .MAXIGP0AWVALID(awvalid), .MAXIGP0AWREADY(awready),
        .MAXIGP0WDATA(wdata), .MAXIGP0WSTRB(wstrb), .MAXIGP0WLAST(wlast), .MAXIGP0WVALID(wvalid),
        .MAXIGP0WREADY(wready),
        .MAXIGP0BID(bid), .MAXIGP0BRESP(bresp), .MAXIGP0BVALID(bvalid), .MAXIGP0BREADY(bready),
        .MAXIGP0ARADDR(araddr), .MAXIGP0ARLEN(arlen), .MAXIGP0ARSIZE(arsize), .MAXIGP0ARBURST(arburst),
        .MAXIGP0ARID(arid), .MAXIGP0ARVALID(arvalid), .MAXIGP0ARREADY(arready),
        .MAXIGP0RID(rid), .MAXIGP0RDATA(rdata), .MAXIGP0RRESP(rresp), .MAXIGP0RLAST(rlast),
        .MAXIGP0RVALID(rvalid), .MAXIGP0RREADY(rready)
    );
    // ports not wired up (see USED in the generator): never ready, never data
    assign dr_arready[0] = 1'b0; assign dr_rvalid[0] = 1'b0; assign dr_rlast[0] = 1'b0; assign dr_rdata[0 +: 64] = 64'd0; assign dr_rresp[0 +: 2] = 2'd0;
    assign dr_arready[2] = 1'b0; assign dr_rvalid[2] = 1'b0; assign dr_rlast[2] = 1'b0; assign dr_rdata[128 +: 64] = 64'd0; assign dr_rresp[4 +: 2] = 2'd0;
    assign dr_arready[4] = 1'b0; assign dr_rvalid[4] = 1'b0; assign dr_rlast[4] = 1'b0; assign dr_rdata[256 +: 64] = 64'd0; assign dr_rresp[8 +: 2] = 2'd0;
endmodule

module ardzy_bus_ddr #(parameter CLK_DIV = 0) (
    output wire        clk,                 // 100 MHz (FCLK0)
    output wire        rstn,
    output reg  [15:0] bus_addr = 16'd0,
    output reg  [31:0] bus_wdata = 32'd0,
    output reg  [3:0]  bus_wstrb = 4'd0,
    output reg         bus_we = 1'b0,
    output reg         bus_re = 1'b0,
    input  wire [31:0] bus_rdata,
    // DDR read ports (ACP = coherent with the ARM's caches; HP0..HP3 = straight to the DDR controller), each:
    // AR channel (address, beats - 1 of 8 bytes, valid / ready) and R channel (64-bit data, valid, last, ready)
    input  wire [5 * 32 - 1:0] dr_araddr, input wire [5 * 4 - 1:0] dr_arlen, input wire [4:0] dr_arvalid,
    output wire [4:0] dr_arready, output wire [5 * 64 - 1:0] dr_rdata, output wire [4:0] dr_rvalid,
    output wire [4:0] dr_rlast, output wire [9:0] dr_rresp, input wire [4:0] dr_rready
);
    wire [31:0] awaddr, wdata, araddr, rdata;
    wire [3:0]  awlen, wstrb, arlen;
    wire [1:0]  awsize, awburst, arsize, arburst, bresp, rresp;
    wire [11:0] awid, arid, bid, rid;
    wire awvalid, awready, wlast, wvalid, wready, bvalid, bready, arvalid, arready, rlast, rvalid, rready;
    ardzy_ps7_ddr #(.CLK_DIV(CLK_DIV)) u_ps7 (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid), .dr_arready(dr_arready), .dr_rdata(dr_rdata),
        .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp), .dr_rready(dr_rready));

    wire [31:0] l_awaddr, l_wdata, l_araddr;
    reg  [31:0] l_rdata = 32'd0;
    wire [3:0]  l_wstrb;
    wire l_awvalid, l_wvalid, l_bready, l_arvalid, l_rready;
    reg  l_awready = 1'b0, l_wready = 1'b0, l_bvalid = 1'b0, l_arready = 1'b0, l_rvalid = 1'b0;
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

    // one transfer at a time: writes first, then reads
    localparam IDLE = 3'd0, W1 = 3'd1, W2 = 3'd2, R1 = 3'd3, R2 = 3'd4, R3 = 3'd5, R1B = 3'd6;
    reg [2:0] st = IDLE;
    reg rwin = 1'b0;
    always @(posedge clk) begin
        bus_we <= 1'b0;
        bus_re <= 1'b0;
        if (!rstn) begin
            st <= IDLE; l_awready <= 1'b0; l_wready <= 1'b0; l_bvalid <= 1'b0; l_arready <= 1'b0; l_rvalid <= 1'b0;
        end else case (st)
        IDLE:
            if (l_awvalid && l_wvalid) begin
                l_awready <= 1'b1; l_wready <= 1'b1;
                bus_we <= (l_awaddr[31:16] == 16'h43C0);
                bus_addr <= l_awaddr[15:0]; bus_wdata <= l_wdata; bus_wstrb <= l_wstrb;
                st <= W1;
            end else if (l_arvalid) begin
                l_arready <= 1'b1;
                bus_re <= (l_araddr[31:16] == 16'h43C0);
                rwin <= (l_araddr[31:16] == 16'h43C0);
                bus_addr <= l_araddr[15:0];
                st <= R1;
            end
        W1: begin l_awready <= 1'b0; l_wready <= 1'b0; l_bvalid <= 1'b1; st <= W2; end
        W2: if (l_bready) begin l_bvalid <= 1'b0; st <= IDLE; end
        R1: begin l_arready <= 1'b0; st <= R1B; end                   // the blocks answer at this clock
        R1B: st <= R2;                                                 // ... or at this one (block RAM)
        R2: begin l_rdata <= rwin ? bus_rdata : 32'd0; l_rvalid <= 1'b1; st <= R3; end
        R3: if (l_rready) begin l_rvalid <= 1'b0; st <= IDLE; end
        default: st <= IDLE;
        endcase
    end
endmodule
