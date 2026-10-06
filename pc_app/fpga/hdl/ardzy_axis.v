// Ardzy FPGA library: AXI-Stream building blocks.
//
// AXI-Stream: data moves from a source to a sink when tvalid (source has data) and tready (sink takes it)
// are both high at a clock edge. tlast marks the last word of a frame (a packet).
//   ardzy_axis_fifo     first-in first-out buffer (LUT RAM, DEPTH up to 64)
//   ardzy_axis_32to8    32-bit words -> 4 bytes (lowest byte first)
//   ardzy_axis_crc32    CRC-32 (the zlib / Ethernet one) of each frame of bytes
//   ardzy_axis_arb2     two sources into one, whole frames at a time, taking turns
//   ardzy_axis_counter  source: counting words, frames of LEN words, as fast as the sink takes them
//   ardzy_axis_meter    sink: counts words per second, checks a counting sequence, can slow down on purpose
`timescale 1ns / 1ps

module ardzy_axis_fifo #(parameter W = 32, parameter AW = 6) (
    input  wire         clk,
    input  wire         rst,
    input  wire [W-1:0] s_tdata,
    input  wire         s_tlast,
    input  wire         s_tvalid,
    output wire         s_tready,
    output wire [W-1:0] m_tdata,
    output wire         m_tlast,
    output wire         m_tvalid,
    input  wire         m_tready,
    output wire [AW:0]  level
);
    (* ram_style = "distributed" *) reg [W:0] mem [0:(1 << AW) - 1];
    reg [AW:0] wp = 0, rp = 0;
    assign level = wp - rp;
    assign s_tready = (level != (1 << AW));
    assign m_tvalid = (level != 0);
    assign {m_tlast, m_tdata} = mem[rp[AW-1:0]];
    always @(posedge clk) begin
        if (rst) begin wp <= 0; rp <= 0; end
        else begin
            if (s_tvalid && s_tready) begin mem[wp[AW-1:0]] <= {s_tlast, s_tdata}; wp <= wp + 1'b1; end
            if (m_tvalid && m_tready) rp <= rp + 1'b1;
        end
    end
endmodule

module ardzy_axis_32to8 (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] s_tdata,
    input  wire        s_tlast,
    input  wire        s_tvalid,
    output wire        s_tready,
    output wire [7:0]  m_tdata,
    output wire        m_tlast,
    output wire        m_tvalid,
    input  wire        m_tready
);
    reg [1:0] k = 2'd0;
    assign m_tdata = s_tdata[8*k +: 8];
    assign m_tvalid = s_tvalid;
    assign m_tlast = s_tlast && (k == 2'd3);
    assign s_tready = m_tready && (k == 2'd3);
    always @(posedge clk) begin
        if (rst) k <= 2'd0;
        else if (m_tvalid && m_tready) k <= k + 1'b1;
    end
endmodule

module ardzy_axis_crc32 (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  s_tdata,
    input  wire        s_tlast,
    input  wire        s_tvalid,
    output wire        s_tready,
    output reg  [31:0] crc = 32'd0,          // CRC of the last whole frame
    output reg  [31:0] frames = 32'd0,
    output reg  [31:0] bytes = 32'd0
);
    assign s_tready = 1'b1;
    reg [31:0] c = 32'hFFFFFFFF;
    function [31:0] step8(input [31:0] cin, input [7:0] d);
        integer i;
        reg [31:0] x;
        begin
            x = cin ^ {24'd0, d};
            for (i = 0; i < 8; i = i + 1) x = x[0] ? (x >> 1) ^ 32'hEDB88320 : (x >> 1);
            step8 = x;
        end
    endfunction
    wire [31:0] nxt = step8(c, s_tdata);
    always @(posedge clk) begin
        if (rst) begin c <= 32'hFFFFFFFF; frames <= 32'd0; bytes <= 32'd0; end
        else if (s_tvalid) begin
            bytes <= bytes + 1'b1;
            if (s_tlast) begin crc <= ~nxt; c <= 32'hFFFFFFFF; frames <= frames + 1'b1; end
            else c <= nxt;
        end
    end
endmodule

module ardzy_axis_arb2 #(parameter W = 32) (
    input  wire         clk,
    input  wire         rst,
    input  wire [W-1:0] s0_tdata, input wire s0_tlast, input wire s0_tvalid, output wire s0_tready,
    input  wire [W-1:0] s1_tdata, input wire s1_tlast, input wire s1_tvalid, output wire s1_tready,
    output wire [W-1:0] m_tdata,
    output wire         m_tlast,
    output wire         m_tvalid,
    input  wire         m_tready,
    output wire         m_src                 // which source the word comes from
);
    reg busy = 1'b0, cur = 1'b0, last = 1'b1;
    // pick a source at a frame boundary: the other one first (take turns)
    // last = the source of the previous frame; prefer the other one when it has data
    wire pick = last ? (s0_tvalid ? 1'b0 : 1'b1) : (s1_tvalid ? 1'b1 : 1'b0);
    wire src = busy ? cur : pick;
    assign m_src = src;
    assign m_tdata = src ? s1_tdata : s0_tdata;
    assign m_tlast = src ? s1_tlast : s0_tlast;
    assign m_tvalid = src ? s1_tvalid : s0_tvalid;
    assign s0_tready = m_tready && !src;
    assign s1_tready = m_tready && src;
    always @(posedge clk) begin
        if (rst) begin busy <= 1'b0; last <= 1'b1; end
        else if (m_tvalid && m_tready) begin
            if (m_tlast) begin busy <= 1'b0; last <= src; end
            else begin busy <= 1'b1; cur <= src; end
        end
    end
endmodule

module ardzy_axis_counter (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire [15:0] len,                  // words per frame
    input  wire [31:0] tag,                  // added to every word (to tell sources apart)
    output wire [31:0] m_tdata,
    output wire        m_tlast,
    output wire        m_tvalid,
    input  wire        m_tready,
    output reg  [31:0] sent = 32'd0
);
    reg [31:0] n = 32'd0;
    reg [15:0] k = 16'd0;
    assign m_tdata = n + tag;
    assign m_tlast = (k + 1'b1 >= len);
    assign m_tvalid = enable;
    always @(posedge clk) begin
        if (rst) begin n <= 32'd0; k <= 16'd0; sent <= 32'd0; end
        else if (m_tvalid && m_tready) begin
            n <= n + 1'b1; sent <= sent + 1'b1;
            k <= m_tlast ? 16'd0 : k + 1'b1;
        end
    end
endmodule

module ardzy_axis_meter (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] s_tdata,
    input  wire        s_tlast,
    input  wire        s_tvalid,
    output wire        s_tready,
    input  wire [7:0]  slow,                 // 0 = always ready; n = ready 1 clock in n+1 (back pressure)
    output reg  [31:0] per_sec = 32'd0,      // words in the last second
    output reg  [31:0] words = 32'd0,
    output reg  [31:0] errors = 32'd0        // words that did not follow the counting sequence
);
    reg [7:0]  sc = 8'd0;
    reg [26:0] gc = 27'd0;
    reg [31:0] in_gate = 32'd0, expect_v = 32'd0;
    reg        first = 1'b1;
    assign s_tready = (sc == 8'd0);
    always @(posedge clk) begin
        sc <= (sc >= slow) ? 8'd0 : sc + 1'b1;
        if (gc == 27'd99_999_999) begin gc <= 27'd0; per_sec <= in_gate + (s_tvalid && s_tready); in_gate <= 32'd0; end
        else begin gc <= gc + 1'b1; if (s_tvalid && s_tready) in_gate <= in_gate + 1'b1; end
        if (rst) begin words <= 32'd0; errors <= 32'd0; first <= 1'b1; end
        else if (s_tvalid && s_tready) begin
            words <= words + 1'b1;
            if (!first && s_tdata != expect_v) errors <= errors + 1'b1;
            expect_v <= s_tdata + 1'b1; first <= 1'b0;
        end
    end
endmodule
