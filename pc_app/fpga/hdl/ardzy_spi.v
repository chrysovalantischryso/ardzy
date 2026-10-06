// Ardzy FPGA library: ardzy_spi, SPI controller (master) with 64-word send and receive buffers.
//
// Registers (word index):
//   0 CTRL    [0] CPHA  [1] CPOL  (mode = CPOL*2 + CPHA)  [2] LSB first  [3] loopback (MISO = MOSI inside)
//             [4] automatic chip select (CS low while words are sent back to back)
//   1 DIV     SCLK = 100 MHz / (2 * (DIV + 1)):  0 = 50 MHz, 4 = 10 MHz, 49 = 1 MHz
//   2 WIDTH   bits per word, 1..32 (default 8)
//   3 TX      write: put a word in the send buffer (sending starts at once)
//   4 RX      read: take the oldest received word ([31] set when the buffer was empty)
//   5 STATUS  [6:0] words waiting to send  [14:8] received words waiting  [16] busy  [17] receive overflow
//   6 CS      [0] chip select level when automatic CS is off (1 = high = not selected)
//   7 ID      "SPIM"
`timescale 1ns / 1ps
module ardzy_spi #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg         sclk = 1'b0,
    output reg         mosi = 1'b0,
    input  wire        miso,
    output reg         cs_n = 1'b1
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    reg [4:0]  ctrl = 5'b10000;
    reg [15:0] div = 16'd49;
    reg [5:0]  width = 6'd8;
    reg        cs_manual = 1'b1, overflow = 1'b0;

    // buffers (LUT RAM)
    reg [31:0] txb [0:63];
    reg [31:0] rxb [0:63];
    reg [6:0]  tw = 7'd0, tr = 7'd0, rw = 7'd0, rr = 7'd0;
    wire [6:0] tx_n = tw - tr, rx_n = rw - rr;
    wire tx_full = (tx_n == 7'd64), rx_full = (rx_n == 7'd64);

    // engine
    reg        busy = 1'b0, hold = 1'b0;
    reg [31:0] sh_o = 32'd0, sh_i = 32'd0;
    reg [6:0]  edges = 7'd0;           // edges left in this word (2 per bit, up to 64)
    reg [15:0] hc = 16'd0;
    reg [1:0]  ms = 2'd0;
    wire cpha = ctrl[0], cpol = ctrl[1], lsb = ctrl[2], loop = ctrl[3], acs = ctrl[4];
    wire din = loop ? mosi : miso;
    wire [31:0] tx_word = txb[tr[5:0]];
    // the next bit to put out of a word
    function [31:0] align(input [31:0] w, input [5:0] n, input l);
        align = l ? w : (w << (6'd32 - n));            // MSB first: move the word's top bit to bit 31
    endfunction

    reg rx_push = 1'b0;
    reg [31:0] rx_word = 32'd0;
    always @(posedge clk) begin
        rx_push <= 1'b0;
        if (!rstn) begin
            busy <= 1'b0; hold <= 1'b0; sclk <= 1'b0; cs_n <= 1'b1; ctrl <= 5'b10000; div <= 16'd49; width <= 6'd8;
        end else if (!busy) begin
            sclk <= cpol;
            if (tx_n != 0) begin
                // load the next word; with CPHA = 0 the first bit goes out now
                sh_o <= align(tx_word, width, lsb);
                mosi <= lsb ? tx_word[0] : tx_word[width - 1'b1];
                tr <= tr + 1'b1;
                sh_i <= 32'd0;
                edges <= {width, 1'b0};
                busy <= 1'b1; hc <= 16'd0; hold <= 1'b0;
                if (acs) cs_n <= 1'b0;
            end else begin
                if (acs) begin if (hold) cs_n <= 1'b1; end else cs_n <= cs_manual;
                hold <= 1'b0;
            end
        end else begin
            if (hc >= div) begin
                hc <= 16'd0;
                sclk <= ~sclk;
                // edge number: leading (first) edges are when edges is even counting down from 2*width
                if (edges[0] == 1'b0) begin                // leading edge
                    if (!cpha) sh_i <= lsb ? {din, sh_i[31:1]} : {sh_i[30:0], din};
                    else begin                              // CPHA = 1: put the bit out on the leading edge
                        mosi <= lsb ? sh_o[0] : sh_o[31];
                        sh_o <= lsb ? (sh_o >> 1) : (sh_o << 1);
                    end
                end else begin                               // trailing edge
                    if (cpha) sh_i <= lsb ? {din, sh_i[31:1]} : {sh_i[30:0], din};
                    else if (edges != 7'd1) begin
                        sh_o <= lsb ? (sh_o >> 1) : (sh_o << 1);
                        mosi <= lsb ? sh_o[1] : sh_o[30];
                    end
                end
                if (edges == 7'd1) begin                     // word done
                    busy <= 1'b0; hold <= 1'b1;
                    rx_push <= 1'b1;
                end
                edges <= edges - 1'b1;
            end else hc <= hc + 1'b1;
        end
        if (rx_push) begin
            // received bits: MSB first collects at the bottom, LSB first at the top
            rx_word = lsb ? (sh_i >> (6'd32 - width)) : sh_i;
            if (!rx_full) begin rxb[rw[5:0]] <= rx_word; rw <= rw + 1'b1; end
            else overflow <= 1'b1;
        end

        if (bus_we && sel) case (idx)
            10'd0: ctrl <= bus_wdata[4:0];
            10'd1: div <= bus_wdata[15:0];
            10'd2: width <= (bus_wdata[5:0] == 0) ? 6'd1 : (bus_wdata[5:0] > 6'd32 ? 6'd32 : bus_wdata[5:0]);
            10'd3: if (!tx_full) begin txb[tw[5:0]] <= bus_wdata; tw <= tw + 1'b1; end
            10'd5: overflow <= 1'b0;
            10'd6: cs_manual <= bus_wdata[0];
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {27'd0, ctrl};
                10'd1: bus_rdata <= {16'd0, div};
                10'd2: bus_rdata <= {26'd0, width};
                10'd4: begin
                    if (rx_n != 0) begin bus_rdata <= rxb[rr[5:0]]; rr <= rr + 1'b1; end
                    else bus_rdata <= 32'h80000000;
                end
                10'd5: bus_rdata <= {14'd0, overflow, busy | (tx_n != 0), 1'b0, rx_n, 1'b0, tx_n};
                10'd6: bus_rdata <= {31'd0, cs_manual};
                10'd7: bus_rdata <= 32'h5350494D;          // "SPIM"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
