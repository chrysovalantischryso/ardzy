// 13 SHA-256 miner: the job the Antminer S9 was built for, in miniature, inside the FPGA.
//
//   sha256_core   one SHA-256 compression (512-bit block, 64 rounds), a round in 2 clocks (129 clocks)
//   sha_unit      double SHA-256 of an 80-byte header for one nonce (two compressions, the first from the midstate)
//   sha_miner     on the Ardzy register bus: a raw core (hash any message) and NU units that try NU nonces at once
//
// Why a round takes 2 clocks: one round adds 5 numbers of 32 bits plus the K constant; done in one clock it
// needs about 13 ns, more than the 10 ns of the 100 MHz clock. Split in two halves it fits easily. Four units
// side by side then try 4 nonces at the same time: that is how mining hardware gets fast (the S9 has 189
// chips with many such units each).
//
// Registers (word index, slot SLOT):
//   0  CTRL        write: [0] start raw   [1] start mining   [2] stop mining
//   1  STATUS      read : [0] raw busy    [1] mining          [2] found   [3] mining finished
//   2  NONCE_START (w)     3  NONCE_COUNT (w, 0 = all 2^32)     4  ZERO_BITS (w, 1 .. 32)
//   5  FOUND_NONCE (r)     6  HASHES (r) nonces tried          7  CYCLES (r) clocks spent mining
//   8 .. 15   MIDSTATE (w) the hash state after the header's first 64 bytes (the ARM computes it)
//  16 .. 18   TAIL (w)     header bytes 64 .. 75 as big-endian words (end of the merkle root, time, bits)
//  24 .. 31   H_IN (w)     raw mode: the hash state before the block
//  32 .. 47   BLOCK (w)    raw mode: the 16 words of the block
//  48 .. 55   H_OUT (r)    raw mode: the state after the block
//  56 .. 63   FOUND_HASH (r) the double hash of the nonce found (big-endian words, as hashlib.digest())
// 126  UNITS (r) how many units work side by side
// 127  ID "SHA2"
`timescale 1ns / 1ps

module sha256_core (
    input  wire         clk,
    input  wire         start,          // one clock: take h_in and blk
    input  wire [255:0] h_in,           // {H0, H1, ..., H7}  (H0 in the top bits)
    input  wire [511:0] blk,            // {W0, W1, ..., W15} (W0 in the top bits)
    output reg          busy = 1'b0,
    output reg          done = 1'b0,    // one clock when h_out is ready
    output reg  [255:0] h_out = 256'd0
);
    function [31:0] kc(input [5:0] t);
        case (t)
            6'd0: kc = 32'h428a2f98;
            6'd1: kc = 32'h71374491;
            6'd2: kc = 32'hb5c0fbcf;
            6'd3: kc = 32'he9b5dba5;
            6'd4: kc = 32'h3956c25b;
            6'd5: kc = 32'h59f111f1;
            6'd6: kc = 32'h923f82a4;
            6'd7: kc = 32'hab1c5ed5;
            6'd8: kc = 32'hd807aa98;
            6'd9: kc = 32'h12835b01;
            6'd10: kc = 32'h243185be;
            6'd11: kc = 32'h550c7dc3;
            6'd12: kc = 32'h72be5d74;
            6'd13: kc = 32'h80deb1fe;
            6'd14: kc = 32'h9bdc06a7;
            6'd15: kc = 32'hc19bf174;
            6'd16: kc = 32'he49b69c1;
            6'd17: kc = 32'hefbe4786;
            6'd18: kc = 32'h0fc19dc6;
            6'd19: kc = 32'h240ca1cc;
            6'd20: kc = 32'h2de92c6f;
            6'd21: kc = 32'h4a7484aa;
            6'd22: kc = 32'h5cb0a9dc;
            6'd23: kc = 32'h76f988da;
            6'd24: kc = 32'h983e5152;
            6'd25: kc = 32'ha831c66d;
            6'd26: kc = 32'hb00327c8;
            6'd27: kc = 32'hbf597fc7;
            6'd28: kc = 32'hc6e00bf3;
            6'd29: kc = 32'hd5a79147;
            6'd30: kc = 32'h06ca6351;
            6'd31: kc = 32'h14292967;
            6'd32: kc = 32'h27b70a85;
            6'd33: kc = 32'h2e1b2138;
            6'd34: kc = 32'h4d2c6dfc;
            6'd35: kc = 32'h53380d13;
            6'd36: kc = 32'h650a7354;
            6'd37: kc = 32'h766a0abb;
            6'd38: kc = 32'h81c2c92e;
            6'd39: kc = 32'h92722c85;
            6'd40: kc = 32'ha2bfe8a1;
            6'd41: kc = 32'ha81a664b;
            6'd42: kc = 32'hc24b8b70;
            6'd43: kc = 32'hc76c51a3;
            6'd44: kc = 32'hd192e819;
            6'd45: kc = 32'hd6990624;
            6'd46: kc = 32'hf40e3585;
            6'd47: kc = 32'h106aa070;
            6'd48: kc = 32'h19a4c116;
            6'd49: kc = 32'h1e376c08;
            6'd50: kc = 32'h2748774c;
            6'd51: kc = 32'h34b0bcb5;
            6'd52: kc = 32'h391c0cb3;
            6'd53: kc = 32'h4ed8aa4a;
            6'd54: kc = 32'h5b9cca4f;
            6'd55: kc = 32'h682e6ff3;
            6'd56: kc = 32'h748f82ee;
            6'd57: kc = 32'h78a5636f;
            6'd58: kc = 32'h84c87814;
            6'd59: kc = 32'h8cc70208;
            6'd60: kc = 32'h90befffa;
            6'd61: kc = 32'ha4506ceb;
            6'd62: kc = 32'hbef9a3f7;
            6'd63: kc = 32'hc67178f2;
        endcase
    endfunction
    function [31:0] rotr(input [31:0] x, input [4:0] n); rotr = (x >> n) | (x << (6'd32 - n)); endfunction

    reg [31:0] a, b, c, d, e, f, g, h;
    reg [31:0] hkw;                     // h + K[t] + W[t] for the round being done
    reg [31:0] kw;                      // K[t + 1] + W[t + 1], made in the first half
    reg [31:0] kn;                      // K[t + 1], looked up a round ahead (the table and the adder each get a clock)
    reg [31:0] t1r, t2r, wnr;           // the first half's results
    reg [31:0] w [0:15];                // W[t] .. W[t + 15]
    reg [5:0]  t = 6'd0;
    reg        half = 1'b0;             // 0: first half of a round, 1: second half
    reg [255:0] h0 = 256'd0;
    integer i;

    // first half: T1 = (h + K[t] + W[t]) + S1(e) + Ch(e, f, g)     T2 = S0(a) + Maj(a, b, c)
    //             and W[t + 16] = s1(W[t + 14]) + W[t + 9] + s0(W[t + 1]) + W[t]
    wire [31:0] s1  = rotr(e, 5'd6) ^ rotr(e, 5'd11) ^ rotr(e, 5'd25);
    wire [31:0] ch  = (e & f) ^ (~e & g);
    wire [31:0] s0  = rotr(a, 5'd2) ^ rotr(a, 5'd13) ^ rotr(a, 5'd22);
    wire [31:0] maj = (a & b) ^ (a & c) ^ (b & c);
    wire [31:0] ws0 = rotr(w[1], 5'd7) ^ rotr(w[1], 5'd18) ^ (w[1] >> 3);
    wire [31:0] ws1 = rotr(w[14], 5'd17) ^ rotr(w[14], 5'd19) ^ (w[14] >> 10);

    always @(posedge clk) begin
        done <= 1'b0;
        if (start && !busy) begin
            busy <= 1'b1;
            t <= 6'd0;
            half <= 1'b0;
            h0 <= h_in;
            {a, b, c, d, e, f, g, h} <= h_in;
            for (i = 0; i < 16; i = i + 1) w[i] <= blk[511 - 32 * i -: 32];
            hkw <= h_in[31:0] + kc(6'd0) + blk[511:480];
            kn <= kc(6'd1);
        end else if (busy && !half) begin
            t1r <= hkw + s1 + ch;
            t2r <= s0 + maj;
            wnr <= ws1 + w[9] + ws0 + w[0];
            kw  <= kn + w[1];
            half <= 1'b1;
        end else if (busy) begin
            // second half: the new working variables
            h <= g; g <= f; f <= e; e <= d + t1r;
            d <= c; c <= b; b <= a; a <= t1r + t2r;
            for (i = 0; i < 15; i = i + 1) w[i] <= w[i + 1];
            w[15] <= wnr;
            hkw <= g + kw;                // the next round's h is today's g
            kn <= kc(t + 6'd2);           // K for the round after next
            half <= 1'b0;
            t <= t + 6'd1;
            if (t == 6'd63) begin
                busy <= 1'b0;
                done <= 1'b1;
                h_out <= {h0[255:224] + t1r + t2r, h0[223:192] + a, h0[191:160] + b, h0[159:128] + c,
                          h0[127:96] + d + t1r, h0[95:64] + e, h0[63:32] + f, h0[31:0] + g};
            end
        end
    end
endmodule

// The double hash of one header with one nonce: SHA-256(SHA-256(header)), the first 64 bytes as a midstate.
module sha_unit (
    input  wire         clk,
    input  wire         go,
    input  wire [255:0] mid,
    input  wire [95:0]  tail,
    input  wire [31:0]  nonce,
    output reg          done = 1'b0,
    output reg  [255:0] hash = 256'd0
);
    localparam [255:0] IV = 256'h6a09e667_bb67ae85_3c6ef372_a54ff53a_510e527f_9b05688c_1f83d9ab_5be0cd19;
    reg          c_start = 1'b0;
    reg  [255:0] c_h = 256'd0;
    reg  [511:0] c_blk = 512'd0;
    wire         c_busy, c_done;
    wire [255:0] c_out;
    sha256_core u_core (.clk(clk), .start(c_start), .h_in(c_h), .blk(c_blk), .busy(c_busy), .done(c_done), .h_out(c_out));
    wire [31:0] nonce_le = {nonce[7:0], nonce[15:8], nonce[23:16], nonce[31:24]};   // the header stores it little-endian
    reg [1:0] st = 2'd0;
    always @(posedge clk) begin
        c_start <= 1'b0;
        done <= 1'b0;
        case (st)
            2'd0: if (go) begin                      // second block of the header: 16 bytes + padding (640 bits)
                c_h <= mid;
                c_blk <= {tail, nonce_le, 32'h80000000, 320'd0, 32'h00000280};
                c_start <= 1'b1;
                st <= 2'd1;
            end
            2'd1: if (c_done) begin                  // the first hash, hashed again (256 bits + padding)
                c_h <= IV;
                c_blk <= {c_out, 32'h80000000, 192'd0, 32'h00000100};
                c_start <= 1'b1;
                st <= 2'd2;
            end
            2'd2: if (c_done) begin hash <= c_out; done <= 1'b1; st <= 2'd0; end
            default: st <= 2'd0;
        endcase
    end
endmodule

module sha_miner #(parameter [3:0] SLOT = 4'd1, parameter NU = 4) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        mining_led,
    output wire        found_led
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    // bus writes are registered once before they are decoded: the address decode then drives the
    // register enables all over the chip from a flip-flop (directly from the bus it missed 100 MHz)
    reg        w_we = 1'b0;
    reg [9:0]  w_idx = 10'd0;
    reg [31:0] w_data = 32'd0;
    always @(posedge clk) begin w_we <= bus_we && sel; w_idx <= idx; w_data <= bus_wdata; end

    reg [31:0] mid [0:7];
    reg [31:0] tail [0:2];
    reg [31:0] hin [0:7];
    reg [31:0] blkr [0:15];
    reg [31:0] nonce_start = 32'd0, nonce_count = 32'd0, base = 32'd0, left = 32'd0;
    reg [5:0]  zbits = 6'd16;
    reg [31:0] found_nonce = 32'd0, hashes = 32'd0, cycles = 32'd0;
    reg [255:0] found_hash = 256'd0;
    reg mining = 1'b0, found = 1'b0, finished = 1'b0, all = 1'b0, stop_req = 1'b0;
    integer i;

    // ---- raw mode: its own core
    reg r_start = 1'b0;
    wire r_busy, r_done;
    wire [255:0] r_out;
    sha256_core u_raw (.clk(clk), .start(r_start),
        .h_in({hin[0], hin[1], hin[2], hin[3], hin[4], hin[5], hin[6], hin[7]}),
        .blk({blkr[0], blkr[1], blkr[2], blkr[3], blkr[4], blkr[5], blkr[6], blkr[7],
              blkr[8], blkr[9], blkr[10], blkr[11], blkr[12], blkr[13], blkr[14], blkr[15]}),
        .busy(r_busy), .done(r_done), .h_out(r_out));
    reg [255:0] raw_out = 256'd0;
    reg raw_busy = 1'b0;

    // ---- the units: unit k tries nonce base + k
    reg  go = 1'b0;
    reg  [NU-1:0] valid = {NU{1'b0}};
    wire [NU-1:0] u_done;
    wire [256*NU-1:0] u_hash;
    wire [255:0] midv = {mid[0], mid[1], mid[2], mid[3], mid[4], mid[5], mid[6], mid[7]};
    wire [95:0]  tailv = {tail[0], tail[1], tail[2]};
    genvar k;
    generate for (k = 0; k < NU; k = k + 1) begin : unit
        wire [31:0] nk = base + k;
        sha_unit u (.clk(clk), .go(go & valid[k]), .mid(midv), .tail(tailv), .nonce(nk),
                    .done(u_done[k]), .hash(u_hash[256 * k +: 256]));
    end endgenerate

    // Bitcoin compares the hash as a little-endian number: its leading zeros are the LAST bytes of the digest.
    // The digest's last word H7 = d28 d29 d30 d31; the hash as shown starts with d31, d30, ...
    reg  [31:0] zmask = 32'hFFFF0000;               // registered: it only changes when ZERO_BITS is written
    always @(posedge clk) zmask <= (zbits >= 6'd32) ? 32'hFFFFFFFF : ~(32'hFFFFFFFF >> zbits);
    reg  [NU-1:0] good;
    always @(*) for (i = 0; i < NU; i = i + 1)
        good[i] = valid[i] && (({u_hash[256 * i + 7 -: 8], u_hash[256 * i + 15 -: 8], u_hash[256 * i + 23 -: 8],
                                 u_hash[256 * i + 31 -: 8]} & zmask) == 32'd0);
    // the lowest unit with a good hash (the first nonce in order)
    reg [7:0] first;
    always @(*) begin
        first = 8'd255;
        for (i = NU - 1; i >= 0; i = i - 1) if (good[i]) first = i;
    end
    // how many units are busy in this batch
    reg [7:0] nvalid;
    always @(*) begin
        nvalid = 8'd0;
        for (i = 0; i < NU; i = i + 1) nvalid = nvalid + valid[i];
    end

    // the check after a batch takes 3 clocks (EVAL, SEL, CHECK): done in one clock its path was too long
    localparam M_IDLE = 3'd0, M_BATCH = 3'd1, M_WAIT = 3'd2, M_EVAL = 3'd3, M_SEL = 3'd4, M_CHECK = 3'd5;
    reg [2:0] mst = M_IDLE;
    reg [7:0] first_r = 8'd255, nvalid_r = 8'd0;
    reg [255:0] hash_r = 256'd0;
    reg [31:0] nonce_r = 32'd0;

    always @(posedge clk) begin
        r_start <= 1'b0;
        go <= 1'b0;
        if (w_we) begin
            if (w_idx >= 10'd8 && w_idx <= 10'd15) mid[w_idx[2:0]] <= w_data;
            if (w_idx >= 10'd16 && w_idx <= 10'd18) tail[w_idx - 10'd16] <= w_data;
            if (w_idx >= 10'd24 && w_idx <= 10'd31) hin[w_idx[2:0]] <= w_data;
            if (w_idx >= 10'd32 && w_idx <= 10'd47) blkr[w_idx[3:0]] <= w_data;
            if (w_idx == 10'd2) nonce_start <= w_data;
            if (w_idx == 10'd3) nonce_count <= w_data;
            if (w_idx == 10'd4) zbits <= (w_data[5:0] == 6'd0) ? 6'd1 : (w_data[5:0] > 6'd32 ? 6'd32 : w_data[5:0]);
            if (w_idx == 10'd0 && w_data[0] && !raw_busy) begin r_start <= 1'b1; raw_busy <= 1'b1; end
            if (w_idx == 10'd0 && w_data[2] && mining) stop_req <= 1'b1;
        end
        if (r_done) begin raw_out <= r_out; raw_busy <= 1'b0; end
        if (mining) cycles <= cycles + 1'b1;
        case (mst)
            M_IDLE: if (w_we && w_idx == 10'd0 && w_data[1]) begin
                base <= nonce_start;
                left <= nonce_count;
                all <= (nonce_count == 32'd0);
                hashes <= 32'd0; cycles <= 32'd0;
                found <= 1'b0; finished <= 1'b0; mining <= 1'b1; stop_req <= 1'b0;
                mst <= M_BATCH;
            end
            M_BATCH: begin
                for (i = 0; i < NU; i = i + 1) valid[i] <= all || (left > i);
                go <= 1'b1;
                mst <= M_WAIT;
            end
            M_WAIT: if (u_done[0]) mst <= M_EVAL;      // (all units take the same time)
            M_EVAL: begin first_r <= first; nvalid_r <= nvalid; mst <= M_SEL; end
            M_SEL: begin
                hash_r <= u_hash[256 * ((first_r >= NU) ? 0 : first_r) +: 256];
                nonce_r <= base + first_r;
                mst <= M_CHECK;
            end
            M_CHECK: begin
                if (first_r != 8'd255) begin
                    hashes <= hashes + first_r + 1'b1;
                    found <= 1'b1; finished <= 1'b1; mining <= 1'b0;
                    found_nonce <= nonce_r;
                    found_hash <= hash_r;
                    mst <= M_IDLE;
                end else begin
                    hashes <= hashes + nvalid_r;
                    if (stop_req || (!all && left <= NU)) begin
                        finished <= 1'b1; mining <= 1'b0; stop_req <= 1'b0;
                        mst <= M_IDLE;
                    end else begin
                        base <= base + NU;
                        left <= left - NU;
                        mst <= M_BATCH;
                    end
                end
            end
        endcase
        if (!rstn) begin mst <= M_IDLE; mining <= 1'b0; raw_busy <= 1'b0; end
    end

    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx >= 10'd48 && idx <= 10'd55) bus_rdata <= raw_out[255 - 32 * idx[2:0] -: 32];
        else if (idx >= 10'd56 && idx <= 10'd63) bus_rdata <= found_hash[255 - 32 * idx[2:0] -: 32];
        else case (idx)
            10'd1: bus_rdata <= {28'd0, finished, found, mining, raw_busy};
            10'd2: bus_rdata <= nonce_start;
            10'd3: bus_rdata <= nonce_count;
            10'd4: bus_rdata <= {26'd0, zbits};
            10'd5: bus_rdata <= found_nonce;
            10'd6: bus_rdata <= hashes;
            10'd7: bus_rdata <= cycles;
            10'd126: bus_rdata <= NU;
            10'd127: bus_rdata <= 32'h53484132;          // "SHA2"
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign mining_led = mining;
    assign found_led = found;
endmodule
