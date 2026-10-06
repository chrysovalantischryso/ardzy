// Ardzy FPGA library: the link between the Zynq's ARM (PS7, AXI GP0 port) and your logic,
// without Vivado IP. Used by the built-in open toolchain (Yosys + nextpnr).
//
//   ardzy_ps7        the PS7 block: FCLK0 clock (through a BUFG), reset, AXI GP0 master port
//   ardzy_axi3_lite  AXI3 (bursts, IDs) from the ARM  ->  simple AXI4-Lite, one word at a time
//   ardzy_lite_mux   one AXI4-Lite master -> 2 slaves by address; any other address answers 0
//   ardzy_gpio       2-channel GPIO with the same registers as the Xilinx AXI GPIO
//                    (0x0 DATA, 0x4 TRI, 0x8 DATA2, 0xC TRI2), so software works with both
//
// Every request from the ARM always gets an answer: a wrong address reads 0 and writes are
// ignored, it can never stop the bus.
`timescale 1ns / 1ps

// ------------------------------------------------------------------------------------- PS7
module ardzy_ps7 (
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
    input wire rvalid, output wire rready
);
    wire [3:0] fclk, fclk_rstn;
    BUFG u_bufg (.I(fclk[0]), .O(clk));
    reg [2:0] rs = 3'b000;
    always @(posedge clk) rs <= {rs[1:0], fclk_rstn[0]};
    assign rstn = rs[2];

    PS7 u_ps7 (
        .FCLKCLK(fclk), .FCLKRESETN(fclk_rstn), .FCLKCLKTRIGN(4'b0000),
        .MAXIGP0ACLK(clk),
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
endmodule

// --------------------------------------------------------------- AXI3 bursts -> AXI4-Lite
module ardzy_axi3_lite (
    input wire clk, input wire rstn,
    input wire [31:0] awaddr, input wire [3:0] awlen, input wire [1:0] awsize, input wire [1:0] awburst,
    input wire [11:0] awid, input wire awvalid, output reg awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wlast, input wire wvalid, output reg wready,
    output reg [11:0] bid, output wire [1:0] bresp, output reg bvalid, input wire bready,
    input wire [31:0] araddr, input wire [3:0] arlen, input wire [1:0] arsize, input wire [1:0] arburst,
    input wire [11:0] arid, input wire arvalid, output reg arready,
    output reg [11:0] rid, output reg [31:0] rdata, output wire [1:0] rresp, output reg rlast,
    output reg rvalid, input wire rready,
    // AXI4-Lite master
    output reg [31:0] m_awaddr, output reg m_awvalid, input wire m_awready,
    output reg [31:0] m_wdata, output reg [3:0] m_wstrb, output reg m_wvalid, input wire m_wready,
    input wire m_bvalid, output reg m_bready,
    output reg [31:0] m_araddr, output reg m_arvalid, input wire m_arready,
    input wire [31:0] m_rdata, input wire m_rvalid, output reg m_rready
);
    assign bresp = 2'b00;
    assign rresp = 2'b00;

    // ---------------- write: AW, then for every beat: W -> lite write -> lite response; then B
    localparam W_IDLE = 3'd0, W_DATA = 3'd1, W_LITE = 3'd2, W_RESP = 3'd3, W_B = 3'd4;
    reg [2:0]  ws;
    reg [3:0]  wlen, wbeat;
    reg [2:0]  winc;
    reg        wfixed, aw_done, w_done;
    always @(posedge clk) begin
        if (!rstn) begin
            ws <= W_IDLE; awready <= 1'b0; wready <= 1'b0; bvalid <= 1'b0;
            m_awvalid <= 1'b0; m_wvalid <= 1'b0; m_bready <= 1'b0;
        end else case (ws)
            W_IDLE: begin
                awready <= 1'b1;
                if (awvalid && awready) begin
                    awready <= 1'b0;
                    m_awaddr <= awaddr; wlen <= awlen; wbeat <= 4'd0; bid <= awid;
                    winc <= 3'd1 << awsize; wfixed <= (awburst == 2'b00);
                    wready <= 1'b1; ws <= W_DATA;
                end
            end
            W_DATA: if (wvalid && wready) begin
                wready <= 1'b0;
                m_wdata <= wdata; m_wstrb <= wstrb;
                m_awvalid <= 1'b1; m_wvalid <= 1'b1; aw_done <= 1'b0; w_done <= 1'b0;
                ws <= W_LITE;
            end
            W_LITE: begin
                if (m_awvalid && m_awready) begin m_awvalid <= 1'b0; aw_done <= 1'b1; end
                if (m_wvalid && m_wready) begin m_wvalid <= 1'b0; w_done <= 1'b1; end
                if ((aw_done || (m_awvalid && m_awready)) && (w_done || (m_wvalid && m_wready))) begin
                    m_bready <= 1'b1; ws <= W_RESP;
                end
            end
            W_RESP: if (m_bvalid && m_bready) begin
                m_bready <= 1'b0;
                if (wbeat == wlen) begin
                    bvalid <= 1'b1; ws <= W_B;
                end else begin
                    wbeat <= wbeat + 1'b1;
                    if (!wfixed) m_awaddr <= m_awaddr + winc;
                    wready <= 1'b1; ws <= W_DATA;
                end
            end
            W_B: if (bready) begin
                bvalid <= 1'b0; ws <= W_IDLE;
            end
            default: ws <= W_IDLE;
        endcase
    end

    // ---------------- read: AR, then for every beat: lite read -> R beat
    localparam R_IDLE = 2'd0, R_LITE = 2'd1, R_WAIT = 2'd2, R_OUT = 2'd3;
    reg [1:0] rs;
    reg [3:0] rlen, rbeat;
    reg [2:0] rinc;
    reg       rfixed;
    always @(posedge clk) begin
        if (!rstn) begin
            rs <= R_IDLE; arready <= 1'b0; rvalid <= 1'b0; rlast <= 1'b0; m_arvalid <= 1'b0; m_rready <= 1'b0;
        end else case (rs)
            R_IDLE: begin
                arready <= 1'b1;
                if (arvalid && arready) begin
                    arready <= 1'b0;
                    m_araddr <= araddr; rlen <= arlen; rbeat <= 4'd0; rid <= arid;
                    rinc <= 3'd1 << arsize; rfixed <= (arburst == 2'b00);
                    m_arvalid <= 1'b1; rs <= R_LITE;
                end
            end
            R_LITE: if (m_arvalid && m_arready) begin
                m_arvalid <= 1'b0; m_rready <= 1'b1; rs <= R_WAIT;
            end
            R_WAIT: if (m_rvalid && m_rready) begin
                m_rready <= 1'b0;
                rdata <= m_rdata; rlast <= (rbeat == rlen); rvalid <= 1'b1; rs <= R_OUT;
            end
            R_OUT: if (rready) begin
                rvalid <= 1'b0;
                if (rlast) rs <= R_IDLE;
                else begin
                    rbeat <= rbeat + 1'b1;
                    if (!rfixed) m_araddr <= m_araddr + rinc;
                    m_arvalid <= 1'b1; rs <= R_LITE;
                end
            end
        endcase
    end
endmodule

// --------------------------------------------------- AXI4-Lite: 1 master -> 2 slaves + "nothing"
// Slave n gets addresses where (addr & MASKn) == BASEn. Other addresses: writes ignored, reads 0.
module ardzy_lite_mux #(
    parameter [31:0] BASE0 = 32'h4120_0000, parameter [31:0] MASK0 = 32'hFFFF_0000,
    parameter [31:0] BASE1 = 32'h43C0_0000, parameter [31:0] MASK1 = 32'hFFFF_0000
) (
    input wire clk, input wire rstn,
    input wire [31:0] awaddr, input wire awvalid, output wire awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wvalid, output wire wready,
    output wire bvalid, input wire bready,
    input wire [31:0] araddr, input wire arvalid, output wire arready,
    output wire [31:0] rdata, output wire rvalid, input wire rready,
    // slave 0
    output wire [31:0] s0_awaddr, output wire s0_awvalid, input wire s0_awready,
    output wire [31:0] s0_wdata, output wire [3:0] s0_wstrb, output wire s0_wvalid, input wire s0_wready,
    input wire s0_bvalid, output wire s0_bready,
    output wire [31:0] s0_araddr, output wire s0_arvalid, input wire s0_arready,
    input wire [31:0] s0_rdata, input wire s0_rvalid, output wire s0_rready,
    // slave 1
    output wire [31:0] s1_awaddr, output wire s1_awvalid, input wire s1_awready,
    output wire [31:0] s1_wdata, output wire [3:0] s1_wstrb, output wire s1_wvalid, input wire s1_wready,
    input wire s1_bvalid, output wire s1_bready,
    output wire [31:0] s1_araddr, output wire s1_arvalid, input wire s1_arready,
    input wire [31:0] s1_rdata, input wire s1_rvalid, output wire s1_rready
);
    // the bridge holds the address steady for the whole transaction, so decoding is combinational
    wire w0 = (awaddr & MASK0) == BASE0, w1 = !w0 && (awaddr & MASK1) == BASE1, wn = !w0 && !w1;
    wire r0 = (araddr & MASK0) == BASE0, r1 = !r0 && (araddr & MASK1) == BASE1, rn = !r0 && !r1;

    assign s0_awaddr = awaddr; assign s1_awaddr = awaddr;
    assign s0_wdata = wdata;   assign s1_wdata = wdata;
    assign s0_wstrb = wstrb;   assign s1_wstrb = wstrb;
    assign s0_araddr = araddr; assign s1_araddr = araddr;
    assign s0_awvalid = awvalid && w0; assign s1_awvalid = awvalid && w1;
    assign s0_wvalid = wvalid && w0;   assign s1_wvalid = wvalid && w1;
    assign s0_bready = bready && w0;   assign s1_bready = bready && w1;
    assign s0_arvalid = arvalid && r0; assign s1_arvalid = arvalid && r1;
    assign s0_rready = rready && r0;   assign s1_rready = rready && r1;

    // "nothing" slave: accepts everything, answers OKAY / 0
    reg n_b, n_r;
    always @(posedge clk) begin
        if (!rstn) begin n_b <= 1'b0; n_r <= 1'b0; end
        else begin
            if (wn && awvalid && wvalid && !n_b) n_b <= 1'b1;
            else if (n_b && bready) n_b <= 1'b0;
            if (rn && arvalid && !n_r) n_r <= 1'b1;
            else if (n_r && rready) n_r <= 1'b0;
        end
    end
    wire n_wtake = wn && awvalid && wvalid && !n_b;
    wire n_rtake = rn && arvalid && !n_r;

    assign awready = w0 ? s0_awready : w1 ? s1_awready : n_wtake;
    assign wready  = w0 ? s0_wready  : w1 ? s1_wready  : n_wtake;
    assign bvalid  = w0 ? s0_bvalid  : w1 ? s1_bvalid  : n_b;
    assign arready = r0 ? s0_arready : r1 ? s1_arready : n_rtake;
    assign rvalid  = r0 ? s0_rvalid  : r1 ? s1_rvalid  : n_r;
    assign rdata   = r0 ? s0_rdata   : r1 ? s1_rdata   : 32'd0;
endmodule

// ------------------------------------------------------- GPIO with AXI GPIO compatible registers
module ardzy_gpio #(parameter W1 = 32, parameter W2 = 17) (
    input wire clk, input wire rstn,
    input wire [31:0] awaddr, input wire awvalid, output reg awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire wvalid, output reg wready,
    output reg bvalid, input wire bready,
    input wire [31:0] araddr, input wire arvalid, output reg arready,
    output reg [31:0] rdata, output reg rvalid, input wire rready,
    output reg [W1-1:0] gpio1_o, output reg [W1-1:0] gpio1_t, input wire [W1-1:0] gpio1_i,
    output reg [W2-1:0] gpio2_o, output reg [W2-1:0] gpio2_t, input wire [W2-1:0] gpio2_i
);
    function [31:0] merge(input [31:0] old, input [31:0] d, input [3:0] s);
        merge = {s[3] ? d[31:24] : old[31:24], s[2] ? d[23:16] : old[23:16],
                 s[1] ? d[15:8] : old[15:8], s[0] ? d[7:0] : old[7:0]};
    endfunction
    wire [31:0] o1 = gpio1_o, t1 = gpio1_t, o2 = gpio2_o, t2 = gpio2_t;
    wire w_hs = awready && awvalid && wready && wvalid;
    always @(posedge clk) begin
        if (!rstn) begin
            awready <= 1'b0; wready <= 1'b0; bvalid <= 1'b0;
            gpio1_o <= 0; gpio1_t <= {W1{1'b1}}; gpio2_o <= 0; gpio2_t <= {W2{1'b1}};
        end else begin
            if (!awready && awvalid && wvalid && !bvalid) begin awready <= 1'b1; wready <= 1'b1; end
            else begin awready <= 1'b0; wready <= 1'b0; end
            if (w_hs) begin                              // response only after the handshake
                bvalid <= 1'b1;
                case (awaddr[3:2])
                    2'd0: gpio1_o <= merge(o1, wdata, wstrb);
                    2'd1: gpio1_t <= merge(t1, wdata, wstrb);
                    2'd2: gpio2_o <= merge(o2, wdata, wstrb);
                    2'd3: gpio2_t <= merge(t2, wdata, wstrb);
                endcase
            end else if (bvalid && bready)
                bvalid <= 1'b0;
        end
    end
    always @(posedge clk) begin
        if (!rstn) begin arready <= 1'b0; rvalid <= 1'b0; rdata <= 32'd0; end
        else begin
            if (!arready && arvalid && !rvalid) arready <= 1'b1;
            else arready <= 1'b0;
            if (arready && arvalid) begin
                rvalid <= 1'b1;
                case (araddr[3:2])
                    2'd0: rdata <= gpio1_i;
                    2'd1: rdata <= gpio1_t;
                    2'd2: rdata <= gpio2_i;
                    2'd3: rdata <= gpio2_t;
                endcase
            end else if (rvalid && rready)
                rvalid <= 1'b0;
        end
    end
endmodule
