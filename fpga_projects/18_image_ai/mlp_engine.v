// mlp_engine: a general neural network engine for the Ardzy FPGA projects 17 (text) and 18 (images).
//
// It runs a network of up to 4 fully connected layers, one after the other. For every layer:
//   out[j] = act( (sum_i W[j][i] * in[i] + B[j]) >> SHIFT )
//   act 0: none, the 32-bit result goes to the SCORES (last layer only)   1: ReLU, kept in 0 .. 255
//   act 2: sigmoid, a 256-entry table: 255 / (1 + e^(-s/16)) for s = the result limited to -128 .. 127
// Inputs and the values between layers are bytes 0 .. 255, weights signed bytes, sums 32 bit: exactly like
// mlp_reference() in blocks.py, so every number can be checked bit for bit.
//
// 16 lanes work side by side; lane l computes the neurons l, 16 + l, 32 + l ... of every layer with its own
// block RAM of weights (2048 words of 4 weights) and its own biases (128). Each clock every lane multiplies
// 4 inputs: 64 multiplications per clock; two lanes share a DSP (see mlp_lane_pair below).
// The values between layers live in two buffers of 1024 bytes (layer 1 reads buffer A, writes B, layer 2 reads
// B, writes A ...). Each lane keeps its own part of the buffers, so 16 results are written at once.
//
// Registers (word index, slot SLOT):
//   0 CTRL    write 1: run the network (the input must be in buffer A)
//   1 STATUS  [0] busy  [1] a result is ready      2 RESULT the largest score's index (when the last act is 0)
//   3 CYCLES  clocks of the last run               4 LAYERS 1 .. 4        5 COUNT  runs since power-on
//   6 WADDR   where the next WDATA goes (then + 1):  lane * 2048 + word  for weights,
//             0x10000 + lane * 128 + n  for biases (neuron j = n * 16 + lane is in lane j % 16 ...)
//   7 WDATA   write: 4 weights (the lowest byte first) or one bias
//  16 + 8L .. 21 + 8L  layer L: IN4 (inputs / 4, 1 .. 256), OG (outputs / 16, 1 .. 64), WBASE (first weight word
//                      of the layer in every lane), BBASE (first bias), SHIFT (0 .. 31), ACT (0, 1, 2)
// 256 .. 511  buffer A (the input), 4 bytes per word     512 .. 767  buffer B
// 768 .. 1022 SCORES[j] (signed 32 bit)                    1023 ID
`timescale 1ns / 1ps
module mlp_engine #(parameter [3:0] SLOT = 4'd1, parameter [31:0] ID = 32'h4D4C5031) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        busy_led
);
    localparam LANES = 16;
    // The bus is registered once on the way in: its signals then reach the 16 lanes, spread over the chip, with a
    // whole clock to spare (a write takes effect one clock later; a read answers in the 2 clocks the bus allows).
    reg [15:0] a_r = 16'd0;
    reg [31:0] wd = 32'd0;
    reg        we_r = 1'b0, re_r = 1'b0;
    always @(posedge clk) begin a_r <= bus_addr; wd <= bus_wdata; we_r <= bus_we; re_r <= bus_re; end
    wire sel = (a_r[15:12] == SLOT);
    wire [9:0] idx = a_r[11:2];
    wire wr = we_r && sel;

    // ---- registers
    reg  [2:0]  layers = 3'd1;
    reg  [16:0] waddr = 17'd0;
    reg  [31:0] cycles = 32'd0, count = 32'd0, clk_count = 32'd0;
    reg  [7:0]  result = 8'd0;
    reg         ready = 1'b0;
    reg  [8:0]  c_in4 [0:3];
    reg  [6:0]  c_og [0:3];
    reg  [10:0] c_wbase [0:3];
    reg  [6:0]  c_bbase [0:3];
    reg  [4:0]  c_shift [0:3];
    reg  [1:0]  c_act [0:3];
    integer n;
    initial for (n = 0; n < 4; n = n + 1) begin
        c_in4[n] = 9'd1; c_og[n] = 7'd1; c_wbase[n] = 11'd0; c_bbase[n] = 7'd0; c_shift[n] = 5'd0; c_act[n] = 2'd0;
    end
    wire start = wr && idx == 10'd0 && wd[0];
    always @(posedge clk) if (wr) begin
        if (idx == 10'd4) layers <= (wd[2:0] == 3'd0) ? 3'd1 : (wd[2:0] > 3'd4 ? 3'd4 : wd[2:0]);
        if (idx == 10'd6) waddr <= wd[16:0];
        if (idx == 10'd7) waddr <= waddr + 1'b1;
        if (idx[9:5] == 5'b00000 && idx[4]) case (idx[2:0])            // 16 .. 31: layers 0, 1
            3'd0: c_in4[{1'b0, idx[3]}] <= wd[8:0];
            3'd1: c_og[{1'b0, idx[3]}] <= wd[6:0];
            3'd2: c_wbase[{1'b0, idx[3]}] <= wd[10:0];
            3'd3: c_bbase[{1'b0, idx[3]}] <= wd[6:0];
            3'd4: c_shift[{1'b0, idx[3]}] <= wd[4:0];
            3'd5: c_act[{1'b0, idx[3]}] <= wd[1:0];
            default: ;
        endcase
        if (idx[9:5] == 5'b00001 && !idx[4]) case (idx[2:0])           // 32 .. 47: layers 2, 3
            3'd0: c_in4[{1'b1, idx[3]}] <= wd[8:0];
            3'd1: c_og[{1'b1, idx[3]}] <= wd[6:0];
            3'd2: c_wbase[{1'b1, idx[3]}] <= wd[10:0];
            3'd3: c_bbase[{1'b1, idx[3]}] <= wd[6:0];
            3'd4: c_shift[{1'b1, idx[3]}] <= wd[4:0];
            3'd5: c_act[{1'b1, idx[3]}] <= wd[1:0];
            default: ;
        endcase
    end
    // the current layer's settings, copied when the layer starts (the pipeline uses them until it is empty)
    reg [1:0]  L = 2'd0;
    reg [8:0]  in4 = 9'd1;
    reg [6:0]  og = 7'd1;
    reg [6:0]  bbase = 7'd0;
    reg [4:0]  shift = 5'd0;
    reg [1:0]  act = 2'd0;
    reg        src = 1'b0;                 // the buffer this layer reads (0 = A); it writes the other one

    // ---- the state machine
    localparam S_IDLE = 3'd0, S_SETUP = 3'd1, S_RUN = 3'd2, S_DRAIN = 3'd3, S_MAX = 3'd4, S_END = 3'd5;
    reg [2:0]  state = S_IDLE;
    reg [10:0] laddr = 11'd0;              // the word every lane reads
    reg [8:0]  t = 9'd0;
    reg [6:0]  g = 7'd0;
    reg        iv = 1'b0, ifirst = 1'b0, ilast = 1'b0;
    reg [6:0]  ig = 7'd0;
    reg [4:0]  drain = 5'd0;
    reg [7:0]  mj = 8'd0;                  // argmax scan
    reg        mv = 1'b0;
    reg [7:0]  mjv = 8'd0;
    reg signed [31:0] best = 0;
    wire signed [31:0] score_rd;           // the score mj (from the lanes, below)
    wire last_layer = (L == layers - 1'b1);

    always @(posedge clk) begin
        iv <= 1'b0; mv <= 1'b0;
        if (state != S_IDLE) clk_count <= clk_count + 1'b1;
        if (!rstn) state <= S_IDLE;
        else case (state)
            S_IDLE: if (start) begin
                state <= S_SETUP; L <= 2'd0; src <= 1'b0; ready <= 1'b0; clk_count <= 32'd1;
            end
            S_SETUP: begin
                in4 <= c_in4[L]; og <= c_og[L]; bbase <= c_bbase[L]; shift <= c_shift[L]; act <= c_act[L];
                laddr <= c_wbase[L]; t <= 9'd0; g <= 7'd0;
                state <= S_RUN;
            end
            S_RUN: begin
                iv <= 1'b1; ifirst <= (t == 9'd0); ilast <= (t == in4 - 1'b1); ig <= g;
                laddr <= laddr + 1'b1;
                if (t == in4 - 1'b1) begin
                    t <= 9'd0;
                    if (g == og - 1'b1) begin state <= S_DRAIN; drain <= 5'd12; end
                    g <= g + 1'b1;
                end else t <= t + 1'b1;
            end
            S_DRAIN: if (drain != 5'd0) drain <= drain - 1'b1;
            else if (!last_layer) begin L <= L + 1'b1; src <= ~src; state <= S_SETUP; end
            else if (act == 2'd0) begin state <= S_MAX; mj <= 8'd0; end
            else state <= S_END;
            S_MAX: begin                     // the largest score (the first one when two are equal)
                mv <= 1'b1; mjv <= mj;
                if (mj == {og, 4'd0} - 1'b1 || mj == 8'd254) state <= S_END;
                mj <= mj + 1'b1;
            end
            S_END: if (!mv) begin
                state <= S_IDLE; ready <= 1'b1; cycles <= clk_count; count <= count + 1'b1;
            end
        endcase
        if (mv && (mjv == 8'd0 || score_rd > best)) begin best <= score_rd; result <= mjv; end
    end

    // ---- the input word (4 bytes) for all lanes: from the lanes' parts of the source buffer
    wire [8 * LANES - 1:0] rowA, rowB;     // byte l = lane l's byte at address t / 4 (input bytes 4t .. 4t + 3)
    reg  [31:0] xq = 32'd0;
    always @(posedge clk) begin           // read in the issue clock, like the weights
        case (t[1:0])
            2'd0: xq <= src ? rowB[31:0]   : rowA[31:0];
            2'd1: xq <= src ? rowB[63:32]  : rowA[63:32];
            2'd2: xq <= src ? rowB[95:64]  : rowA[95:64];
            default: xq <= src ? rowB[127:96] : rowA[127:96];
        endcase
    end

    // ---- the pipeline: issue (the RAMs and the input word answer, flag iv), 1 products, 2 sum, 3 accumulate
    //      (and the bias is read), 4 + bias, 5 shift, 6 act and write
    reg pv = 0, pf = 0, pl = 0, sv = 0, sf = 0, sl = 0, f1 = 0, f2 = 0, f3 = 0;
    reg [6:0] pg = 0, sg = 0, g1 = 0, g2 = 0, g3 = 0;
    always @(posedge clk) begin
        pv <= iv; pf <= ifirst; pl <= ilast; pg <= ig;
        sv <= pv; sf <= pf; sl <= pl; sg <= pg;
        f1 <= sv && sl; g1 <= sg;
        f2 <= f1; g2 <= g1;
        f3 <= f2; g3 <= g2;
    end

    // ---- bus access to the buffers and scores: word w of a buffer = bytes 4w .. 4w + 3 = lanes (4w % 16) .. + 3
    wire bufA_wr = wr && idx[9:8] == 2'b01, bufB_wr = wr && idx[9:8] == 2'b10;
    wire [5:0] bus_ba = idx[7:2];                      // address inside a lane's part (reading)
    wire [1:0] bus_quad = idx[1:0];                    // which 4 lanes
    // Writes from the bus are decoded into one enable per lane and registered: each RAM then gets a ready
    // signal (the decode across the chip and the RAM's write enable in one clock were too slow for 100 MHz).
    reg [15:0] we_w = 16'd0, we_b = 16'd0, we_ba = 16'd0, we_bb = 16'd0;
    reg [10:0] w_ofs = 11'd0;
    reg [6:0]  b_ofs = 7'd0;
    reg [5:0]  bba = 6'd0;
    reg [31:0] w_dat = 32'd0;
    integer q;
    always @(posedge clk) begin
        for (q = 0; q < 16; q = q + 1) begin
            we_w[q]  <= wr && idx == 10'd7 && !waddr[16] && waddr[14:11] == q;
            we_b[q]  <= wr && idx == 10'd7 && waddr[16] && waddr[10:7] == q;
            we_ba[q] <= bufA_wr && bus_quad == q / 4;
            we_bb[q] <= bufB_wr && bus_quad == q / 4;
        end
        w_ofs <= waddr[10:0]; b_ofs <= waddr[6:0]; bba <= bus_ba; w_dat <= wd;
    end
    wire [8 * LANES - 1:0] busA, busB;
    wire [32 * LANES - 1:0] busS, scoreFlat;

    genvar pp, u;
    generate for (pp = 0; pp < LANES / 2; pp = pp + 1) begin : pair
        wire [31:0] wq [0:1];
        reg signed [18:0] s0 = 0, s1 = 0;
        reg signed [33:0] P0 = 0, P1 = 0, P2 = 0, P3 = 0;
        // two weights side by side in one multiplier: (w_odd * 2^17 + w_even) * input; each product fits 17 bits
        wire signed [24:0] a0 = $signed({wq[1][7:0], 17'd0}) + $signed(wq[0][7:0]);
        wire signed [24:0] a1 = $signed({wq[1][15:8], 17'd0}) + $signed(wq[0][15:8]);
        wire signed [24:0] a2 = $signed({wq[1][23:16], 17'd0}) + $signed(wq[0][23:16]);
        wire signed [24:0] a3 = $signed({wq[1][31:24], 17'd0}) + $signed(wq[0][31:24]);
        always @(posedge clk) begin
            if (iv) begin
                P0 <= a0 * $signed({1'b0, xq[7:0]});
                P1 <= a1 * $signed({1'b0, xq[15:8]});
                P2 <= a2 * $signed({1'b0, xq[23:16]});
                P3 <= a3 * $signed({1'b0, xq[31:24]});
            end
            if (pv) begin
                s0 <= $signed(P0[16:0]) + $signed(P1[16:0]) + $signed(P2[16:0]) + $signed(P3[16:0]);
                s1 <= ($signed(P0[33:17]) + $signed({1'b0, P0[16]})) + ($signed(P1[33:17]) + $signed({1'b0, P1[16]}))
                    + ($signed(P2[33:17]) + $signed({1'b0, P2[16]})) + ($signed(P3[33:17]) + $signed({1'b0, P3[16]}));
            end
        end
        for (u = 0; u < 2; u = u + 1) begin : half
            localparam integer LN = 2 * pp + u;
            // weights (block RAM) and biases
            reg [31:0] wmem [0:2047];
            reg [31:0] wqr = 32'd0;
            reg signed [31:0] bmem [0:127];
            reg signed [31:0] bq = 0;
            always @(posedge clk) begin
                if (we_w[LN]) wmem[w_ofs] <= w_dat;
                if (we_b[LN]) bmem[b_ofs] <= w_dat;
                wqr <= wmem[laddr];
                if (sv) bq <= bmem[bbase + sg];
            end
            assign wq[u] = wqr;
            // this lane's part of the buffers (64 bytes each) and of the scores (16)
            reg [7:0] ba [0:63];
            reg [7:0] bb [0:63];
            reg signed [31:0] sc [0:15];
            assign rowA[8 * LN +: 8] = ba[t[7:2]];
            assign rowB[8 * LN +: 8] = bb[t[7:2]];
            assign busA[8 * LN +: 8] = ba[bus_ba];
            assign busB[8 * LN +: 8] = bb[bus_ba];
            assign busS[32 * LN +: 32] = sc[idx[7:4]];
            assign scoreFlat[32 * LN +: 32] = sc[mjv[7:4]];
            // accumulate, + bias, shift, act
            wire signed [18:0] s = u ? s1 : s0;
            reg signed [31:0] acc = 0, sum = 0, shv = 0;
            wire [7:0] relu = (shv < 0) ? 8'd0 : (shv > 255) ? 8'd255 : shv[7:0];
            wire [7:0] sidx = (shv < -128) ? 8'd0 : (shv > 127) ? 8'd255 : shv[7:0] + 8'd128;
            wire [7:0] sig;
            mlp_sigmoid u_sig (.i(sidx), .o(sig));
            wire [7:0] outb = (act == 2'd2) ? sig : relu;
            wire f3w = f3 && act != 2'd0;                              // the pipeline writes a result
            wire [7:0] bus_byte = w_dat[8 * (LN % 4) +: 8];
            wire weA = (f3w && src) || we_ba[LN];
            wire weB = (f3w && !src) || we_bb[LN];
            always @(posedge clk) begin
                if (sv) acc <= sf ? s : acc + s;
                if (f1) sum <= acc + bq;
                if (f2) shv <= sum >>> shift;
                if (f3 && act == 2'd0) sc[g3[3:0]] <= shv;
                if (weA) ba[f3w ? g3[5:0] : bba] <= f3w ? outb : bus_byte;        // one write port each
                if (weB) bb[f3w ? g3[5:0] : bba] <= f3w ? outb : bus_byte;
            end
        end
    end endgenerate
    assign score_rd = scoreFlat[32 * mjv[3:0] +: 32];

    // ---- reading
    always @(posedge clk) if (re_r) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx[9:8] == 2'b01) bus_rdata <= busA[32 * bus_quad +: 32];
        else if (idx[9:8] == 2'b10) bus_rdata <= busB[32 * bus_quad +: 32];
        else if (idx[9:8] == 2'b11 && idx != 10'd1023) bus_rdata <= busS[32 * idx[3:0] +: 32];
        else if (idx[9:5] == 5'b00000 && idx[4]) case (idx[2:0])
            3'd0: bus_rdata <= c_in4[{1'b0, idx[3]}];
            3'd1: bus_rdata <= c_og[{1'b0, idx[3]}];
            3'd2: bus_rdata <= c_wbase[{1'b0, idx[3]}];
            3'd3: bus_rdata <= c_bbase[{1'b0, idx[3]}];
            3'd4: bus_rdata <= c_shift[{1'b0, idx[3]}];
            3'd5: bus_rdata <= c_act[{1'b0, idx[3]}];
            default: bus_rdata <= 32'd0;
        endcase
        else case (idx)
            10'd1: bus_rdata <= {30'd0, ready, state != S_IDLE};
            10'd2: bus_rdata <= {24'd0, result};
            10'd3: bus_rdata <= cycles;
            10'd4: bus_rdata <= {29'd0, layers};
            10'd5: bus_rdata <= count;
            10'd6: bus_rdata <= {15'd0, waddr};
            10'd1023: bus_rdata <= ID;
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign busy_led = state != S_IDLE;
endmodule
