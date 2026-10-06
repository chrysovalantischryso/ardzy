// Ardzy FPGA library: ardzy_radio, a radio transmitter on one pin. FM stereo with RDS, AM, a plain carrier,
// and a symbol player for CW, FSK (RTTY), PSK and tone beacons.
//
// RF: a 32-bit carrier synthesizer at 250 MHz with two samples per clock (an ODDR), so 500 million samples
// per second, steps of 0.116 Hz, carriers up to about 200 MHz. The pin is high while the carrier phase is
// below WIDTH (512 = half the period = the strongest fundamental). AM and the power level change WIDTH.
// The output is a square wave, so it also sends harmonics. Keep the antenna short, use a filter for
// anything more than a bench test, and follow the radio rules of your country.
//
// FM stereo multiplex (MPX) at 390625 samples per second (100 MHz / 256):
//   audio (FIFO at any rate, resampled to 48828.125 Hz, or two test tones) -> volume -> pre-emphasis ->
//   clip -> 15 kHz low-pass (63 taps) -> M = (L+R)/2, S = (L-R)/2 -> x8 interpolation (96 taps) ->
//   MPX = A*M + A*S*sin(2p) + P*sin(p) + R*rds*sin(3p)    (p = the 19 kHz pilot phase, all locked)
//   RDS: 1187.5 bit/s (pilot / 16). The ARM writes the blocks (16 bits + 10 check bits) in two banks;
//   the block sends them in turn with differential coding, each bit as one sine period (biphase).
// Slots: SLOT registers, SLOT+1 RDS blocks (2 banks of 256 x 26 bit: word n = bank 0, 256 + n = bank 1),
//        SLOT+2 .. SLOT+5 MPX capture (4096 signed samples).
// Registers (word index):
//   0 CTRL      [0] transmit  [1] stereo  [2] RDS  [3] pilot  [5:4] pre-emphasis 0 off, 1 50 us, 2 75 us
//               [6] mute  [7] audio from the two test tones (else from the FIFO)
//               [8] narrow: the sound through the 300 .. 2700 Hz voice filter, mono (NFM, AM)
//   1 MODE      0 off, 1 carrier (key in 14), 2 FM, 3 AM, 4 symbols, 5 USB, 6 LSB, 7 DSB
//               SSB / DSB: a 256-tap complex band-pass (300 .. 2700 Hz) makes I and Q from the sound;
//               a CORDIC turns them into the carrier's strength (pulse width) and phase, 390625 times a second
//   2 FREQ      carrier = FREQ * 500 MHz / 2^32
//   3 DEV       FM deviation: offset = MPX * DEV / 2^16 (in FREQ units); 1288530 = 75 kHz at full MPX
//   4 G_AUDIO   audio in the MPX, Q15 (28508 = 87 %)   5 G_PILOT (2949 = 9 %)   6 G_RDS (1311 = 4 %)
//   7 VOLUME    audio input gain, 256 = 1.0 (up to 1023)
//   8 RATIO     input sample rate / 48828.125, Q16.16 (65536 = 48828 Hz, 59190 = 44100 Hz), 0.0625 .. 4
//   9 AUDIO     write: one stereo sample, right << 16 | left (8192 places)
//  10 AUDIO_LEVEL read: samples waiting; write: empty the FIFO
//  11 TONE_L    left test tone = TONE_L * 48828.125 / 2^32 Hz    12 TONE_R   (writing restarts the tone at 0)
//  13 AM_DEPTH  Q15 (29491 = 90 %)
//  14 LEVEL     [9:0] width for carrier and FM (512 = full power, less = weaker), [16] key (mode 1)
//  15 RDS_N     [8:0] blocks in a bank (4 .. 256, groups are 4 blocks), [16] bank to send (it changes
//               at the end of the list); read [17] the bank on air now
//  16 SYM_LO    symbol: [23:0] frequency offset (signed, FREQ units)  [31:24] phase (256 = a full turn)
//  17 SYM_HI    symbol: [9:0] width (0 = silent, 512 = full)  [29:10] time in us; writing queues it (512)
//  18 SYM_LEVEL read: symbols waiting; write: empty the queue (and stop the symbol on air)
//  19 CAPTURE write 1: record 4096 MPX samples, 3: record 2048 I / Q pairs (SSB); read [0] still recording
//  20 RDS_LOG   read: the next 32 sent RDS data bits (first sent in bit 31; 64 words kept)
//  21 RDS_LOG_LEVEL (read)   write: empty the log
//  22 PEAK_L    23 PEAK_R   24 PEAK_MPX   (read: the largest size since the last read, 0 .. 32767)
//  25 RF_HZ     (read) carrier rising edges at the pin per second (0.1 s gates, x10)
//  26 UNDERRUNS (read) audio samples that were missing   27 SYM_UNDER (read) symbol gaps
//  28 STATUS    (read) [0] RF clock locked   29 ID "FMTX"
//  30 RF_HIGH   (read) 250 MHz samples with the pin high in the last 0.1 s gate (25,000,000 = always high)
`timescale 1ns / 1ps
module ardzy_radio #(parameter [3:0] SLOT = 4'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        rf_out,               // the ODDR output: to the pin's output buffer
    input  wire        rf_pin                // the pin read back at the pad
);
    wire       reg_sel = (bus_addr[15:12] == SLOT);
    wire       rds_sel = (bus_addr[15:12] == SLOT + 4'd1);
    wire [3:0] cap_s = bus_addr[15:12] - SLOT - 4'd2;
    wire       cap_sel = (cap_s < 4'd4);
    wire [11:0] cap_a = {cap_s[1:0], bus_addr[11:2]};
    wire [9:0] idx = bus_addr[11:2];

    // ------------------------------------------------------------------ registers
    reg [8:0]  ctrl = 9'b0_0000_1110;
    reg [2:0]  mode = 3'd0;
    reg [31:0] freq = 32'd824633721;                    // 96.0 MHz
    reg [31:0] dev = 32'd1288530;
    reg [15:0] g_audio = 16'd28508, g_pilot = 16'd2949, g_rds = 16'd1311, am_depth = 16'd29491;
    reg [9:0]  vol = 10'd256, level = 10'd512;
    reg        key = 1'b0;
    reg [31:0] ratio = 32'd65536;
    reg [31:0] tone_l = 32'd87960930, tone_r = 32'd35184372;   // 1000 Hz, 400 Hz
    reg [8:0]  rds_n = 9'd16;
    reg        bank_req = 1'b0;
    reg [31:0] sym_lo = 32'd0;
    reg [2:0]  pk_clr = 3'd0;
    reg        log_clr = 1'b0;
    reg        tl_rst = 1'b0, tr_rst = 1'b0;               // a new tone frequency restarts its phase
    reg        a_flush = 1'b0, s_flush = 1'b0;             // empty the audio / symbol FIFO

    // ------------------------------------------------------------------ audio FIFO
    (* ram_style = "block" *) reg [31:0] afifo [0:8191];
    reg [13:0] aw = 14'd0, aw1 = 14'd0, aw2 = 14'd0, ar = 14'd0;
    wire [13:0] a_n = aw - ar;                           // places used (for the writer)
    wire [13:0] a_av = aw2 - ar;                         // samples surely readable (for the reader)
    reg         a_ready = 1'b0;                          // registered: a pop is never 2 clocks after the last
    reg [31:0] aq = 32'd0;
    always @(posedge clk) begin
        if (bus_we && reg_sel && idx == 10'd9 && a_n != 14'd8192) afifo[aw[12:0]] <= bus_wdata;
        aq <= afifo[ar[12:0]];
        aw1 <= aw; aw2 <= aw1;
    end

    // ------------------------------------------------------------------ symbol FIFO
    (* ram_style = "block" *) reg [61:0] sfifo [0:511];
    reg [9:0]  sw_p = 10'd0, sw1 = 10'd0, sw2 = 10'd0, sr_p = 10'd0;
    wire [9:0] s_n = sw_p - sr_p;
    wire [9:0] s_av = sw2 - sr_p;
    reg        s_ready = 1'b0;
    reg [61:0] sq = 62'd0;
    always @(posedge clk) begin
        if (bus_we && reg_sel && idx == 10'd17 && s_n != 10'd512) sfifo[sw_p[8:0]] <= {bus_wdata[29:0], sym_lo};
        sq <= sfifo[sr_p[8:0]];
        sw1 <= sw_p; sw2 <= sw1;
    end

    // ------------------------------------------------------------------ tables
    reg  [9:0]  sa_m = 10'd0, sa_t = 10'd0;
    wire signed [15:0] sin_m, sin_t;
    ardzy_sine_rom u_sm (.clk(clk), .a(sa_m), .q(sin_m));
    ardzy_sine_rom u_st (.clk(clk), .a(sa_t), .q(sin_t));
    reg  [7:0]  asin_a = 8'd0;
    wire [9:0]  asin_q;
    ardzy_radio_asin u_asin (.clk(clk), .a(asin_a), .q(asin_q));

    // ------------------------------------------------------------------ MAC engine (two channels)
    // tap t: coefficient ROM and history RAM read (1 clock), product (1 clock), add.
    reg        m_iss = 1'b0, m_v1 = 1'b0, m_v2 = 1'b0, m_sel = 1'b0;
    reg [6:0]  m_t = 7'd0, m_last = 7'd0;
    reg [2:0]  ph8 = 3'd0;                               // which of the 8 MPX samples per audio sample
    reg [5:0]  hp = 6'd0;                                // newest L/R sample in the history
    reg [3:0]  ip = 4'd0;                                // newest M/S sample
    wire signed [17:0] lpf_q, itp_q;
    ardzy_radio_lpf15  u_lpf (.clk(clk), .a(m_t[5:0]), .q(lpf_q));
    ardzy_radio_interp u_itp (.clk(clk), .a({m_t[3:0], ph8}), .q(itp_q));
    reg        m_ssb = 1'b0;                             // the MAC runs the SSB filter (32 taps per tick)
    wire signed [17:0] ssbi_q, ssbq_q;
    ardzy_radio_ssb_i u_ssbi (.clk(clk), .a({ph8, m_t[4:0]}), .q(ssbi_q));
    ardzy_radio_ssb_q u_ssbq (.clk(clk), .a({ph8, m_t[4:0]}), .q(ssbq_q));
    (* ram_style = "block" *) reg [15:0] h_m [0:255];   // (L+R)/2 after pre-emphasis, for the SSB filter
    reg [7:0]  mp = 8'd0, hm_wa = 8'd0;
    reg        hm_we = 1'b0;
    reg [15:0] hm_d = 16'd0, h_m_q = 16'd0;
    always @(posedge clk) begin
        if (hm_we) h_m[hm_wa] <= hm_d;
        h_m_q <= h_m[mp - {ph8, m_t[4:0]}];
    end
    (* ram_style = "block" *) reg [31:0] h_lr [0:63];   // {R, L} after pre-emphasis
    (* ram_style = "block" *) reg [31:0] h_ms [0:15];   // {S, M} after the low-pass
    reg [31:0] h_lr_q = 32'd0, h_ms_q = 32'd0;
    reg        h_lr_we = 1'b0, h_ms_we = 1'b0;
    reg [31:0] h_lr_d = 32'd0, h_ms_d = 32'd0;
    always @(posedge clk) begin
        if (h_lr_we) h_lr[hp] <= h_lr_d;
        if (h_ms_we) h_ms[ip] <= h_ms_d;
        h_lr_q <= h_lr[hp - m_t[5:0]];
        h_ms_q <= h_ms[ip - m_t[3:0]];
    end
    wire signed [17:0] m_ca = m_ssb ? ssbi_q : m_sel ? itp_q : lpf_q;
    wire signed [17:0] m_cb = m_ssb ? ssbq_q : m_sel ? itp_q : lpf_q;
    wire signed [15:0] m_da = m_ssb ? h_m_q : m_sel ? h_ms_q[15:0] : h_lr_q[15:0];
    wire signed [15:0] m_db = m_ssb ? h_m_q : m_sel ? h_ms_q[31:16] : h_lr_q[31:16];
    reg  signed [33:0] m_pa = 34'sd0, m_pb = 34'sd0;
    reg  signed [47:0] acc_a = 48'sd0, acc_b = 48'sd0, acc_c = 48'sd0, acc_d = 48'sd0;
    wire m_busy = m_iss | m_v1 | m_v2;

    // ------------------------------------------------------------------ the MPX machine (once per 256 clocks)
    reg [7:0] tc = 8'd0;
    always @(posedge clk) tc <= tc + 1'b1;
    wire tick = (tc == 8'd0);

    localparam [4:0] S_IDLE = 5'd0, S_TONE1 = 5'd1, S_TONE2 = 5'd2, S_TONE3 = 5'd3, S_POP = 5'd4, S_POPW = 5'd5,
                     S_RES1 = 5'd6, S_RES2 = 5'd7, S_VOL1 = 5'd8, S_VOL2 = 5'd9, S_PRE1 = 5'd10, S_PRE2 = 5'd11,
                     S_PUSH = 5'd12, S_LPF = 5'd13, S_MS = 5'd14, S_ITP0 = 5'd15, S_ITP = 5'd16, S_SIN = 5'd17,
                     S_MPX1 = 5'd18, S_MPX2 = 5'd19, S_MPX3 = 5'd20, S_MPX4 = 5'd21, S_DEV = 5'd22, S_SEND = 5'd23,
                     S_SSB = 5'd24, S_COR0 = 5'd25, S_COR = 5'd26, S_COR1 = 5'd27, S_COR2 = 5'd28;
    reg [4:0]  st = S_IDLE;
    reg [2:0]  k = 3'd0;
    localparam [31:0] PILOT_INC = 32'd208909520, RDS_INC = 32'd13056845;   // 19000.0007 Hz, and exactly / 16
    reg [31:0] pp = 32'd0, rp = 32'd0, tlp = 32'd0, trp = 32'd0, rfrac = 32'd0;
    wire [31:0] pp3 = pp + {pp[30:0], 1'b0};
    reg signed [15:0] pl = 0, pr = 0, cl = 0, cr = 0, xl = 0, xr = 0, x1l = 0, x1r = 0, yl = 0, yr = 0;
    reg signed [15:0] lpl = 0, lpr = 0, mup = 0, sup = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0, mpx = 0;
    reg signed [33:0] il_r = 0, ir_r = 0, pel_r = 0, per_r = 0;
    reg signed [26:0] vl_r = 0, vr_r = 0;
    reg signed [31:0] q_m = 0, q_s0 = 0, q_s = 0, q_p = 0, q_r0 = 0, q_r = 0, q_am = 0;
    reg signed [18:0] sum = 0;
    reg signed [16:0] env = 0;
    reg signed [47:0] dprod = 0;
    reg [31:0] underruns = 32'd0;
    reg [15:0] pk_l = 16'd0, pk_r = 16'd0, pk_m = 16'd0, mg_l = 16'd0, mg_r = 16'd0, mg_m = 16'd0;
    reg        rdiff = 1'b0;                             // differentially coded RDS bit (from the RDS engine)
    // SSB / DSB
    reg signed [15:0] ssb_i = 0, ssb_q = 0;              // the SSB filter's last I and Q (48828 per second)
    reg signed [18:0] cx = 0, cy = 0;                    // CORDIC
    reg [15:0] cz = 16'd0, c_ang = 16'd0;
    reg [3:0]  ci = 4'd0;
    reg signed [34:0] c_mag = 0;
    wire       ssb_mode = (mode == 3'd5) || (mode == 3'd6) || (mode == 3'd7);
    reg [15:0] atan_t;
    always @* case (ci)
        4'd0: atan_t = 16'd8192;  4'd1: atan_t = 16'd4836;  4'd2: atan_t = 16'd2555;  4'd3: atan_t = 16'd1297;
        4'd4: atan_t = 16'd651;   4'd5: atan_t = 16'd326;   4'd6: atan_t = 16'd163;   4'd7: atan_t = 16'd81;
        4'd8: atan_t = 16'd41;    4'd9: atan_t = 16'd20;    4'd10: atan_t = 16'd10;   4'd11: atan_t = 16'd5;
        4'd12: atan_t = 16'd3;    default: atan_t = 16'd1;
    endcase
    wire signed [16:0] y_sum = yl + yr;
    // towards the RF clock
    reg [31:0] o_inc = 32'd0;
    reg [9:0]  o_duty = 10'd0, o_ph = 10'd0;
    reg        o_tog = 1'b0;
    // symbol player outputs
    reg [23:0] s_off = 24'd0;
    reg [7:0]  s_ph = 8'd0;
    reg [9:0]  s_duty = 10'd0;

    function signed [15:0] clip16(input signed [31:0] v);
        clip16 = (v > 32'sd32767) ? 16'sd32767 : (v < -32'sd32767) ? -16'sd32767 : v[15:0];
    endfunction
    function [15:0] mag(input signed [15:0] v);
        mag = v[15] ? (~v + 1'b1) : v;
    endfunction
    wire [15:0] c_pre = (ctrl[5:4] == 2'd1) ? 16'd625 : (ctrl[5:4] == 2'd2) ? 16'd937 : 16'd0;   // tau * fs * 256
    wire signed [16:0] d_l = cl - pl, d_r = cr - pr, e_l = xl - x1l, e_r = xr - x1r;
    wire signed [16:0] frac = {1'b0, rfrac[15:0]};
    wire signed [16:0] m_sum = lpl + lpr, s_dif = lpl - lpr;
    wire signed [15:0] s_mod = q_s0[30:15], r_mod = q_r0[30:15];
    wire signed [15:0] rds_sym = rdiff ? s4 : -s4;
    wire signed [31:0] inc_off = dprod[47:16];

    always @(posedge clk) begin
        h_lr_we <= 1'b0; h_ms_we <= 1'b0;
        // (aw2 may lag a flush by 2 clocks: then a_av > a_n, not ready)
        a_ready <= !a_flush && (a_av != 14'd0) && (a_av <= a_n);
        // MAC engine
        m_v1 <= m_iss; m_v2 <= m_v1;
        if (m_iss) begin
            m_t <= m_t + 1'b1;
            if (m_t == m_last) m_iss <= 1'b0;
        end
        hm_we <= 1'b0;
        if (m_v1) begin m_pa <= m_ca * m_da; m_pb <= m_cb * m_db; end
        if (m_v2 && m_ssb) begin acc_c <= acc_c + m_pa; acc_d <= acc_d + m_pb; end
        else if (m_v2) begin acc_a <= acc_a + m_pa; acc_b <= acc_b + m_pb; end
        if (pk_clr[0]) pk_l <= 16'd0;
        if (pk_clr[1]) pk_r <= 16'd0;
        if (pk_clr[2]) pk_m <= 16'd0;

        case (st)
        S_IDLE: if (tick) begin
            pp <= pp + PILOT_INC;
            rp <= rp + RDS_INC;
            if (ph8 != 3'd0) st <= S_ITP0;
            else if (ctrl[7]) begin sa_t <= tlp[31:22]; st <= S_TONE1; end
            else begin rfrac <= rfrac + ratio; st <= S_POP; end
        end
        // ---- test tones (sine ROM: 1 clock)
        S_TONE1: begin sa_t <= trp[31:22]; st <= S_TONE2; end
        S_TONE2: begin xl <= sin_t >>> 1; tlp <= tlp + tone_l; trp <= trp + tone_r; st <= S_TONE3; end
        S_TONE3: begin xr <= sin_t >>> 1; st <= S_VOL1; end
        // ---- audio from the FIFO, linear resampling
        S_POP: if (rfrac[31:16] != 16'd0) begin
            rfrac[31:16] <= rfrac[31:16] - 1'b1;
            pl <= cl; pr <= cr;
            if (a_ready && !a_flush) begin cl <= aq[15:0]; cr <= aq[31:16]; ar <= ar + 1'b1; end
            else begin cl <= 16'sd0; cr <= 16'sd0; underruns <= underruns + 1'b1; end
            st <= S_POPW;
        end else st <= S_RES1;
        S_POPW: st <= S_POP;                             // the FIFO output needs one clock
        S_RES1: begin il_r <= d_l * frac; ir_r <= d_r * frac; st <= S_RES2; end
        S_RES2: begin xl <= pl + il_r[31:16]; xr <= pr + ir_r[31:16]; st <= S_VOL1; end
        // ---- volume, pre-emphasis, clip
        S_VOL1: begin vl_r <= xl * $signed({1'b0, vol}); vr_r <= xr * $signed({1'b0, vol}); st <= S_VOL2; end
        S_VOL2: begin
            xl <= ctrl[6] ? 16'sd0 : clip16(vl_r >>> 8);
            xr <= ctrl[6] ? 16'sd0 : clip16(vr_r >>> 8);
            st <= S_PRE1;
        end
        S_PRE1: begin pel_r <= e_l * $signed({1'b0, c_pre}); per_r <= e_r * $signed({1'b0, c_pre}); st <= S_PRE2; end
        S_PRE2: begin
            yl <= clip16(xl + (pel_r >>> 8));
            yr <= clip16(xr + (per_r >>> 8));
            x1l <= xl; x1r <= xr;
            st <= S_PUSH;
        end
        S_PUSH: begin
            h_lr_d <= {yr, yl}; h_lr_we <= 1'b1;         // written at the next clock
            hm_d <= y_sum[16:1]; hm_wa <= mp + 1'b1; hm_we <= 1'b1; mp <= mp + 1'b1;
            mg_l <= mag(yl); mg_r <= mag(yr);            // (compared with the peaks next clock)
            k <= 3'd0;
            st <= S_LPF;
        end
        // ---- 15 kHz low-pass, 63 taps
        S_LPF: begin
            if (k != 3'd3) k <= k + 1'b1;
            if (k == 3'd0) begin
                m_t <= 7'd0; m_last <= 7'd62; m_sel <= 1'b0; m_iss <= 1'b1;
                acc_a <= 48'sd0; acc_b <= 48'sd0;
                if (mg_l > pk_l) pk_l <= mg_l;
                if (mg_r > pk_r) pk_r <= mg_r;
            end else if (k == 3'd3 && !m_busy) begin
                lpl <= clip16(acc_a >>> 17); lpr <= clip16(acc_b >>> 17);
                st <= S_MS;
            end
        end
        S_MS: begin
            hp <= hp + 1'b1;
            ip <= ip + 1'b1;
            if (mode == 3'd5) h_ms_d <= {ssb_q, ssb_i};                 // USB: I + jQ
            else if (mode == 3'd6) h_ms_d <= {-ssb_q, ssb_i};           // LSB: I - jQ
            else if (mode == 3'd7 || ctrl[8]) h_ms_d <= {16'd0, ssb_i}; // DSB, narrow: the band-passed sound
            else h_ms_d <= {s_dif[16:1], m_sum[16:1]};
            st <= S_ITP0;
        end
        // ---- x8 interpolation: the 12 taps of this phase, M and S
        S_ITP0: begin
            h_ms_we <= (ph8 == 3'd0);                    // a new M/S sample (phase 0 only), written next clock
            k <= 3'd0;
            st <= S_ITP;
        end
        S_ITP: begin
            if (k != 3'd3) k <= k + 1'b1;
            if (k == 3'd1) begin
                m_t <= 7'd0; m_last <= 7'd11; m_sel <= 1'b1; m_iss <= 1'b1;
                acc_a <= 48'sd0; acc_b <= 48'sd0;
            end else if (k == 3'd3 && !m_busy) begin
                mup <= clip16(acc_a >>> 16); sup <= clip16(acc_b >>> 16);
                k <= 3'd0;
                st <= S_SSB;
            end
        end
        // ---- the SSB filter: 256 taps, 32 in each of the 8 ticks of an audio sample
        S_SSB: begin
            if (k != 3'd3) k <= k + 1'b1;
            if (k == 3'd1) begin
                m_t <= 7'd0; m_last <= 7'd31; m_ssb <= 1'b1; m_iss <= 1'b1;
                if (ph8 == 3'd0) begin acc_c <= 48'sd0; acc_d <= 48'sd0; end
            end else if (k == 3'd3 && !m_busy) begin
                if (ph8 == 3'd7) begin ssb_i <= clip16(acc_c >>> 17); ssb_q <= clip16(acc_d >>> 17); end
                m_ssb <= 1'b0;
                sa_m <= pp[31:22];
                k <= 3'd0;
                st <= S_SIN;
            end
        end
        // ---- sin(p), sin(2p), sin(3p), sin(RDS bit phase)
        S_SIN: begin
            k <= k + 1'b1;
            case (k)
                3'd0: sa_m <= pp[30:21];
                3'd1: begin s1 <= sin_m; sa_m <= pp3[31:22]; end
                3'd2: begin s2 <= sin_m; sa_m <= rp[31:22]; end
                3'd3: s3 <= sin_m;
                default: begin s4 <= sin_m; st <= S_MPX1; end
            endcase
        end
        S_MPX1: begin
            q_m <= mup * $signed({1'b0, g_audio[14:0]});
            q_s0 <= sup * s2;
            q_p <= s1 * $signed({1'b0, g_pilot[14:0]});
            q_r0 <= rds_sym * s3;
            q_am <= mup * $signed({1'b0, am_depth[14:0]});
            st <= S_MPX2;
        end
        S_MPX2: begin
            q_s <= ctrl[1] ? s_mod * $signed({1'b0, g_audio[14:0]}) : 32'sd0;
            q_r <= ctrl[2] ? r_mod * $signed({1'b0, g_rds[14:0]}) : 32'sd0;
            if (!(ctrl[1] && ctrl[3])) q_p <= 32'sd0;
            env <= 17'sd16384 + (q_am >>> 16);
            st <= S_MPX3;
        end
        S_MPX3: begin
            sum <= (q_m >>> 15) + (q_s >>> 15) + (q_p >>> 15) + (q_r >>> 15);
            asin_a <= env[16] ? 8'd0 : env[15] ? 8'd255 : env[14:7];
            st <= S_MPX4;
        end
        S_MPX4: begin mpx <= clip16(sum); st <= ssb_mode ? S_COR0 : S_DEV; end
        // ---- I + jQ -> strength and phase (CORDIC, 14 steps)
        S_COR0: begin
            if (mup[15]) begin cx <= -mup; cy <= -sup; cz <= 16'h8000; end
            else begin cx <= mup; cy <= sup; cz <= 16'd0; end
            ci <= 4'd0;
            st <= S_COR;
        end
        S_COR: begin
            if (cy[18]) begin cx <= cx - (cy >>> ci); cy <= cy + (cx >>> ci); cz <= cz - atan_t; end
            else begin cx <= cx + (cy >>> ci); cy <= cy - (cx >>> ci); cz <= cz + atan_t; end
            ci <= ci + 1'b1;
            if (ci == 4'd13) st <= S_COR1;
        end
        S_COR1: begin c_mag <= cx * 35'sd19898; c_ang <= cz; st <= S_COR2; end   // x 0.60725: the CORDIC gain
        S_COR2: begin
            asin_a <= (c_mag[34:15] > 20'd32767) ? 8'd255 : c_mag[29:22];   // the strength's top 8 bits
            st <= S_DEV;
        end
        S_DEV: begin
            dprod <= mpx * $signed({1'b0, dev[30:0]});
            mg_m <= mag(mpx);
            st <= S_SEND;
        end
        S_SEND: begin                                    // hand the new values to the RF clock
            case (mode)
                3'd1: begin o_inc <= freq; o_duty <= key ? level : 10'd0; o_ph <= 10'd0; end
                3'd2: begin o_inc <= freq + inc_off; o_duty <= level; o_ph <= 10'd0; end
                3'd3: begin o_inc <= freq; o_duty <= asin_q; o_ph <= 10'd0; end
                3'd4: begin o_inc <= freq + {{8{s_off[23]}}, s_off}; o_duty <= s_duty; o_ph <= {s_ph, 2'b00}; end
                3'd5, 3'd6, 3'd7: begin o_inc <= freq; o_duty <= asin_q; o_ph <= c_ang[15:6]; end
                default: begin o_inc <= freq; o_duty <= 10'd0; o_ph <= 10'd0; end
            endcase
            if (!ctrl[0]) o_duty <= 10'd0;
            o_tog <= ~o_tog;
            ph8 <= ph8 + 1'b1;
            if (mg_m > pk_m) pk_m <= mg_m;
            st <= S_IDLE;
        end
        default: st <= S_IDLE;
        endcase
        if (a_flush) ar <= aw;
        if (tl_rst) tlp <= 32'd0;
        if (tr_rst) trp <= 32'd0;
        if (!rstn) begin st <= S_IDLE; m_iss <= 1'b0; end
    end

    // ------------------------------------------------------------------ RDS engine (a bit at each bit-phase wrap)
    (* ram_style = "block" *) reg [25:0] rds_mem [0:511];
    always @(posedge clk) if (bus_we && rds_sel && idx < 10'd512) rds_mem[idx[8:0]] <= bus_wdata[25:0];
    reg        bank = 1'b0;
    reg [7:0]  rblk = 8'd0;
    reg [4:0]  rbit = 5'd25;
    reg [25:0] blk = 26'd0;
    reg [31:0] rp_last = 32'd0;
    reg [31:0] rlog_sr = 32'd0;
    reg [4:0]  rlog_n = 5'd0;
    reg [31:0] rlog [0:63];
    reg [6:0]  rlw = 7'd0, rlr = 7'd0;
    wire [6:0] rl_n = rlw - rlr;
    wire [8:0] nblk = {1'b0, rblk} + 1'b1;
    wire       rds_wrap = (rp < rp_last);
    wire       dbit = blk[rbit];
    always @(posedge clk) begin
        rp_last <= rp;
        blk <= rds_mem[{bank, rblk}];
        if (rds_wrap) begin
            rdiff <= rdiff ^ dbit;
            rlog_sr <= {rlog_sr[30:0], dbit};
            rlog_n <= rlog_n + 1'b1;
            if (rlog_n == 5'd31 && rl_n != 7'd64) begin rlog[rlw[5:0]] <= {rlog_sr[30:0], dbit}; rlw <= rlw + 1'b1; end
            if (rbit == 5'd0) begin
                rbit <= 5'd25;
                if (nblk >= rds_n) begin rblk <= 8'd0; bank <= bank_req; end
                else rblk <= nblk[7:0];
            end else rbit <= rbit - 1'b1;
        end
        if (log_clr) begin rlw <= rlr; rlog_n <= 5'd0; end
    end

    // ------------------------------------------------------------------ symbol player (1 us steps)
    reg [6:0]  us_c = 7'd0;
    reg [19:0] s_left = 20'd0;
    reg [31:0] s_under = 32'd0;
    always @(posedge clk) begin
        s_ready <= !s_flush && (s_av != 10'd0) && (s_av <= s_n);
        us_c <= (us_c == 7'd99) ? 7'd0 : us_c + 1'b1;
        if (mode != 3'd4) begin s_left <= 20'd0; s_duty <= 10'd0; end
        else if (us_c == 7'd0) begin
            if (s_left > 20'd1) s_left <= s_left - 1'b1;
            else if (s_ready && !s_flush) begin
                s_off <= sq[23:0]; s_ph <= sq[31:24]; s_duty <= sq[41:32]; s_left <= sq[61:42];
                sr_p <= sr_p + 1'b1;
            end else begin
                if (s_left == 20'd1) s_under <= s_under + 1'b1;    // the queue ran dry after a symbol
                s_duty <= 10'd0; s_left <= 20'd0;
            end
        end
        if (s_flush) begin sr_p <= sw_p; s_left <= 20'd0; s_duty <= 10'd0; end
    end

    // ------------------------------------------------------------------ capture of 4096 MPX samples
    (* ram_style = "block" *) reg [15:0] cap [0:4095];
    reg [12:0] cap_i = 13'd4096;
    reg [15:0] cap_q = 16'd0;
    reg        cap_go = 1'b0, cap_iq = 1'b0;
    always @(posedge clk) begin
        if (cap_go) cap_i <= 13'd0;
        else if (st == S_DEV && cap_iq && !cap_i[12]) begin cap[cap_i[11:0]] <= mup; cap_i <= cap_i + 1'b1; end
        else if (st == S_SEND && cap_iq && !cap_i[12]) begin cap[cap_i[11:0]] <= sup; cap_i <= cap_i + 1'b1; end
        else if (st == S_SEND && !cap_i[12]) begin cap[cap_i[11:0]] <= mpx; cap_i <= cap_i + 1'b1; end
        cap_q <= cap[cap_a];
    end

    // ------------------------------------------------------------------ RF clock domain (250 MHz)
    wire fb_o, fb_i, r250_o, rclk, locked;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(4.0)) u_mmcm (
        .CLKIN1(clk), .CLKFBIN(fb_i), .CLKFBOUT(fb_o), .RST(~rstn), .PWRDWN(1'b0), .CLKOUT0(r250_o), .LOCKED(locked));
    BUFG u_bfb (.I(fb_o), .O(fb_i));
    BUFG u_br (.I(r250_o), .O(rclk));
    // o_inc, o_duty and o_ph are steady for 256 system clocks after each o_tog change: take them
    // when the (synchronized) toggle arrives
    reg [2:0]  tg = 3'd0;
    reg [31:0] r_inc = 32'd0, r_inc2 = 32'd0;
    reg [9:0]  r_duty = 10'd0, r_ph = 10'd0;
    always @(posedge rclk) begin
        tg <= {tg[1:0], o_tog};
        if (tg[2] != tg[1]) begin r_inc <= o_inc; r_inc2 <= {o_inc[30:0], 1'b0}; r_duty <= o_duty; r_ph <= o_ph; end
    end
    // Two carrier samples per clock: P (first half) and P + inc (second half). Every adder is at most
    // 17 bits long: the 32-bit sums are split in two halves with the carry taken one clock later.
    //   accumulator: lo and hi halves; the true phase is {hi + c, lo} (c = the low half's last carry)
    reg [15:0] acc_lo = 16'd0, acc_hi = 16'd0, p_lo = 16'd0, p_hi = 16'd0, q_lo = 16'd0, q_hp = 16'd0, q_hi = 16'd0;
    reg [15:0] p_hi1 = 16'd0, p_hi2 = 16'd0;
    reg        c_lo = 1'b0, qc = 1'b0;
    reg [9:0]  a0 = 10'd0, a1 = 10'd0;
    reg        d1 = 1'b0, d2 = 1'b0;
    always @(posedge rclk) begin
        {c_lo, acc_lo} <= {1'b0, acc_lo} + {1'b0, r_inc2[15:0]};
        acc_hi <= acc_hi + r_inc2[31:16] + c_lo;
        p_lo <= acc_lo;                                   // stage 1: P
        p_hi <= acc_hi + c_lo;
        {qc, q_lo} <= {1'b0, p_lo} + {1'b0, r_inc[15:0]}; // stage 2: P + inc
        q_hp <= p_hi + r_inc[31:16];
        p_hi1 <= p_hi;
        q_hi <= q_hp + qc;                                // stage 3
        p_hi2 <= p_hi1;
        a0 <= p_hi2[15:6] + r_ph;                         // stage 4: the top 10 phase bits + PSK phase
        a1 <= q_hi[15:6] + r_ph;
        d1 <= (a0 < r_duty);                              // stage 5: inside the pulse?
        d2 <= (a1 < r_duty);
    end
    ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")) u_oddr (
        .C(rclk), .CE(1'b1), .D1(d1), .D2(d2), .R(1'b0), .S(1'b0), .Q(rf_out));
    // rising edges at the pin, counted at 250 MHz over 0.1 s gates. The pad is far from the counter:
    // the edge goes through 3 registers, and the counter is a 6-bit part with its carry taken one
    // clock later into an 18-bit part (no long adder at 250 MHz); the sum is made at 100 MHz.
    reg [2:0]  ps = 3'd0;
    reg        e1 = 1'b0, e2 = 1'b0, e3 = 1'b0, gend = 1'b0, ec_c = 1'b0, ec_c2 = 1'b0, h_c = 1'b0, h_c2 = 1'b0, etog = 1'b0;
    reg [24:0] gcnt = 25'd0;
    reg [5:0]  ec_lo = 6'd0, h_lo = 6'd0;
    reg [17:0] ec_hi = 18'd0, h_hi = 18'd0;
    // and the time the pin is high (samples at 250 MHz): the pulse width, so AM and the power setting
    // can be measured. The carrier is not in step with the 250 MHz clock, so the average is exact.
    reg        p1 = 1'b0, p2 = 1'b0, p3 = 1'b0, pc_c = 1'b0, pc_c2 = 1'b0, ph_c = 1'b0, ph_c2 = 1'b0;
    reg [5:0]  pc_lo = 6'd0, ph_lo = 6'd0;
    reg [18:0] pc_hi = 19'd0, ph_hi = 19'd0;
    always @(posedge rclk) begin
        ps <= {ps[1:0], rf_pin};
        e1 <= ps[1] & ~ps[2];
        e2 <= e1;
        e3 <= e2;
        p1 <= ps[1];
        p2 <= p1;
        p3 <= p2;
        gend <= (gcnt == 25'd24_999_998);                // registered: high while gcnt = 24 999 999
        if (gend) begin
            gcnt <= 25'd0;
            h_lo <= ec_lo; h_c <= ec_c; h_c2 <= ec_c2; h_hi <= ec_hi; etog <= ~etog;
            ec_lo <= {5'd0, e3}; ec_c <= 1'b0; ec_c2 <= 1'b0; ec_hi <= 18'd0;
            ph_lo <= pc_lo; ph_c <= pc_c; ph_c2 <= pc_c2; ph_hi <= pc_hi;
            pc_lo <= {5'd0, p3}; pc_c <= 1'b0; pc_c2 <= 1'b0; pc_hi <= 19'd0;
        end else begin
            gcnt <= gcnt + 1'b1;
            {ec_c, ec_lo} <= {1'b0, ec_lo} + e3;         // the carry goes through one more register,
            ec_c2 <= ec_c;                                // so the long route to the high part has a whole clock
            ec_hi <= ec_hi + ec_c2;
            {pc_c, pc_lo} <= {1'b0, pc_lo} + p3;
            pc_c2 <= pc_c;
            pc_hi <= pc_hi + pc_c2;
        end
    end
    reg [2:0]  et = 3'd0;
    reg [31:0] rf_hz = 32'd0, rf_high = 32'd0;
    wire [23:0] ehold = {h_hi + h_c + h_c2, 6'd0} + h_lo;      // steady for 0.1 s when read
    wire [24:0] phold = {ph_hi + ph_c + ph_c2, 6'd0} + ph_lo;
    always @(posedge clk) begin
        et <= {et[1:0], etog};
        if (et[2] != et[1]) begin rf_hz <= ehold * 32'd10; rf_high <= {7'd0, phold}; end
    end

    // ------------------------------------------------------------------ bus
    reg rd_cap = 1'b0;
    always @(posedge clk) begin
        cap_go <= 1'b0; pk_clr <= 3'd0; log_clr <= 1'b0; tl_rst <= 1'b0; tr_rst <= 1'b0; a_flush <= 1'b0; s_flush <= 1'b0;
        if (!rstn) begin
            ctrl <= 9'b0_0000_1110; mode <= 3'd0; key <= 1'b0;
        end else if (bus_we && reg_sel) case (idx)
            10'd0: ctrl <= bus_wdata[8:0];
            10'd1: mode <= bus_wdata[2:0];
            10'd2: freq <= bus_wdata;
            10'd3: dev <= bus_wdata;
            10'd4: g_audio <= bus_wdata[15:0];
            10'd5: g_pilot <= bus_wdata[15:0];
            10'd6: g_rds <= bus_wdata[15:0];
            10'd7: vol <= bus_wdata[9:0];
            10'd8: ratio <= (bus_wdata < 32'd4096) ? 32'd4096 : (bus_wdata > 32'd262144) ? 32'd262144 : bus_wdata;
            10'd9: if (a_n != 14'd8192) aw <= aw + 1'b1;
            10'd11: begin tone_l <= bus_wdata; tl_rst <= 1'b1; end
            10'd12: begin tone_r <= bus_wdata; tr_rst <= 1'b1; end
            10'd13: am_depth <= bus_wdata[15:0];
            10'd14: begin level <= bus_wdata[9:0]; key <= bus_wdata[16]; end
            10'd15: begin rds_n <= (bus_wdata[8:0] < 9'd4) ? 9'd4 : (bus_wdata[8:0] > 9'd256) ? 9'd256 : bus_wdata[8:0];
                          bank_req <= bus_wdata[16]; end
            10'd10: a_flush <= 1'b1;
            10'd16: sym_lo <= bus_wdata;
            10'd17: if (s_n != 10'd512) sw_p <= sw_p + 1'b1;
            10'd18: s_flush <= 1'b1;
            10'd19: begin cap_go <= bus_wdata[0]; cap_iq <= bus_wdata[1]; end
            10'd21: log_clr <= 1'b1;
            default: ;
        endcase
        rd_cap <= bus_re && cap_sel;
        if (bus_re) begin
            if (!reg_sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {23'd0, ctrl};
                10'd1: bus_rdata <= {29'd0, mode};
                10'd2: bus_rdata <= freq;
                10'd3: bus_rdata <= dev;
                10'd4: bus_rdata <= {16'd0, g_audio};
                10'd5: bus_rdata <= {16'd0, g_pilot};
                10'd6: bus_rdata <= {16'd0, g_rds};
                10'd7: bus_rdata <= {22'd0, vol};
                10'd8: bus_rdata <= ratio;
                10'd10: bus_rdata <= {18'd0, a_n};
                10'd11: bus_rdata <= tone_l;
                10'd12: bus_rdata <= tone_r;
                10'd13: bus_rdata <= {16'd0, am_depth};
                10'd14: bus_rdata <= {15'd0, key, 6'd0, level};
                10'd15: bus_rdata <= {14'd0, bank, bank_req, 7'd0, rds_n};
                10'd16: bus_rdata <= sym_lo;
                10'd18: bus_rdata <= {22'd0, s_n};
                10'd19: bus_rdata <= {31'd0, ~cap_i[12]};
                10'd20: if (rl_n != 7'd0) begin bus_rdata <= rlog[rlr[5:0]]; rlr <= rlr + 1'b1; end
                        else bus_rdata <= 32'd0;
                10'd21: bus_rdata <= {25'd0, rl_n};
                10'd22: begin bus_rdata <= {16'd0, pk_l}; pk_clr[0] <= 1'b1; end
                10'd23: begin bus_rdata <= {16'd0, pk_r}; pk_clr[1] <= 1'b1; end
                10'd24: begin bus_rdata <= {16'd0, pk_m}; pk_clr[2] <= 1'b1; end
                10'd25: bus_rdata <= rf_hz;
                10'd26: bus_rdata <= underruns;
                10'd27: bus_rdata <= s_under;
                10'd28: bus_rdata <= {31'd0, locked};
                10'd29: bus_rdata <= 32'h464D5458;          // "FMTX"
                10'd30: bus_rdata <= rf_high;
                default: bus_rdata <= 32'd0;
            endcase
        end
        if (rd_cap) bus_rdata <= {{16{cap_q[15]}}, cap_q};
    end
endmodule
