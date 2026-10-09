// mlp_ddr: the neural network engine of project 19 (AI Studio), with its weights in the board's DDR memory.
//
// The same math and the same 16 lanes as mlp_engine (two lanes per DSP), but the weights do not sit in block RAM:
// they stream from the DDR through the HP ports while the network runs (NP = 2: HP0 and HP2, the only setting that
// routes next to the engine; NP = 4 works in simulation). AI Studio runs it at 75 MHz (see its top.v).
// So a network can have millions of weights instead of 128 KB, and many networks can wait in the DDR at once.
//
// The stream: port p carries the weights of lanes 16 / NP * p .. (NP = 2: HP0 lanes 0..7, HP2 lanes 8..15). For every layer and every group of
// 16 neurons it holds one bias row (each lane's 32-bit bias) and then one row per 4 inputs (each lane's 4 weights);
// a row is 64 bytes in all. A network's layers follow each other, so the stream never stops.
// Port p's stream lies at byte REGION * p + OFS of the program's locked memory; the page table turns those
// bytes into the physical 4 KB pages Linux gave the program (the FPGA only reads them).
//
//   out[j] = act( (sum_i W[j][i] * in[i] + B[j]) >> SHIFT )     act 0: scores, 1: ReLU 0..255, 2: sigmoid table
//   exactly mlp_reference() in blocks.py.
//
// Registers (word index, slot SLOT):
//   0 CTRL   write 1: run          1 STATUS [0] busy [1] ready       2 RESULT (largest score)     3 CYCLES
//   4 LAYERS 1 .. 4                5 COUNT  runs since power-on      6 STALLS clocks spent waiting for the DDR
//   8 OFS    the network's first byte in every port's region (a multiple of 128)
//   9 LEN    its bytes per port (a multiple of 128)               10 REGION  bytes per port region (multiple of 4096)
//  11 PORTS  2 or 4 (how the streams are cut)
//  12 PTADDR, 13 PTDATA  the page table (physical page numbers, 4096 pages = 16 MB)
//  16 + 8L, 17 + 8L, 20 + 8L, 21 + 8L   layer L: IN4 (inputs / 4), OG (outputs / 16), SHIFT, ACT
// 256 .. 511 buffer A (the input), 512 .. 767 buffer B, 768 .. 1022 SCORES, 1023 ID
`timescale 1ns / 1ps
module mlp_ddr #(parameter [3:0] SLOT = 4'd1, parameter [31:0] ID = 32'h4D4C5032, parameter NP = 4) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        busy_led,
    // the DDR read ports of ardzy_bus_ddr (0 = ACP, not used here; 1..4 = HP0..HP3)
    output wire [5 * 32 - 1:0] dr_araddr, output wire [5 * 4 - 1:0] dr_arlen, output wire [4:0] dr_arvalid,
    input  wire [4:0] dr_arready, input wire [5 * 64 - 1:0] dr_rdata, input wire [4:0] dr_rvalid,
    input  wire [4:0] dr_rlast, input wire [9:0] dr_rresp, output wire [4:0] dr_rready
);
    localparam LANES = 16;
    // NP = 4: HP0..HP3, port p carries lanes 4p .. 4p + 3 (2 words of 8 bytes per row);
    // NP = 2: HP0 and HP2, port p carries lanes 8p .. 8p + 7 (4 words per row): half the wires at the PS edge
    localparam LPP = LANES / NP, BPR = LPP / 2;
    // (The paths to and from the PS's HP ports are long and their timing is not fully known to the tools: on the
    // chip 100 MHz gave wrong results, 75 MHz is right. AI Studio therefore runs at 75 MHz, see its top.v.)
    reg [15:0] a_r = 16'd0;
    reg [31:0] wd = 32'd0;
    reg        we_r = 1'b0, re_r = 1'b0;
    always @(posedge clk) begin a_r <= bus_addr; wd <= bus_wdata; we_r <= bus_we; re_r <= bus_re; end
    wire sel = (a_r[15:12] == SLOT);
    wire [9:0] idx = a_r[11:2];
    wire wr = we_r && sel;

    // ---- registers
    reg  [2:0]  layers = 3'd1;
    reg  [31:0] cycles = 32'd0, count = 32'd0, clk_count = 32'd0, stalls = 32'd0, errors = 32'd0;
    reg  [31:0] r_ofs = 32'd0, r_len = 32'd128, r_region = 32'd4096;
    reg  [12:0] ptw = 13'd0;
    reg  [7:0]  result = 8'd0;
    reg         ready = 1'b0;
    reg  [8:0]  c_in4 [0:3];
    reg  [6:0]  c_og [0:3];
    reg  [4:0]  c_shift [0:3];
    reg  [1:0]  c_act [0:3];
    reg  [19:0] pt [0:4095];
    integer n;
    initial for (n = 0; n < 4; n = n + 1) begin c_in4[n] = 9'd1; c_og[n] = 7'd1; c_shift[n] = 5'd0; c_act[n] = 2'd0; end
    wire start = wr && idx == 10'd0 && wd[0];
    always @(posedge clk) if (wr) begin
        if (idx == 10'd4) layers <= (wd[2:0] == 3'd0) ? 3'd1 : (wd[2:0] > 3'd4 ? 3'd4 : wd[2:0]);
        if (idx == 10'd8) r_ofs <= wd;
        if (idx == 10'd9) r_len <= wd;
        if (idx == 10'd10) r_region <= wd;
        if (idx == 10'd12) ptw <= wd[12:0];
        if (idx == 10'd13) begin pt[ptw[11:0]] <= wd[19:0]; ptw <= ptw + 1'b1; end
        if (idx >= 10'd16 && idx < 10'd48) case (idx[2:0])
            3'd0: c_in4[idx[4:3] - 2'd2] <= wd[8:0];
            3'd1: c_og[idx[4:3] - 2'd2] <= wd[6:0];
            3'd4: c_shift[idx[4:3] - 2'd2] <= wd[4:0];
            3'd5: c_act[idx[4:3] - 2'd2] <= wd[1:0];
            default: ;
        endcase
    end

    // ---- the four streamers: port p reads its stream in bursts of 128 bytes into its FIFO
    reg st_go = 1'b0;                      // a run starts: every streamer begins at the network's first byte
    wire [3:0] f_dv;                       // FIFO p has a word ready
    wire [255:0] f_do;                     // ... this word
    reg  [3:0] f_pop = 4'd0;
    wire [3:0] pt_req;
    wire [3:0] s_idle;                     // streamer p has no reads on their way
    wire [47:0] pt_page;                   // 12 bits per port
    reg  [3:0] pt_gnt = 4'd0;
    reg  [19:0] pt_q = 20'd0;
    // the page table is shared: one lookup per clock, the lowest waiting port first (one read port: block RAM)
    wire [3:0] pt_want = pt_req & ~pt_gnt;
    wire [3:0] pt_pick = pt_want[0] ? 4'b0001 : pt_want[1] ? 4'b0010 : pt_want[2] ? 4'b0100 : pt_want[3] ? 4'b1000 : 4'b0000;
    wire [11:0] pt_a = pt_want[0] ? pt_page[11:0] : pt_want[1] ? pt_page[23:12] : pt_want[2] ? pt_page[35:24] : pt_page[47:36];
    always @(posedge clk) begin
        pt_gnt <= pt_pick;
        pt_q <= pt[pt_a];
    end
    assign dr_araddr[31:0] = 32'd0; assign dr_arlen[3:0] = 4'd0; assign dr_arvalid[0] = 1'b0; assign dr_rready[0] = 1'b1;
    genvar p;
    generate for (p = NP; p < 4; p = p + 1) begin : unused
        assign pt_req[p] = 1'b0; assign pt_page[12 * p +: 12] = 12'd0; assign s_idle[p] = 1'b1;
        assign f_dv[p] = 1'b1; assign f_do[64 * p +: 64] = 64'd0;
    end endgenerate
    // the HP ports not used (NP = 2: HP1, HP3)
    generate if (NP == 2) begin : tie
        assign dr_araddr[64 +: 32] = 32'd0; assign dr_arlen[8 +: 4] = 4'd0; assign dr_arvalid[2] = 1'b0; assign dr_rready[2] = 1'b1;
        assign dr_araddr[128 +: 32] = 32'd0; assign dr_arlen[16 +: 4] = 4'd0; assign dr_arvalid[4] = 1'b0; assign dr_rready[4] = 1'b1;
    end endgenerate
    generate for (p = 0; p < NP; p = p + 1) begin : stream
        localparam integer D = (NP == 4) ? p + 1 : 2 * p + 1;     // which dr_ port: HP0 + ...
        reg [31:0] pos = 32'd0;            // bytes asked for
        reg        active = 1'b0;
        reg [11:0] cur = 12'hFFF;          // the page whose physical number is in pfn
        reg [19:0] pfn = 20'd0;
        reg        pfn_ok = 1'b0;
        reg [31:0] ar_a = 32'd0;
        reg        ar_v = 1'b0;
        reg [9:0]  infl = 10'd0;           // words asked for, not yet arrived
        assign s_idle[p] = infl == 10'd0 && !ar_v;
        // the next burst's byte in the program's memory (region * p without a multiplier: p is 0..3)
        wire [31:0] base = (p == 0) ? 32'd0 : (p == 1) ? r_region : (p == 2) ? {r_region[30:0], 1'b0} : r_region + {r_region[30:0], 1'b0};
        wire [31:0] v = base + r_ofs + pos;
        wire need = active && pos < r_len;
        wire [9:0] used;
        assign pt_req[p] = need && !(pfn_ok && v[23:12] == cur);     // held until the answer comes
        assign pt_page[12 * p +: 12] = v[23:12];
        wire got = pt_gnt[p];
        always @(posedge clk) begin
            if (got) begin pfn <= pt_q; cur <= v[23:12]; pfn_ok <= 1'b1; end
            if (ar_v && dr_arready[D]) ar_v <= 1'b0;
            infl <= infl + ((ar_v && dr_arready[D]) ? 10'd16 : 10'd0) - (dr_rvalid[D] ? 10'd1 : 10'd0);
            if (st_go) begin pos <= 32'd0; active <= 1'b1; pfn_ok <= 1'b0; end
            else if (need && pfn_ok && v[23:12] == cur && !ar_v && used + infl + 10'd16 <= 10'd512) begin
                ar_a <= {pfn, v[11:0]};
                ar_v <= 1'b1;
                pos <= pos + 32'd128;
            end
        end
        assign dr_araddr[32 * D +: 32] = ar_a;
        assign dr_arlen[4 * D +: 4] = 4'd15;
        assign dr_arvalid[D] = ar_v;
        assign dr_rready[D] = 1'b1;       // there is always room: only asked for what fits
        mlp_fifo u_f (.clk(clk), .clr(st_go), .din(dr_rdata[64 * D +: 64]), .wr(dr_rvalid[D]),
                      .dout(f_do[64 * p +: 64]), .dv(f_dv[p]), .pop(f_pop[p]), .used(used));
    end endgenerate
    always @(posedge clk) if (st_go) errors <= 32'd0;
        else if (|(dr_rvalid[4:1] & {dr_rresp[9] | dr_rresp[8], dr_rresp[7] | dr_rresp[6], dr_rresp[5] | dr_rresp[4], dr_rresp[3] | dr_rresp[2]}))
            errors <= errors + 1'b1;

    // ---- rows: BPR words from every FIFO = 64 bytes = one row (4 bytes per lane). Each FIFO's words go past its
    // lanes; a lane keeps its 4 bytes when they pass (word ph), and the row is complete with the last word. So
    // every lane collects its own weights next to itself: no 512-bit row in the middle of the chip.
    reg [1:0]  ph = 2'd0;                 // which word of the row comes now
    wire       run_pop;                   // the state machine wants rows (it is in S_RUN)
    wire all_dv = &f_dv;
    wire pop_now = all_dv && run_pop;
    wire take = pop_now && ph == BPR - 1; // a whole row this clock
    integer q;
    always @(*) f_pop = pop_now ? 4'b1111 : 4'b0000;
    always @(posedge clk) begin
        if (st_go) ph <= 2'd0;
        else if (pop_now) ph <= (ph == BPR - 1) ? 2'd0 : ph + 1'b1;
    end

    // ---- the state machine
    reg [1:0]  L = 2'd0;
    reg [8:0]  in4 = 9'd1;
    reg [6:0]  og = 7'd1;
    reg [4:0]  shift = 5'd0;
    reg [1:0]  act = 2'd0;
    reg        src = 1'b0;
    localparam S_IDLE = 3'd0, S_SETUP = 3'd1, S_RUN = 3'd2, S_DRAIN = 3'd3, S_MAX = 3'd4, S_END = 3'd5, S_FLUSH = 3'd6;
    reg [2:0]  state = S_IDLE;
    reg [8:0]  t = 9'd0;
    reg [6:0]  g = 7'd0;
    reg        needb = 1'b0;
    reg        iv = 1'b0, ifirst = 1'b0, ilast = 1'b0, btake = 1'b0;
    reg [6:0]  ig = 7'd0, bg = 7'd0;
    reg [4:0]  drain = 5'd0;
    reg [7:0]  mj = 8'd0, mjv = 8'd0;
    reg        mv = 1'b0;
    reg signed [31:0] best = 0;
    wire signed [31:0] score_rd;
    wire last_layer = (L == layers - 1'b1);
    assign run_pop = (state == S_RUN);

    always @(posedge clk) begin
        iv <= 1'b0; mv <= 1'b0; btake <= 1'b0; st_go <= 1'b0;
        if (state != S_IDLE) clk_count <= clk_count + 1'b1;
        if (!rstn) state <= S_IDLE;
        else case (state)
            S_IDLE: if (start) begin
                state <= S_FLUSH; L <= 2'd0; src <= 1'b0; ready <= 1'b0; clk_count <= 32'd1; stalls <= 32'd0;
            end
            // the last run's final burst may still be arriving (the padding after its last row): wait for it,
            // then clear the FIFOs and start every streamer at this network's first byte
            S_FLUSH: if (&s_idle) begin st_go <= 1'b1; state <= S_SETUP; end
            S_SETUP: begin
                in4 <= c_in4[L]; og <= c_og[L]; shift <= c_shift[L]; act <= c_act[L];
                t <= 9'd0; g <= 7'd0; needb <= 1'b1;
                state <= S_RUN;
            end
            S_RUN: if (take) begin
                if (needb) begin btake <= 1'b1; bg <= g; needb <= 1'b0; end
                else begin
                    iv <= 1'b1; ifirst <= (t == 9'd0); ilast <= (t == in4 - 1'b1); ig <= g;
                    if (t == in4 - 1'b1) begin
                        t <= 9'd0; needb <= 1'b1;
                        if (g == og - 1'b1) begin state <= S_DRAIN; drain <= 5'd12; end
                        g <= g + 1'b1;
                    end else t <= t + 1'b1;
                end
            end else if (!all_dv) stalls <= stalls + 1'b1;     // (a row needs 2 clocks; only real waiting counts)
            S_DRAIN: if (drain != 5'd0) drain <= drain - 1'b1;
            else if (!last_layer) begin L <= L + 1'b1; src <= ~src; state <= S_SETUP; end
            else if (act == 2'd0) begin state <= S_MAX; mj <= 8'd0; end
            else state <= S_END;
            S_MAX: begin
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

    // ---- the input word for all lanes (read in the issue clock, like the weights)
    wire [8 * LANES - 1:0] rowA, rowB;
    reg  [31:0] xq = 32'd0;
    always @(posedge clk) begin
        case (t[1:0])
            2'd0: xq <= src ? rowB[31:0]   : rowA[31:0];
            2'd1: xq <= src ? rowB[63:32]  : rowA[63:32];
            2'd2: xq <= src ? rowB[95:64]  : rowA[95:64];
            default: xq <= src ? rowB[127:96] : rowA[127:96];
        endcase
    end

    // ---- the pipeline flags (as in mlp_engine)
    reg pv = 0, pf = 0, pl = 0, sv = 0, sf = 0, sl = 0, f1 = 0, f2 = 0, f3 = 0;
    reg [6:0] pg = 0, sg = 0, g1 = 0, g2 = 0, g3 = 0;
    always @(posedge clk) begin
        pv <= iv; pf <= ifirst; pl <= ilast; pg <= ig;
        sv <= pv; sf <= pf; sl <= pl; sg <= pg;
        f1 <= sv && sl; g1 <= sg;
        f2 <= f1; g2 <= g1;
        f3 <= f2; g3 <= g2;
    end

    // ---- bus access to the buffers and scores (as in mlp_engine)
    wire bufA_wr = wr && idx[9:8] == 2'b01, bufB_wr = wr && idx[9:8] == 2'b10;
    wire [5:0] bus_ba = idx[7:2];
    wire [1:0] bus_quad = idx[1:0];
    reg [15:0] we_ba = 16'd0, we_bb = 16'd0;
    reg [5:0]  bba = 6'd0;
    reg [31:0] w_dat = 32'd0;
    always @(posedge clk) begin
        for (q = 0; q < 16; q = q + 1) begin
            we_ba[q] <= bufA_wr && bus_quad == q / 4;
            we_bb[q] <= bufB_wr && bus_quad == q / 4;
        end
        bba <= bus_ba; w_dat <= wd;
    end
    wire [8 * LANES - 1:0] busA, busB;
    wire [32 * LANES - 1:0] busS, scoreFlat;

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
            // this lane's 4 weights: word WK of its port's FIFO, the low or high half (LH); words before the
            // last wait in stg. Its bias comes the same way, from a bias row.
            localparam integer PQ = LN / LPP, WK = (LN % LPP) / 2, LH = LN % 2;
            wire [31:0] mine = f_do[64 * PQ + 32 * LH +: 32];
            reg [31:0] stg = 32'd0;
            wire [31:0] word = (WK == BPR - 1) ? mine : stg;
            reg [31:0] wqr = 32'd0;
            reg signed [31:0] bs [0:3];   // four groups' biases (a fast stream can bring the next ones early)
            always @(posedge clk) begin
                if (pop_now && ph == WK) stg <= mine;
                if (take) wqr <= word;
                if (take && needb && state == S_RUN) bs[g[1:0]] <= word;
            end
            assign wq[u] = wqr;
            reg [7:0] ba [0:63];
            reg [7:0] bb [0:63];
            reg signed [31:0] sc [0:15];
            assign rowA[8 * LN +: 8] = ba[t[7:2]];
            assign rowB[8 * LN +: 8] = bb[t[7:2]];
            assign busA[8 * LN +: 8] = ba[bus_ba];
            assign busB[8 * LN +: 8] = bb[bus_ba];
            assign busS[32 * LN +: 32] = sc[idx[7:4]];
            assign scoreFlat[32 * LN +: 32] = sc[mjv[7:4]];
            wire signed [18:0] s = u ? s1 : s0;
            reg signed [31:0] acc = 0, sum = 0, shv = 0;
            wire [7:0] relu = (shv < 0) ? 8'd0 : (shv > 255) ? 8'd255 : shv[7:0];
            wire [7:0] sidx = (shv < -128) ? 8'd0 : (shv > 127) ? 8'd255 : shv[7:0] + 8'd128;
            wire [7:0] sig;
            mlp_sigmoid u_sig (.i(sidx), .o(sig));
            wire [7:0] outb = (act == 2'd2) ? sig : relu;
            wire f3w = f3 && act != 2'd0;
            wire [7:0] bus_byte = w_dat[8 * (LN % 4) +: 8];
            wire weA = (f3w && src) || we_ba[LN];
            wire weB = (f3w && !src) || we_bb[LN];
            always @(posedge clk) begin
                if (sv) acc <= sf ? s : acc + s;
                if (f1) sum <= acc + bs[g1[1:0]];
                if (f2) shv <= sum >>> shift;
                if (f3 && act == 2'd0) sc[g3[3:0]] <= shv;
                if (weA) ba[f3w ? g3[5:0] : bba] <= f3w ? outb : bus_byte;
                if (weB) bb[f3w ? g3[5:0] : bba] <= f3w ? outb : bus_byte;
            end
        end
    end endgenerate
    assign score_rd = scoreFlat[32 * mjv[3:0] +: 32];

    always @(posedge clk) if (re_r) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx[9:8] == 2'b01) bus_rdata <= busA[32 * bus_quad +: 32];
        else if (idx[9:8] == 2'b10) bus_rdata <= busB[32 * bus_quad +: 32];
        else if (idx[9:8] == 2'b11 && idx != 10'd1023) bus_rdata <= busS[32 * idx[3:0] +: 32];
        else case (idx)
            10'd1: bus_rdata <= {30'd0, ready, state != S_IDLE};
            10'd2: bus_rdata <= {24'd0, result};
            10'd3: bus_rdata <= cycles;
            10'd4: bus_rdata <= {29'd0, layers};
            10'd5: bus_rdata <= count;
            10'd6: bus_rdata <= stalls;
            10'd7: bus_rdata <= errors;
            10'd8: bus_rdata <= r_ofs;
            10'd9: bus_rdata <= r_len;
            10'd10: bus_rdata <= r_region;
            10'd11: bus_rdata <= NP;
            10'd1023: bus_rdata <= ID;
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign busy_led = state != S_IDLE;
endmodule

// A first-word-fall-through FIFO of 512 x 64 bits (block RAM): dout is valid when dv; pop takes it.
module mlp_fifo (input wire clk, input wire clr, input wire [63:0] din, input wire wr, output reg [63:0] dout = 64'd0,
                 output reg dv = 1'b0, input wire pop, output wire [9:0] used);
    reg [63:0] mem [0:511];
    reg [8:0] wp = 9'd0, rp = 9'd0;
    reg [9:0] n = 10'd0;                     // words in mem (not counting dout)
    wire rd = n != 10'd0 && (!dv || pop);
    always @(posedge clk) begin
        if (clr) begin wp <= 9'd0; rp <= 9'd0; n <= 10'd0; dv <= 1'b0; end
        else begin
            if (wr) begin mem[wp] <= din; wp <= wp + 1'b1; end
            if (rd) begin dout <= mem[rp]; rp <= rp + 1'b1; end
            dv <= rd ? 1'b1 : (pop ? 1'b0 : dv);
            n <= n + (wr ? 10'd1 : 10'd0) - (rd ? 10'd1 : 10'd0);
        end
    end
    assign used = n + dv;
endmodule
