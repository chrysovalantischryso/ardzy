// Ardzy FPGA library: ardzy_audio, I2S sound out and in, PDM microphone in.
//
// One 100 MHz clock makes everything: MCLK 12.5 MHz, BCLK 3.125 MHz (64 bits per frame), LRCLK and the
// sample rate 48828.125 Hz (100 MHz / 2048). DACs with their own PLL (PCM5102A, MAX98357A, UDA1334A)
// take this rate; play sound resampled to 48828 Hz (blocks.py has a helper).
// Samples are 16 bit, stereo: word = right << 16 | left. I2S format, 32-bit slots, MSB first.
// Registers (word index):
//   0 CTRL      [0] sound out on  [1] out source: 0 = buffer, 1 = tone generator
//               [3:2] in source: 0 = DIN pin, 1 = inside loop from the output, 2 = the DOUT pin read back,
//                     3 = PDM microphone   [4] in on   [5] PDM test (a modulated tone instead of the mic pin)
//   1 TX        write: put a sample in the out buffer (2048 places)
//   2 TX_LEVEL  (read) samples waiting in the out buffer
//   3 RX        read: take the oldest received sample (1024 places)
//   4 RX_LEVEL  (read) samples waiting in the in buffer
//   5 TONE_INC  tone frequency = TONE_INC * 48828.125 / 2^32
//   6 VOLUME    0..256 (256 = full)
//   7 UNDERFLOWS (read) frames with an empty out buffer
//   8 OVERFLOWS  (read) samples lost because the in buffer was full
//   9 LR_PERIOD (read) time between LRCLK falls at the pin, in 10 ns (should be 2048)
//  10 FS        (read) 48828
//  11 ID        "AUD0"
`timescale 1ns / 1ps
module ardzy_audio #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        mclk,
    output wire        bclk,
    output reg         lrclk = 1'b0,
    output reg         dout = 1'b0,
    input  wire        din,
    input  wire        dout_in,              // DOUT read back at the pad
    input  wire        lr_in,                // LRCLK read back at the pad
    output wire        pdm_clk,
    input  wire        pdm_dat
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    reg [5:0]  ctrl = 6'd0;
    reg [31:0] tone_inc = 32'd87960930, tphase = 32'd0;      // 1 kHz
    reg [8:0]  vol = 9'd128;
    reg [31:0] under = 32'd0, over = 32'd0;

    // frame counter: 2048 clocks per frame, 32 clocks per bit
    reg [10:0] fc = 11'd0;
    always @(posedge clk) fc <= fc + 1'b1;
    wire on = ctrl[0];
    assign mclk = on & fc[2];
    assign bclk = on & fc[4];
    assign pdm_clk = on & fc[4];
    wire bit_start = (fc[4:0] == 5'd0);          // BCLK falls: put the next bit out
    wire bit_mid = (fc[4:0] == 5'd16);           // BCLK rises: read the bit in
    wire [5:0] slot = fc[10:5];
    wire frame_start = (fc == 11'd0);
    wire frame_end = (fc == 11'd2047);

    // out buffer (block RAM)
    (* ram_style = "block" *) reg [31:0] txb [0:2047];
    reg [11:0] tw = 12'd0, tr = 12'd0;
    wire [11:0] tx_n = tw - tr;
    reg [31:0] txq = 32'd0;
    always @(posedge clk) begin
        if (bus_we && sel && idx == 10'd1 && tx_n != 12'd2048) txb[tw[10:0]] <= bus_wdata;
        txq <= txb[tr[10:0]];
    end

    // tone generator (one step per frame)
    wire signed [15:0] sine;
    ardzy_sine_rom u_rom (.clk(clk), .a(tphase[31:22]), .q(sine));

    // the frame being sent
    reg signed [15:0] l_out = 16'sd0, r_out = 16'sd0;
    reg signed [24:0] ml, mr;
    always @(posedge clk) begin
        if (frame_start) begin
            tphase <= tphase + tone_inc;
            if (ctrl[1]) begin
                ml = sine * $signed({1'b0, vol}); mr = ml;
            end else if (tx_n != 0 && on) begin
                ml = $signed(txq[15:0]) * $signed({1'b0, vol}); mr = $signed(txq[31:16]) * $signed({1'b0, vol});
            end else begin
                ml = 25'sd0; mr = 25'sd0;                    // empty buffer: silence (counted below)
            end
            l_out <= ml[23:8]; r_out <= mr[23:8];
        end
    end

    // I2S out: the bit for slot s (s = 0 .. 63; 0..31 left, 32..63 right; MSB one bit after LRCLK changes)
    wire [4:0] pos = slot[4:0];
    wire [15:0] cur = slot[5] ? r_out : l_out;
    always @(posedge clk) if (bit_start) begin
        lrclk <= on & slot[5];
        dout <= on && (pos >= 5'd1) && (pos <= 5'd16) && cur[5'd16 - pos];
    end

    // I2S in
    wire rx_src_bit = (ctrl[3:2] == 2'd1) ? dout : (ctrl[3:2] == 2'd2) ? dout_in : din;
    reg [15:0] sh = 16'd0, l_in = 16'd0, r_in = 16'd0;
    always @(posedge clk) if (bit_mid) begin
        if (pos >= 5'd1 && pos <= 5'd16) sh <= {sh[14:0], rx_src_bit};
        if (pos == 5'd17) begin if (slot[5]) r_in <= sh; else l_in <= sh; end
    end

    // PDM microphone: 3rd order CIC, 64 x down (3.125 MHz -> 48.8 kHz)
    reg [15:0] pm_acc = 16'd0;
    reg pm_bit = 1'b0;
    wire [15:0] tone_u = sine ^ 16'h8000;
    reg [2:0] pd = 3'd0;
    always @(posedge clk) pd <= {pd[1:0], pdm_dat};
    reg signed [21:0] i1 = 0, i2 = 0, i3 = 0, d3 = 0, c1 = 0, d1 = 0, c2 = 0, d2 = 0, c3 = 0;
    always @(posedge clk) begin
        if (bit_mid) begin
            {pm_bit, pm_acc} <= {1'b0, pm_acc} + {1'b0, tone_u};      // test modulator (1st order)
            i1 <= i1 + ((ctrl[5] ? pm_bit : pd[2]) ? 22'sd1 : -22'sd1);
            i2 <= i2 + i1;
            i3 <= i3 + i2;
        end
        if (frame_end) begin
            c1 <= i3 - d3; d3 <= i3;
            c2 <= c1 - d1; d1 <= c1;
            c3 <= c2 - d2; d2 <= c2;
        end
    end
    wire signed [21:0] pdm_s = c3 >>> 3;                                  // +-2^18 -> 16 bit
    wire [15:0] pdm16 = (pdm_s > 22'sd32767) ? 16'h7FFF : (pdm_s < -22'sd32768 ? 16'h8000 : pdm_s[15:0]);

    // in buffer (block RAM)
    (* ram_style = "block" *) reg [31:0] rxb [0:1023];
    reg [10:0] rw = 11'd0, rr = 11'd0;
    wire [10:0] rx_n = rw - rr;
    reg [31:0] rxq = 32'd0;
    wire push = ctrl[4] && on && frame_end;
    wire [31:0] rx_word = (ctrl[3:2] == 2'd3) ? {pdm16, pdm16} : {r_in, l_in};
    always @(posedge clk) begin
        if (push && rx_n != 11'd1024) rxb[rw[9:0]] <= rx_word;
        rxq <= rxb[rr[9:0]];
    end

    // LRCLK at the pin
    reg [2:0] lr3 = 3'd0;
    reg [31:0] lcnt = 32'd0, lper = 32'd0;
    always @(posedge clk) begin
        lr3 <= {lr3[1:0], lr_in};
        lcnt <= lcnt + 1'b1;
        if (lr3[2] && !lr3[1]) begin lper <= lcnt; lcnt <= 32'd1; end
    end

    always @(posedge clk) begin
        if (frame_start && on && !ctrl[1] && tx_n != 0) tr <= tr + 1'b1;     // the buffer waits while sound is off
        if (frame_start && on && !ctrl[1] && tx_n == 0) under <= under + 1'b1;
        if (push) begin if (rx_n != 11'd1024) rw <= rw + 1'b1; else over <= over + 1'b1; end
        if (!rstn) begin ctrl <= 6'd0; vol <= 9'd128; end
        else if (bus_we && sel) case (idx)
            10'd0: ctrl <= bus_wdata[5:0];
            10'd1: if (tx_n != 12'd2048) tw <= tw + 1'b1;
            10'd5: tone_inc <= bus_wdata;
            10'd6: vol <= (bus_wdata[8:0] > 9'd256) ? 9'd256 : bus_wdata[8:0];
            10'd7: under <= 32'd0;
            10'd8: over <= 32'd0;
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {26'd0, ctrl};
                10'd2: bus_rdata <= {20'd0, tx_n};
                10'd3: if (rx_n != 0) begin bus_rdata <= rxq; rr <= rr + 1'b1; end else bus_rdata <= 32'd0;
                10'd4: bus_rdata <= {21'd0, rx_n};
                10'd5: bus_rdata <= tone_inc;
                10'd6: bus_rdata <= {23'd0, vol};
                10'd7: bus_rdata <= under;
                10'd8: bus_rdata <= over;
                10'd9: bus_rdata <= lper;
                10'd10: bus_rdata <= 32'd48828;
                10'd11: bus_rdata <= 32'h41554430;         // "AUD0"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
