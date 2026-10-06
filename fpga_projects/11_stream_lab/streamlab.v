// 11 Stream lab: three small AXI-Stream chains made of the Ardzy library blocks (fpga/hdl/ardzy_axis.v).
//
//   A: ARM -> FIFO -> 32 to 8 bits -> CRC-32           (the ARM compares with Python's zlib.crc32)
//   B: counter source -> FIFO -> meter                 (words per second, sequence check, back pressure)
//   C: two counter sources -> arbiter -> FIFO -> ARM    (frames must arrive whole, taking turns)
// Registers (word index):
//   0 CTRL       [0] write 1: reset everything  [1] source B on  [2] sources C on
//   1 IN_DATA    write: a word into chain A        2 IN_LAST  write: the last word of a frame into chain A
//   3 CRC        (read) CRC-32 of the last frame   4 CRC_FRAMES (read)   5 CRC_BYTES (read)
//   6 B_PER_SEC  (read) words per second at the meter   7 B_WORDS (read)   8 B_ERRORS (read)
//   9 B_SLOW     meter back pressure: 0 = always ready, n = ready 1 clock in n+1
//  10 B_LEN      frame length of source B
//  11 C_DATA     read: take a word from chain C   12 C_LEVEL (read) words waiting
//  13 C_INFO     (read) about the last word taken: [0] last word of a frame [1] from source 1
//  14 A_LEVEL    (read) words waiting in chain A's FIFO
//  15 ID         "AXIS"
`timescale 1ns / 1ps
module streamlab #(parameter [3:0] SLOT = 4'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    reg  [2:0] ctrl = 3'd0;
    reg        rst = 1'b1;
    reg  [7:0] slow = 8'd0;
    reg  [15:0] blen = 16'd256;
    always @(posedge clk) begin
        rst <= !rstn || (bus_we && sel && idx == 10'd0 && bus_wdata[0]);
        if (bus_we && sel) case (idx)
            10'd0: ctrl <= {bus_wdata[2:1], 1'b0};
            10'd9: slow <= bus_wdata[7:0];
            10'd10: blen <= (bus_wdata[15:0] == 0) ? 16'd1 : bus_wdata[15:0];
            default: ;
        endcase
    end

    // ---------------- chain A
    wire a_push = bus_we && sel && (idx == 10'd1 || idx == 10'd2);
    wire [31:0] a_d;
    wire a_l, a_v, a_r, b8_v, b8_r, b8_l;
    wire [7:0] b8;
    wire [6:0] a_level;
    ardzy_axis_fifo #(.W(32), .AW(6)) a_fifo (.clk(clk), .rst(rst), .s_tdata(bus_wdata), .s_tlast(idx == 10'd2),
        .s_tvalid(a_push), .s_tready(), .m_tdata(a_d), .m_tlast(a_l), .m_tvalid(a_v), .m_tready(a_r), .level(a_level));
    ardzy_axis_32to8 a_w (.clk(clk), .rst(rst), .s_tdata(a_d), .s_tlast(a_l), .s_tvalid(a_v), .s_tready(a_r),
        .m_tdata(b8), .m_tlast(b8_l), .m_tvalid(b8_v), .m_tready(b8_r));
    wire [31:0] crc, crc_frames, crc_bytes;
    ardzy_axis_crc32 a_crc (.clk(clk), .rst(rst), .s_tdata(b8), .s_tlast(b8_l), .s_tvalid(b8_v), .s_tready(b8_r),
        .crc(crc), .frames(crc_frames), .bytes(crc_bytes));

    // ---------------- chain B
    wire [31:0] b_d, f_d;
    wire b_l, b_v, b_r, f_l, f_v, f_r;
    wire [31:0] b_sent, per_sec, words, errors;
    ardzy_axis_counter b_src (.clk(clk), .rst(rst), .enable(ctrl[1]), .len(blen), .tag(32'd0),
        .m_tdata(b_d), .m_tlast(b_l), .m_tvalid(b_v), .m_tready(b_r), .sent(b_sent));
    ardzy_axis_fifo #(.W(32), .AW(6)) b_fifo (.clk(clk), .rst(rst), .s_tdata(b_d), .s_tlast(b_l), .s_tvalid(b_v),
        .s_tready(b_r), .m_tdata(f_d), .m_tlast(f_l), .m_tvalid(f_v), .m_tready(f_r), .level());
    ardzy_axis_meter b_meter (.clk(clk), .rst(rst), .s_tdata(f_d), .s_tlast(f_l), .s_tvalid(f_v), .s_tready(f_r),
        .slow(slow), .per_sec(per_sec), .words(words), .errors(errors));

    // ---------------- chain C
    wire [31:0] c0_d, c1_d, m_d;
    wire c0_l, c0_v, c0_r, c1_l, c1_v, c1_r, m_l, m_v, m_r, m_src;
    ardzy_axis_counter c_src0 (.clk(clk), .rst(rst), .enable(ctrl[2]), .len(16'd3), .tag(32'h10000000),
        .m_tdata(c0_d), .m_tlast(c0_l), .m_tvalid(c0_v), .m_tready(c0_r), .sent());
    ardzy_axis_counter c_src1 (.clk(clk), .rst(rst), .enable(ctrl[2]), .len(16'd5), .tag(32'h20000000),
        .m_tdata(c1_d), .m_tlast(c1_l), .m_tvalid(c1_v), .m_tready(c1_r), .sent());
    ardzy_axis_arb2 #(.W(32)) c_arb (.clk(clk), .rst(rst),
        .s0_tdata(c0_d), .s0_tlast(c0_l), .s0_tvalid(c0_v), .s0_tready(c0_r),
        .s1_tdata(c1_d), .s1_tlast(c1_l), .s1_tvalid(c1_v), .s1_tready(c1_r),
        .m_tdata(m_d), .m_tlast(m_l), .m_tvalid(m_v), .m_tready(m_r), .m_src(m_src));
    wire [32:0] o_d;
    wire o_l, o_v;
    wire [6:0] o_level;
    wire o_pop = bus_re && sel && idx == 10'd11 && o_v;
    ardzy_axis_fifo #(.W(33), .AW(6)) c_fifo (.clk(clk), .rst(rst), .s_tdata({m_src, m_d}), .s_tlast(m_l),
        .s_tvalid(m_v), .s_tready(m_r), .m_tdata(o_d), .m_tlast(o_l), .m_tvalid(o_v), .m_tready(o_pop), .level(o_level));
    reg [1:0] c_info = 2'd0;

    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else case (idx)
            10'd0: bus_rdata <= {29'd0, ctrl};
            10'd3: bus_rdata <= crc;
            10'd4: bus_rdata <= crc_frames;
            10'd5: bus_rdata <= crc_bytes;
            10'd6: bus_rdata <= per_sec;
            10'd7: bus_rdata <= words;
            10'd8: bus_rdata <= errors;
            10'd9: bus_rdata <= {24'd0, slow};
            10'd10: bus_rdata <= {16'd0, blen};
            10'd11: begin bus_rdata <= o_v ? o_d[31:0] : 32'd0; c_info <= {o_d[32], o_l}; end
            10'd12: bus_rdata <= {25'd0, o_level};
            10'd13: bus_rdata <= {30'd0, c_info};
            10'd14: bus_rdata <= {25'd0, a_level};
            10'd15: bus_rdata <= 32'h41584953;          // "AXIS"
            default: bus_rdata <= 32'd0;
        endcase
    end
endmodule
