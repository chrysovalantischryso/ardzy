// Ardzy FPGA library: ardzy_bus, the register bus of the Ardzy FPGA blocks (and the FPGA projects).
//
//   The ARM's window 0x43C0_0000 .. 0x43C0_FFFF (64 KB) is cut into 16 slots of 4 KB:
//   slot n starts at 0x43C0_0000 + n * 0x1000. Every block takes one or more slots.
//
//   Write: bus_we is high for one clock with bus_addr (byte address in the window), bus_wdata, bus_wstrb.
//   Read:  bus_re is high for one clock with bus_addr. The block answers on its own rdata output within
//          two clocks and keeps it; a block that is not addressed answers 0. The top ORs all answers.
//   An address outside the window, or a slot no block uses, reads 0, so the ARM never hangs.
//
//   From Python on the board:  from ardzy import MMIO; bus = MMIO(0x43C00000); bus.write(0x1000, 5)
//   The projects' blocks.py has a driver class for every block.
`timescale 1ns / 1ps
module ardzy_bus (
    output wire        clk,                 // 100 MHz (FCLK0)
    output wire        rstn,
    output reg  [15:0] bus_addr = 16'd0,
    output reg  [31:0] bus_wdata = 32'd0,
    output reg  [3:0]  bus_wstrb = 4'd0,
    output reg         bus_we = 1'b0,
    output reg         bus_re = 1'b0,
    input  wire [31:0] bus_rdata
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

// Slot 0 of every Ardzy FPGA project: who is loaded, a seconds counter and the 4 board LEDs.
//   0 MAGIC "ARDZ"   1 PROJECT (4 letters, e.g. "LEDS")   2 VERSION   3 SECONDS since the design started
//   4 LEDS (write/read, bit n = LED n on; the LEDs are active low on the board, handled here)
//   5 SCRATCH (write/read, free for tests)   6 CLOCK_HZ (100000000)
module ardzy_info #(parameter [3:0] SLOT = 4'd0, parameter [31:0] PROJECT = "TEST", parameter [31:0] VERSION = 32'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire [3:0]  leds_n                 // to the LED pins (active low)
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    reg [3:0]  led = 4'd0;
    reg [31:0] scratch = 32'd0, seconds = 32'd0;
    reg [26:0] tick = 27'd0;
    assign leds_n = ~led;
    always @(posedge clk) begin
        if (tick == 27'd99_999_999) begin tick <= 27'd0; seconds <= seconds + 1'b1; end
        else tick <= tick + 1'b1;
        if (bus_we && sel) case (idx)
            10'd4: led <= bus_wdata[3:0];
            10'd5: scratch <= bus_wdata;
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= 32'h4152445A;          // "ARDZ"
                10'd1: bus_rdata <= PROJECT;
                10'd2: bus_rdata <= VERSION;
                10'd3: bus_rdata <= seconds;
                10'd4: bus_rdata <= {28'd0, led};
                10'd5: bus_rdata <= scratch;
                10'd6: bus_rdata <= 32'd100_000_000;
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule

// Register helper for blocks: decodes the block's slot and the register (word) index.
//   sel  = this slot is addressed;  idx = word index inside the 4 KB slot (0..1023)
module ardzy_slot #(parameter [3:0] SLOT = 4'd0) (
    input  wire [15:0] bus_addr,
    output wire        sel,
    output wire [9:0]  idx
);
    assign sel = (bus_addr[15:12] == SLOT);
    assign idx = bus_addr[11:2];
endmodule
