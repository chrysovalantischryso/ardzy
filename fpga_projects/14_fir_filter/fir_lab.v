// 14 FIR filter lab: a digital filter in hardware, the way DSP chips (and radios, and audio gear) do it.
//
//   y[n] = (c[0] x[n] + c[1] x[n-1] + ... + c[N-1] x[n-N+1]) >> SHIFT        (then limited to 16 bits)
//
// One multiplier (a DSP48 slice) does one tap per clock: a 64-tap filter takes 68 clocks per sample, so it
// filters up to 1.47 million samples per second. The samples come from the ARM (through a FIFO) or from a
// built-in generator (a sine of any frequency plus noise) at a sample rate you choose; the results go into a
// FIFO for the ARM, and two peak meters measure the input and the output (a frequency response in seconds).
//
// Registers (word index, slot SLOT):
//   0  CTRL       write: [0] reset (history, FIFOs, meters)  [1] source: 0 = ARM, 1 = generator
//   1  STATUS     read : [7:0] input FIFO level  [17:8] output FIFO level  [24] busy
//   2  TAPS       1 .. 64                          3  SHIFT  0 .. 47 (the result is divided by 2^SHIFT)
//   4  IN         write: one sample (signed 16 bit) into the input FIFO
//   5  OUT        read : the oldest result: [31:16] output, [15:0] the input sample it belongs to
//   7  GEN_FREQ   the generator's phase step per sample (frequency = step / 2^32 * sample rate)
//   8  GEN_RATE   clocks per generator sample (sample rate = 100 MHz / GEN_RATE, at least TAPS + 4)
//   9  GEN_AMP    0 .. 32767                      10  GEN_NOISE  0 .. 32767 (white noise added)
//  11  PEAK_IN    read: largest |input| since the last read     12  PEAK_OUT  the same for the output
//  13  SAMPLES    samples filtered                 14  CLIPPED  results that did not fit in 16 bits
//  15  CAPTURE    write n: the generator's next n results also go into the output FIFO
//  16  LOST       results lost because the output FIFO was full
//  64 .. 127  COEF[k]  the coefficients, signed 18 bit
// 1023  ID "FIR1"
`timescale 1ns / 1ps
module fir_lab #(parameter [3:0] SLOT = 4'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        busy_led
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    reg        rst = 1'b1, use_gen = 1'b0;
    reg [6:0]  taps = 7'd16;
    reg [5:0]  shift = 6'd17;
    reg [31:0] gfreq = 32'd0, grate = 32'd100, gcount = 32'd0, phase = 32'd0, lfsr = 32'hACE1ACE1;
    reg [15:0] gamp = 16'd16384, gnoise = 16'd0;
    reg [31:0] samples = 32'd0, clipped = 32'd0, lost = 32'd0, capture = 32'd0;
    reg [15:0] peak_in = 16'd0, peak_out = 16'd0;

    (* ram_style = "distributed" *) reg signed [17:0] coef [0:63];
    (* ram_style = "distributed" *) reg signed [15:0] hist [0:63];

    always @(posedge clk) begin
        rst <= !rstn || (bus_we && sel && idx == 10'd0 && bus_wdata[0]);
        if (bus_we && sel) begin
            case (idx)
                10'd0: use_gen <= bus_wdata[1];
                10'd2: taps <= (bus_wdata[6:0] == 7'd0) ? 7'd1 : (bus_wdata[6:0] > 7'd64 ? 7'd64 : bus_wdata[6:0]);
                10'd3: shift <= (bus_wdata[5:0] > 6'd47) ? 6'd47 : bus_wdata[5:0];
                10'd7: gfreq <= bus_wdata;
                10'd8: grate <= bus_wdata;
                10'd9: gamp <= (bus_wdata[15:0] > 16'd32767) ? 16'd32767 : bus_wdata[15:0];
                10'd10: gnoise <= (bus_wdata[15:0] > 16'd32767) ? 16'd32767 : bus_wdata[15:0];
                default: ;
            endcase
            if (idx >= 10'd64 && idx <= 10'd127) coef[idx[5:0]] <= bus_wdata[17:0];
        end
    end

    // ---- the input FIFO (from the ARM)
    wire [15:0] in_d;
    wire in_v;
    reg  in_take = 1'b0;
    wire [6:0] in_level;
    ardzy_axis_fifo #(.W(16), .AW(6)) u_in (.clk(clk), .rst(rst), .s_tdata(bus_wdata[15:0]), .s_tlast(1'b0),
        .s_tvalid(bus_we && sel && idx == 10'd4), .s_tready(), .m_tdata(in_d), .m_tlast(), .m_tvalid(in_v),
        .m_tready(in_take), .level(in_level));

    // ---- the generator: sine (1024-point table) * amplitude + noise, one sample every GEN_RATE clocks
    wire signed [15:0] sine;
    ardzy_sine_rom u_rom (.clk(clk), .a(phase[31:22]), .q(sine));
    wire signed [31:0] s_amp = sine * $signed({1'b0, gamp});
    wire signed [31:0] s_noise = $signed(lfsr[15:0]) * $signed({1'b0, gnoise});
    wire signed [17:0] g_sum = (s_amp >>> 15) + (s_noise >>> 15);
    reg  signed [15:0] gen_x = 16'sd0;
    always @(posedge clk) begin
        gen_x <= (g_sum > 18'sd32767) ? 16'sd32767 : (g_sum < -18'sd32768) ? -16'sd32768 : g_sum[15:0];
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
    end
    wire tick = use_gen && (gcount == 32'd0);
    always @(posedge clk) begin
        if (rst || !use_gen) gcount <= 32'd0;
        else gcount <= (gcount + 1'b1 >= grate) ? 32'd0 : gcount + 1'b1;
        if (tick) phase <= phase + gfreq;
    end

    // ---- the filter: issue (read x and c) -> multiply (DSP48) -> accumulate
    reg        running = 1'b0, v1 = 1'b0, v2 = 1'b0, l1 = 1'b0, l2 = 1'b0, f1 = 1'b0, f2 = 1'b0, rdy = 1'b0;
    reg [5:0]  wp = 6'd0, cur = 6'd0;
    reg [6:0]  k = 7'd0;
    reg signed [15:0] xa = 16'sd0, xin = 16'sd0, xcur = 16'sd0;
    reg signed [17:0] ca = 18'sd0;
    reg signed [33:0] prod = 34'sd0;
    reg signed [47:0] acc = 48'sd0;
    reg        clearing = 1'b1;             // after a reset the history is set to 0, one place per clock
    reg [5:0]  ci = 6'd0;
    wire busy = running | v1 | v2 | rdy | clearing;
    wire start_arm = !use_gen && in_v && !busy && !in_take;
    wire start_gen = tick && !busy;

    // the result, in three clocks (one clock was too long a path): 1. divide by 2^SHIFT  2. limit to 16 bits
    // 3. meters and the output FIFO. Each stage keeps its own copy of the input sample.
    reg  signed [47:0] ys = 48'sd0;
    reg  signed [15:0] y = 16'sd0, xs1 = 16'sd0, xs2 = 16'sd0;
    reg  [15:0] absx2 = 16'd0;
    reg         r1 = 1'b0, r2 = 1'b0, clip = 1'b0;
    wire [15:0] absy = y[15] ? -y : y;
    reg  out_push = 1'b0;
    reg  [31:0] out_word = 32'd0;
    wire out_ready;

    always @(posedge clk) begin
        in_take <= 1'b0;
        out_push <= 1'b0;
        v1 <= 1'b0;
        if (rst) begin
            running <= 1'b0; v2 <= 1'b0; rdy <= 1'b0; r1 <= 1'b0; r2 <= 1'b0; wp <= 6'd0; clearing <= 1'b1; ci <= 6'd0;
            samples <= 32'd0; clipped <= 32'd0; lost <= 32'd0; peak_in <= 16'd0; peak_out <= 16'd0; capture <= 32'd0;
        end else begin
            if (clearing) begin
                hist[ci] <= 16'sd0;
                ci <= ci + 1'b1;
                if (ci == 6'd63) clearing <= 1'b0;
            end
            // a new sample: into the history, then taps x[n], x[n-1], ...
            if (start_arm || start_gen) begin
                hist[wp] <= start_gen ? gen_x : in_d;
                xin <= start_gen ? gen_x : in_d;
                cur <= wp;
                wp <= wp + 1'b1;
                k <= 7'd0;
                running <= 1'b1;
                if (start_arm) in_take <= 1'b1;
            end else if (running) begin
                xa <= hist[cur - k[5:0]];
                ca <= coef[k[5:0]];
                v1 <= 1'b1;
                f1 <= (k == 7'd0);
                l1 <= (k == taps - 1'b1);
                if (k == taps - 1'b1) running <= 1'b0;
                k <= k + 1'b1;
            end
            // multiply
            v2 <= v1; l2 <= l1; f2 <= f1;
            if (v1) prod <= xa * ca;
            // accumulate
            if (v2) acc <= f2 ? {{14{prod[33]}}, prod} : acc + {{14{prod[33]}}, prod};
            rdy <= v2 && l2;
            // the result: 1. shift
            r1 <= rdy;
            if (rdy) begin ys <= acc >>> shift; xs1 <= xin; end
            // 2. limit to 16 bits
            r2 <= r1;
            if (r1) begin
                clip <= (ys > 48'sd32767) || (ys < -48'sd32768);
                y <= (ys > 48'sd32767) ? 16'sd32767 : (ys < -48'sd32768) ? -16'sd32768 : ys[15:0];
                xs2 <= xs1;
                absx2 <= xs1[15] ? -xs1 : xs1;
            end
            // 3. count, meters, output
            if (r2) begin
                samples <= samples + 1'b1;
                if (clip) clipped <= clipped + 1'b1;
                if (absy > peak_out) peak_out <= absy;
                if (absx2 > peak_in) peak_in <= absx2;
                if (!use_gen || capture != 32'd0) begin
                    if (out_ready) begin out_push <= 1'b1; out_word <= {y, xs2}; end
                    else lost <= lost + 1'b1;
                    if (use_gen) capture <= capture - 1'b1;
                end
            end
            if (bus_we && sel && idx == 10'd15) capture <= bus_wdata;
            if (bus_re && sel && idx == 10'd11) peak_in <= 16'd0;         // the meters start over when read
            if (bus_re && sel && idx == 10'd12) peak_out <= 16'd0;
        end
    end

    // ---- the output FIFO (to the ARM)
    wire [31:0] o_d;
    wire o_v;
    wire [9:0] o_level;
    wire o_pop = bus_re && sel && idx == 10'd5 && o_v;
    ardzy_axis_fifo #(.W(32), .AW(9)) u_out (.clk(clk), .rst(rst), .s_tdata(out_word), .s_tlast(1'b0),
        .s_tvalid(out_push), .s_tready(out_ready), .m_tdata(o_d), .m_tlast(), .m_tvalid(o_v),
        .m_tready(o_pop), .level(o_level));

    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx >= 10'd64 && idx <= 10'd127) bus_rdata <= {{14{coef[idx[5:0]][17]}}, coef[idx[5:0]]};
        else case (idx)
            10'd0: bus_rdata <= {30'd0, use_gen, 1'b0};
            10'd1: bus_rdata <= {7'd0, busy, 6'd0, o_level, 1'b0, in_level};
            10'd2: bus_rdata <= {25'd0, taps};
            10'd3: bus_rdata <= {26'd0, shift};
            10'd5: bus_rdata <= o_v ? o_d : 32'd0;
            10'd7: bus_rdata <= gfreq;
            10'd8: bus_rdata <= grate;
            10'd9: bus_rdata <= {16'd0, gamp};
            10'd10: bus_rdata <= {16'd0, gnoise};
            10'd11: bus_rdata <= {16'd0, peak_in};
            10'd12: bus_rdata <= {16'd0, peak_out};
            10'd13: bus_rdata <= samples;
            10'd14: bus_rdata <= clipped;
            10'd15: bus_rdata <= capture;
            10'd16: bus_rdata <= lost;
            10'd1023: bus_rdata <= 32'h46495231;          // "FIR1"
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign busy_led = busy;
endmodule
