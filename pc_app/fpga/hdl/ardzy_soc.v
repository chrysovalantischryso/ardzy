// Ardzy FPGA library: the easy way to talk to the ARM from your Verilog.
//
//   ardzy_soc    clock + reset + registers:
//                ctrl[n]    written (and read back) by the ARM at 0x4120_0000 + 4*n   (n = 0..N_CTRL-1)
//                status[n]  read by the ARM at                    0x4120_0080 + 4*n   (n = 0..N_STAT-1)
//                From Python:  from ardzy import MMIO; r = MMIO(0x41200000); r.write(0, 5); r.read(0x80)
//                From C:      mmap /dev/mem at 0x41200000 (the c_program template shows how), then r[0] = 5;
//   ardzy_clock  only the clock (FCLK0, 100 MHz) for designs that do not talk to the ARM
//
// Any other address in the ARM's FPGA window reads 0, so a wrong address never stops the board.
// The registers are flat vectors: ctrl[31:0] is register 0, ctrl[63:32] register 1, and so on.
`timescale 1ns / 1ps
module ardzy_soc #(
    parameter N_CTRL = 4,                       // 1..32 registers written by the ARM
    parameter N_STAT = 4                        // 1..32 values read by the ARM
) (
    output wire                    clk,
    output wire                    rstn,
    output reg  [32*N_CTRL-1:0]    ctrl,
    input  wire [32*N_STAT-1:0]    status
);
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

    wire [31:0] l_awaddr, l_wdata, l_araddr;
    reg  [31:0] l_rdata;
    wire [3:0]  l_wstrb;
    wire l_awvalid, l_wvalid, l_bready, l_arvalid, l_rready;
    reg  l_awready, l_wready, l_bvalid, l_arready, l_rvalid;
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

    // our window: 0x4120_0000 .. 0x4120_FFFF; offsets 0x000-0x07C = ctrl, 0x080-0x0FC = status
    wire w_ours = (l_awaddr[31:16] == 16'h4120);
    wire r_ours = (l_araddr[31:16] == 16'h4120);
    wire [5:0] w_idx = l_awaddr[7:2];
    wire [5:0] r_idx = l_araddr[7:2];
    integer k;
    always @(posedge clk) begin
        if (!rstn) begin
            l_awready <= 1'b0; l_wready <= 1'b0; l_bvalid <= 1'b0;
            ctrl <= {32*N_CTRL{1'b0}};
        end else begin
            if (!l_awready && l_awvalid && l_wvalid && !l_bvalid) begin l_awready <= 1'b1; l_wready <= 1'b1; end
            else begin l_awready <= 1'b0; l_wready <= 1'b0; end
            if (l_awready && l_awvalid && l_wready && l_wvalid) begin
                l_bvalid <= 1'b1;
                if (w_ours && !w_idx[5] && w_idx < N_CTRL)
                    for (k = 0; k < 4; k = k + 1)
                        if (l_wstrb[k]) ctrl[32 * w_idx + 8 * k +: 8] <= l_wdata[8 * k +: 8];
            end else if (l_bvalid && l_bready)
                l_bvalid <= 1'b0;
        end
    end
    always @(posedge clk) begin
        if (!rstn) begin l_arready <= 1'b0; l_rvalid <= 1'b0; l_rdata <= 32'd0; end
        else begin
            if (!l_arready && l_arvalid && !l_rvalid) l_arready <= 1'b1;
            else l_arready <= 1'b0;
            if (l_arready && l_arvalid) begin
                l_rvalid <= 1'b1;
                if (!r_ours) l_rdata <= 32'd0;
                else if (!r_idx[5]) l_rdata <= (r_idx < N_CTRL) ? ctrl[32 * r_idx[4:0] +: 32] : 32'd0;
                else l_rdata <= (r_idx[4:0] < N_STAT) ? status[32 * r_idx[4:0] +: 32] : 32'd0;
            end else if (l_rvalid && l_rready)
                l_rvalid <= 1'b0;
        end
    end
endmodule

// only the clock (and a safe answer to any ARM access)
module ardzy_clock (
    output wire clk,
    output wire rstn
);
    wire [31:0] unused;
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) u_soc (.clk(clk), .rstn(rstn), .ctrl(unused), .status(32'd0));
endmodule
