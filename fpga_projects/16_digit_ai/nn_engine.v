// 16 AI in the FPGA: a neural network that reads handwritten digits, computed by 64 multipliers at once.
//
//   the picture: 28 x 28 = 784 pixels, 0 .. 255
//   layer 1:     64 neurons   h[j] = limit( (sum_i W1[j][i] * x[i] + B1[j]) >> SHIFT , 0 .. 255 )   (ReLU)
//   layer 2:     10 neurons   score[k] = sum_j W2[k][j] * h[j] + B2[k]
//   the answer:  the digit k with the highest score
//
// Weights are signed 8 bit, sums 32 bit, exactly like nn_reference() in blocks.py (so the results can be
// compared bit for bit). 16 lanes work side by side; every lane has its own block RAM with the weights of
// 4 neurons and multiplies 4 pixels per clock: 64 multiplications per clock (two lanes share a DSP). Layer 1 takes 4 x 196 clocks,
// layer 2 10 x 16 clocks: about 1000 clocks = 10 microseconds for one digit at 100 MHz.
//
// Registers (word index, slot SLOT):
//   0  CTRL     write: [0] start (the picture must be written first)
//   1  STATUS   read : [0] busy  [1] a result is ready
//   2  RESULT   read : the digit 0 .. 9                  3  CYCLES  clocks the last digit took
//   4  SHIFT    0 .. 31                                  5  COUNT   digits recognised since power-on
//   6  WADDR    where the next WDATA goes (then +1):  lane * 1024 + row * 196 + i/4  for W1 (neuron = row * 16 + lane)
//               0x8000 + k * 16 + j/4  for W2.   Every word holds 4 weights, the lowest byte first.
//   7  WDATA    write: one word of weights
//  16 .. 25     SCORE[k] (signed)                   64 .. 79   the 64 hidden values, 4 per word (read)
// 128 .. 191    B1[j] (signed 32 bit)              192 .. 201  B2[k]
// 256 .. 451    the picture: 196 words, 4 pixels each, the lowest byte first
// 1023          ID "NNET"
`timescale 1ns / 1ps
module nn_engine #(parameter [3:0] SLOT = 4'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        busy_led
);
    localparam LANES = 16, ROWS = 4, WORDS = 196, CLASSES = 10;
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    wire wr = bus_we && sel;

    reg  [4:0]  shift = 5'd8;
    reg  [15:0] waddr = 16'd0;
    reg  [31:0] cycles = 32'd0, count = 32'd0, clk_count = 32'd0;
    reg  [3:0]  result = 4'd0;
    reg         ready = 1'b0;
    reg  signed [31:0] b1 [0:63];
    reg  signed [31:0] b2 [0:15];
    reg  signed [31:0] score [0:15];
    wire [511:0] hflat;                    // the 64 hidden values, h[j] = hflat[8j +: 8]
    integer n;
    initial for (n = 0; n < 64; n = n + 1) b1[n] = 32'sd0;
    initial for (n = 0; n < 16; n = n + 1) begin b2[n] = 32'sd0; score[n] = 32'sd0; end

    // ---- the picture (196 words) and the layer-2 weights (160 words): block RAM, written by the ARM
    reg [31:0] xmem [0:255];
    reg [31:0] w2mem [0:255];
    reg [7:0]  xa = 8'd0, w2a = 8'd0;
    reg [31:0] xq = 32'd0, w2q = 32'd0;
    always @(posedge clk) begin
        if (wr && idx[9:8] == 2'b01) xmem[idx[7:0]] <= bus_wdata;
        if (wr && idx == 10'd7 && waddr[15]) w2mem[waddr[7:0]] <= bus_wdata;
        xq <= xmem[xa];
        w2q <= w2mem[w2a];
    end

    // ---- registers
    wire start = wr && idx == 10'd0 && bus_wdata[0];
    always @(posedge clk) begin
        if (wr) begin
            if (idx == 10'd4) shift <= bus_wdata[4:0];
            if (idx == 10'd6) waddr <= bus_wdata[15:0];
            if (idx == 10'd7) waddr <= waddr + 1'b1;
            if (idx[9:6] == 4'b0010) b1[idx[5:0]] <= bus_wdata;           // 128 .. 191
            if (idx[9:4] == 6'b001100) b2[idx[3:0]] <= bus_wdata;         // 192 .. 207
        end
    end

    // ---- the state machine: layer 1 (rows 0..3, words 0..195), then layer 2 (classes 0..9, words 0..15)
    localparam S_IDLE = 2'd0, S_L1 = 2'd1, S_L2 = 2'd2, S_END = 2'd3;
    reg [1:0]  state = S_IDLE;
    reg [1:0]  row = 2'd0;
    reg [7:0]  t = 8'd0;
    reg [3:0]  k = 4'd0;
    reg [9:0]  laddr = 10'd0;              // the address in every lane's RAM
    reg        iv = 1'b0, ifirst = 1'b0, ilast = 1'b0;     // a read was issued this clock (layer 1)
    reg        jv = 1'b0, jfirst = 1'b0, jlast = 1'b0;     // the same for layer 2
    reg [1:0]  irow = 2'd0;
    reg [3:0]  jk = 4'd0, jj = 4'd0;
    reg [7:0]  drain = 8'd0;

    always @(posedge clk) begin
        iv <= 1'b0; jv <= 1'b0;
        if (state != S_IDLE) clk_count <= clk_count + 1'b1;
        if (!rstn) begin
            state <= S_IDLE;
        end else case (state)
            S_IDLE: if (start) begin
                state <= S_L1; row <= 2'd0; t <= 8'd0; ready <= 1'b0; clk_count <= 32'd1;
            end
            S_L1: begin
                laddr <= row * 10'd196 + t;
                xa <= t;
                iv <= 1'b1; ifirst <= (t == 8'd0); ilast <= (t == WORDS - 1); irow <= row;
                if (t == WORDS - 1) begin
                    t <= 8'd0;
                    if (row == ROWS - 1) begin state <= S_L2; k <= 4'd0; drain <= 8'd10; end
                    row <= row + 1'b1;
                end else t <= t + 1'b1;
            end
            S_L2: if (drain != 8'd0) drain <= drain - 1'b1;      // the last hidden values are being written
            else begin
                w2a <= {k, t[3:0]};
                jv <= 1'b1; jfirst <= (t[3:0] == 4'd0); jlast <= (t[3:0] == 4'd15); jk <= k; jj <= t[3:0];
                if (t[3:0] == 4'd15) begin
                    t <= 8'd0;
                    if (k == CLASSES - 1) begin state <= S_END; drain <= 8'd8; end
                    k <= k + 1'b1;
                end else t <= t + 1'b1;
            end
            S_END: if (drain != 8'd0) drain <= drain - 1'b1;
            else begin
                state <= S_IDLE; ready <= 1'b1; cycles <= clk_count; count <= count + 1'b1;
            end
        endcase
    end

    // ---- layer 1: 16 lanes, 4 multiplications each per clock
    // clock 1: the RAMs answer   clock 2: 4 products   clock 3: their sum   clock 4: accumulate   5 .. 7: the neuron
    reg dv = 1'b0, dfirst = 1'b0, dlast = 1'b0, pv = 1'b0, pfirst = 1'b0, plast = 1'b0, sv = 1'b0, sfirst = 1'b0, slast = 1'b0;
    reg f1 = 1'b0, f2 = 1'b0, f3 = 1'b0;
    reg [1:0] drow = 2'd0, prow = 2'd0, srow = 2'd0, frow1 = 2'd0, frow2 = 2'd0, frow3 = 2'd0;
    always @(posedge clk) begin
        dv <= iv; dfirst <= ifirst; dlast <= ilast; drow <= irow;
        pv <= dv; pfirst <= dfirst; plast <= dlast; prow <= drow;
        sv <= pv; sfirst <= pfirst; slast <= plast; srow <= prow;
        f1 <= sv && slast; frow1 <= srow;
        f2 <= f1; frow2 <= frow1;
        f3 <= f2; frow3 <= frow2;
    end

    // Two lanes share one DSP multiplier: they multiply the same pixel, so their two weights go in side by side,
    // a = w_odd * 2^17 + w_even (25 bits), and a * pixel = w_odd * pixel * 2^17 + w_even * pixel. Each product
    // fits in 17 bits (127 * 255 = 32385), so the low 17 bits are the even lane's product and the rest (plus
    // the low part's sign) the odd lane's. 64 multiplications per clock in 32 DSPs.
    genvar pp, u;
    generate for (pp = 0; pp < LANES / 2; pp = pp + 1) begin : pair
        wire [31:0] wq [0:1];
        reg signed [18:0] s0 = 0, s1 = 0;
        reg signed [33:0] P0 = 0, P1 = 0, P2 = 0, P3 = 0;
        wire signed [24:0] a0 = $signed({wq[1][7:0], 17'd0}) + $signed(wq[0][7:0]);
        wire signed [24:0] a1 = $signed({wq[1][15:8], 17'd0}) + $signed(wq[0][15:8]);
        wire signed [24:0] a2 = $signed({wq[1][23:16], 17'd0}) + $signed(wq[0][23:16]);
        wire signed [24:0] a3 = $signed({wq[1][31:24], 17'd0}) + $signed(wq[0][31:24]);
        always @(posedge clk) begin
            if (dv) begin
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
            localparam integer L = 2 * pp + u;           // the lane: neurons L, 16 + L, 32 + L, 48 + L
            reg [31:0] wmem [0:1023];
            reg [31:0] wqr = 32'd0;
            always @(posedge clk) begin
                if (wr && idx == 10'd7 && !waddr[15] && waddr[13:10] == L) wmem[waddr[9:0]] <= bus_wdata;
                wqr <= wmem[laddr];
            end
            assign wq[u] = wqr;
            wire signed [18:0] s = u ? s1 : s0;
            reg signed [31:0] acc = 0, sum = 0, shv = 0;
            reg [7:0] h0 = 8'd0, h1 = 8'd0, h2 = 8'd0, h3 = 8'd0;
            wire [7:0] hn = (shv < 0) ? 8'd0 : (shv > 255) ? 8'd255 : shv[7:0];   // ReLU and the 0..255 limit
            assign hflat[8 * L +: 8] = h0;
            assign hflat[8 * (16 + L) +: 8] = h1;
            assign hflat[8 * (32 + L) +: 8] = h2;
            assign hflat[8 * (48 + L) +: 8] = h3;
            always @(posedge clk) begin
                if (sv) acc <= sfirst ? s : acc + s;
                if (f1) sum <= acc + b1[frow1 * 16 + L];
                if (f2) shv <= sum >>> shift;               // divide by 2^SHIFT (a clock of its own: a wide shifter is slow)
                if (f3) case (frow3) 2'd0: h0 <= hn; 2'd1: h1 <= hn; 2'd2: h2 <= hn; default: h3 <= hn; endcase
            end
        end
    end endgenerate

    // ---- layer 2: 4 multiplications per clock, one class after the other
    reg ev = 1'b0, efirst = 1'b0, elast = 1'b0, qv = 1'b0, qfirst = 1'b0, qlast = 1'b0, rv = 1'b0, rfirst = 1'b0, rlast = 1'b0;
    reg [3:0] ek = 4'd0, qk = 4'd0, rk = 4'd0, ej = 4'd0;
    reg [31:0] hw = 32'd0;
    reg signed [16:0] q0 = 0, q1 = 0, q2 = 0, q3 = 0;
    reg signed [18:0] qs = 0;
    reg signed [31:0] acc2 = 0, best = 0;
    reg wv = 1'b0;
    reg [3:0] wk = 4'd0;
    reg signed [31:0] wsum = 0;
    always @(posedge clk) begin
        ev <= jv; efirst <= jfirst; elast <= jlast; ek <= jk; ej <= jj;
        hw <= hflat[32 * jj +: 32];
        qv <= ev; qfirst <= efirst; qlast <= elast; qk <= ek;
        if (ev) begin
            q0 <= $signed(w2q[7:0])   * $signed({1'b0, hw[7:0]});
            q1 <= $signed(w2q[15:8])  * $signed({1'b0, hw[15:8]});
            q2 <= $signed(w2q[23:16]) * $signed({1'b0, hw[23:16]});
            q3 <= $signed(w2q[31:24]) * $signed({1'b0, hw[31:24]});
        end
        rv <= qv; rfirst <= qfirst; rlast <= qlast; rk <= qk;
        if (qv) qs <= q0 + q1 + q2 + q3;
        if (rv) acc2 <= rfirst ? qs : acc2 + qs;
        wv <= rv && rlast; wk <= rk;
        if (wv) begin
            wsum = acc2 + b2[wk];
            score[wk] <= wsum;
            if (wk == 4'd0 || wsum > best) begin best <= wsum; result <= wk; end
        end
    end

    // ---- reading
    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx[9:4] == 6'd1) bus_rdata <= score[idx[3:0]];                                   // 16 .. 31
        else if (idx[9:4] == 6'd4) bus_rdata <= hflat[32 * idx[3:0] +: 32];                        // 64 .. 79
        else if (idx[9:6] == 4'b0010) bus_rdata <= b1[idx[5:0]];
        else if (idx[9:4] == 6'b001100) bus_rdata <= b2[idx[3:0]];
        else case (idx)
            10'd1: bus_rdata <= {30'd0, ready, state != S_IDLE};
            10'd2: bus_rdata <= {28'd0, result};
            10'd3: bus_rdata <= cycles;
            10'd4: bus_rdata <= {27'd0, shift};
            10'd5: bus_rdata <= count;
            10'd6: bus_rdata <= {16'd0, waddr};
            10'd1023: bus_rdata <= 32'h4E4E4554;          // "NNET"
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign busy_led = state != S_IDLE;
endmodule
