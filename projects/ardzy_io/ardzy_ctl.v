// ardzy_ctl: AXI4-Lite peripheral of the Ardzy "pin control" design, version 2 ("ARZ2").
// It sits between the AXI GPIO and the 49 FPGA pins and adds small instruments:
//   - pin function switch: every pin can be GPIO (AXI GPIO), one of 8 PWM outputs or the UART TX
//   - 8 PWM generators (also square-wave clock outputs up to 50 MHz, servo pulses)
//   - 4 measuring channels (frequency, duty cycle, period) on any of the 56 sampled signals
//   - a UART on any two pins (TX through the pin function switch, RX from any pin)
//   - a 4096-sample logic analyzer over all 56 signals (49 pins + 6 fan speed inputs + fan PWM)
//   - the fan controller of version 1 (same registers, same offsets) and the FCLK0 cycle counter
//   - the chip's unique 57-bit Device DNA
// The 4 board-ID straps (pins 41..44) are forced to inputs in hardware.
//
// Pin index (0..48): 0..31 = j1[0]..j8[3] (AXI GPIO channel 1), 32..48 = AXI GPIO channel 2:
//   32..35 j9[0..3], 36..39 leds[0..3], 40 tp1, 41..44 board_id[0..3], 45 i2c1_scl, 46 i2c1_sda,
//   47 i2c2_scl, 48 i2c2_sda. Sample bits 49..54 = fan_tach[0..5], 55 = fan_pwm.
//
// Registers (byte offsets, 32 bit). Offsets 0x00..0x30 are the same as version 1.
//   0x00 ID        0x41525A32 ("ARZ2")
//   0x04 CTRL      fan: bit0 = PWM on (off = held high, full speed), bit1 = invert
//   0x08 PERIOD    fan PWM period in clock cycles            0x0C HIGH  fan PWM high time
//   0x10..0x24     TACH0..5: rising edges in the last gate window
//   0x28 GATE      gate window in cycles (fan speed + measuring channels), reset 100,000,000
//   0x2C WINDOWS   completed gate windows                     0x30 CYCLES free-running counter
//   0x34 DNA_LO    Device DNA bits 31:0                       0x38 DNA_HI bit31 = valid, 24:0 = DNA 56:32
//   0x3C CAPS      15:0 analyzer depth, 23:16 pins, 27:24 PWM channels, 31:28 measuring channels
//   0x40..0x58     FUNC0..6: 4 bits per pin (pin 8n+k at bits 4k+3:4k). 0 = GPIO, 1..8 = PWM0..7, 9 = UART TX
//   0x60 + 8n      PWMn PERIOD (cycles, min 2)                0x64 + 8n PWMn HIGH (cycles)
//   0xA0 + 16n     MEASn SEL (signal 0..55)
//   0xA4 + 16n     MEASn COUNT  rising edges in the last gate window
//   0xA8 + 16n     MEASn HIGHT  cycles the signal was 1 in the last gate window
//   0xAC + 16n     MEASn PERIOD cycles between the last two rising edges
//   0xE0 UART_CTRL 15:0 cycles per bit, 21:16 RX signal, bit31 = enable
//   0xE4 UART_TX   write: send a byte. read: free places in the send queue (of 64)
//   0xE8 UART_RX   read: bit8 = valid, 7:0 = byte (taken out of the queue)
//   0xEC UART_STAT 10:0 bytes waiting, bit16 = overflow, bit17 = frame error (write: clear)
//   0x100 LA_CTRL  write: bit0 start, bit1 stop, bit2 force trigger. read: bit0 running, bit1 triggered, bit2 done
//   0x104 LA_DIV   sample every DIV+1 cycles                  0x108 LA_PRE samples kept before the trigger
//   0x10C/0x110    LA_MASK lo/hi   0x114/0x118 LA_VAL lo/hi  trigger when (sample & MASK) == VAL
//   0x11C LA_MODE  bit0 = edge (only the moment the pattern starts to match)
//   0x120 LA_TIDX  buffer index of the trigger sample         0x124 LA_WIDX write index
//   0x128/0x12C    LIVE lo/hi: all 56 signals now
//   0x8000 + 8i    analyzer sample i, bits 31:0 (+4: bits 63:32)
`timescale 1ns / 1ps
module ardzy_ctl #(parameter LA_AW = 12, parameter DNA_CLK_MODE = 1) (
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    input  wire [15:0] s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [15:0] s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,
    // AXI GPIO, both channels
    input  wire [31:0] gpio1_o,
    input  wire [31:0] gpio1_t,
    output wire [31:0] gpio1_i,
    input  wire [16:0] gpio2_o,
    input  wire [16:0] gpio2_t,
    output wire [16:0] gpio2_i,
    // the 49 FPGA pins (tri-state buffers inside)
    inout  wire [48:0] pins,
    output wire        fan_pwm,
    input  wire [5:0]  fan_tach
);
    localparam [31:0] ID = 32'h41525A32;
    localparam NP = 49;
    localparam DEPTH = 1 << LA_AW;
    localparam [15:0] DEPTH16 = DEPTH;
    wire clk = s_axi_aclk;
    wire rst = ~s_axi_aresetn;
    integer ip, it, iw;            // loop counters, one per always block
    genvar g;

    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;

    // ------------------------------------------------------------ registers
    reg [1:0]  fan_ctrl;
    reg [31:0] fan_period, fan_high, gate;
    reg [31:0] func [0:6];
    reg [31:0] pwm_per [0:7];
    reg [31:0] pwm_hi  [0:7];
    reg [5:0]  m_sel   [0:3];
    reg [15:0] u_div;
    reg [5:0]  u_rxsel;
    reg        u_en;
    reg [31:0] la_div;
    reg [LA_AW-1:0] la_pre;
    reg [63:0] la_mask, la_val;
    reg        la_edge;

    // ------------------------------------------------------------ pins: buffers, synchronizers
    wire [NP-1:0] pin_o, pin_t, pin_i;
    generate for (g = 0; g < NP; g = g + 1) begin : io
        IOBUF u_buf (.IO(pins[g]), .I(pin_o[g]), .T(pin_t[g]), .O(pin_i[g]));
    end endgenerate

    reg [NP-1:0] pin_s1, pin_s2;
    reg [5:0]    tach_s1, tach_s2, tach_s3;
    always @(posedge clk) begin
        pin_s1 <= pin_i;  pin_s2 <= pin_s1;
        tach_s1 <= fan_tach; tach_s2 <= tach_s1; tach_s3 <= tach_s2;
    end
    assign gpio1_i = pin_s2[31:0];
    assign gpio2_i = pin_s2[48:32];
    wire [63:0] smp = {8'd0, fan_pwm, tach_s2, pin_s2};

    // ------------------------------------------------------------ PWM generators
    reg [31:0] pwm_cnt [0:7];
    reg [7:0]  pwm_q;
    always @(posedge clk) begin
        for (ip = 0; ip < 8; ip = ip + 1) begin
            if (rst || pwm_cnt[ip] >= pwm_per[ip] - 1) pwm_cnt[ip] <= 32'd0;
            else                                     pwm_cnt[ip] <= pwm_cnt[ip] + 1'b1;
            pwm_q[ip] <= (pwm_cnt[ip] < pwm_hi[ip]);
        end
    end

    // ------------------------------------------------------------ UART transmitter
    wire [15:0] u_bit = (u_div < 16'd4) ? 16'd4 : u_div;    // cycles per bit
    reg [7:0]  txf [0:63];
    reg [6:0]  tx_wp, tx_rp;
    reg [9:0]  tx_sh;
    reg [3:0]  tx_bits;
    reg [15:0] tx_tmr;
    reg        uart_tx;
    reg        tx_push;
    reg [7:0]  tx_byte;
    wire [6:0] tx_used = tx_wp - tx_rp;
    wire       tx_we = !rst && tx_push && tx_used != 7'd64;
    always @(posedge clk) if (tx_we) txf[tx_wp[5:0]] <= tx_byte;
    always @(posedge clk) begin
        if (rst) begin
            tx_wp <= 7'd0; tx_rp <= 7'd0; tx_bits <= 4'd0; tx_tmr <= 16'd0; uart_tx <= 1'b1;
        end else begin
            if (tx_we) tx_wp <= tx_wp + 1'b1;
            if (tx_tmr != 16'd0)                     // every bit, the stop bit too, lasts u_bit cycles
                tx_tmr <= tx_tmr - 1'b1;
            else if (tx_bits != 4'd0) begin
                uart_tx <= tx_sh[0];
                tx_sh <= {1'b1, tx_sh[9:1]};
                tx_tmr <= u_bit - 1'b1;
                tx_bits <= tx_bits - 1'b1;
            end else if (u_en && tx_wp != tx_rp) begin
                tx_sh <= {1'b1, txf[tx_rp[5:0]], 1'b0};
                tx_rp <= tx_rp + 1'b1;
                tx_bits <= 4'd10;
            end else
                uart_tx <= 1'b1;
        end
    end

    // ------------------------------------------------------------ UART receiver
    reg [7:0]  rxf [0:1023];
    reg [10:0] rx_wp, rx_rp;
    reg [1:0]  rx_st;
    reg [15:0] rx_tmr;
    reg [2:0]  rx_n;
    reg [7:0]  rx_sh;
    reg        rx_ovf, rx_ferr;
    reg        rx_pop, rx_clr;
    reg [7:0]  rx_q;
    wire       rx_in = smp[u_rxsel];
    wire [10:0] rx_used = rx_wp - rx_rp;
    wire       rx_we = !rst && rx_st == 2'd3 && rx_tmr == 16'd0 && rx_in && rx_used != 11'd1024;
    always @(posedge clk) if (rx_we) rxf[rx_wp[9:0]] <= rx_sh;
    always @(posedge clk) rx_q <= rxf[rx_rp[9:0]];
    always @(posedge clk) begin
        if (rst) begin
            rx_wp <= 11'd0; rx_rp <= 11'd0; rx_st <= 2'd0; rx_ovf <= 1'b0; rx_ferr <= 1'b0;
        end else begin
            if (rx_pop && rx_used != 11'd0) rx_rp <= rx_rp + 1'b1;
            if (rx_clr) begin rx_ovf <= 1'b0; rx_ferr <= 1'b0; end
            case (rx_st)
                2'd0: if (u_en && !rx_in) begin rx_st <= 2'd1; rx_tmr <= {1'b0, u_bit[15:1]}; end
                2'd1: if (rx_tmr != 0) rx_tmr <= rx_tmr - 1'b1;
                      else if (!rx_in) begin rx_st <= 2'd2; rx_tmr <= u_bit - 1'b1; rx_n <= 3'd0; end
                      else rx_st <= 2'd0;                                   // glitch, not a start bit
                2'd2: if (rx_tmr != 0) rx_tmr <= rx_tmr - 1'b1;
                      else begin
                          rx_sh <= {rx_in, rx_sh[7:1]};
                          rx_tmr <= u_bit - 1'b1;
                          rx_n <= rx_n + 1'b1;
                          if (rx_n == 3'd7) rx_st <= 2'd3;
                      end
                2'd3: if (rx_tmr != 0) rx_tmr <= rx_tmr - 1'b1;
                      else begin
                          rx_st <= 2'd0;
                          if (!rx_in) rx_ferr <= 1'b1;
                          else if (rx_used == 11'd1024) rx_ovf <= 1'b1;
                          else rx_wp <= rx_wp + 1'b1;
                      end
            endcase
        end
    end

    // ------------------------------------------------------------ pin function switch
    wire [223:0] func_flat = {func[6], func[5], func[4], func[3], func[2], func[1], func[0]};
    generate for (g = 0; g < NP; g = g + 1) begin : mux
        wire [3:0] fn  = func_flat[4 * g +: 4];
        wire       id  = (g >= 41 && g <= 44);
        wire       ins = !id && fn >= 4'd1 && fn <= 4'd9;
        wire       iv  = (fn == 4'd9) ? uart_tx : pwm_q[fn[2:0] - 3'd1];
        wire       go, gt;
        if (g < 32) begin : ch1
            assign go = gpio1_o[g];
            assign gt = gpio1_t[g];
        end else begin : ch2
            assign go = gpio2_o[g - 32];
            assign gt = gpio2_t[g - 32];
        end
        assign pin_o[g] = ins ? iv : go;
        assign pin_t[g] = id ? 1'b1 : (ins ? 1'b0 : gt);
    end endgenerate

    // ------------------------------------------------------------ fan PWM, gate, speed counters
    reg [31:0] cycles, windows, gate_cnt, fpwm_cnt;
    reg [31:0] tach_cnt [0:5];
    reg [31:0] tach_val [0:5];
    always @(posedge clk) begin
        if (rst || fpwm_cnt >= fan_period - 1) fpwm_cnt <= 32'd0;
        else                                   fpwm_cnt <= fpwm_cnt + 1'b1;
    end
    reg fan_q;
    always @(posedge clk) fan_q <= (fan_ctrl[0] ? (fpwm_cnt < fan_high) : 1'b1) ^ fan_ctrl[1];
    assign fan_pwm = fan_q;

    wire gate_end = (gate_cnt >= gate - 1);
    always @(posedge clk) begin
        cycles <= rst ? 32'd0 : cycles + 1'b1;
        if (rst) begin
            gate_cnt <= 32'd0; windows <= 32'd0;
            for (it = 0; it < 6; it = it + 1) begin tach_cnt[it] <= 32'd0; tach_val[it] <= 32'd0; end
        end else begin
            gate_cnt <= gate_end ? 32'd0 : gate_cnt + 1'b1;
            if (gate_end) windows <= windows + 1'b1;
            for (it = 0; it < 6; it = it + 1) begin
                if (gate_end) begin
                    tach_val[it] <= tach_cnt[it] + (tach_s2[it] & ~tach_s3[it]);
                    tach_cnt[it] <= 32'd0;
                end else if (tach_s2[it] & ~tach_s3[it])
                    tach_cnt[it] <= tach_cnt[it] + 1'b1;
            end
        end
    end

    // ------------------------------------------------------------ measuring channels
    wire [31:0] m_count [0:3], m_high [0:3], m_period [0:3];
    generate for (g = 0; g < 4; g = g + 1) begin : meas
        wire       sig  = smp[m_sel[g]];
        reg        prev;
        wire       rise = sig & ~prev;
        reg [31:0] cnt, hcnt, since, count, high, period;
        always @(posedge clk) begin
            prev <= sig;
            if (rst) begin
                cnt <= 0; hcnt <= 0; since <= 32'hFFFFFFFF; count <= 0; high <= 0; period <= 0;
            end else begin
                if (gate_end) begin
                    count <= cnt + rise;
                    high  <= hcnt + sig;
                    cnt <= 0; hcnt <= 0;
                end else begin
                    if (rise) cnt  <= cnt + 1'b1;
                    if (sig)  hcnt <= hcnt + 1'b1;
                end
                if (rise) begin
                    period <= since;
                    since  <= 32'd1;
                end else if (since != 32'hFFFFFFFF)
                    since <= since + 1'b1;
            end
        end
        assign m_count[g] = count;
        assign m_high[g] = high;
        assign m_period[g] = period;
    end endgenerate

    // ------------------------------------------------------------ logic analyzer
    reg [63:0] la_mem [0:DEPTH-1];
    reg [LA_AW-1:0] la_wa, la_tidx;
    reg        la_run, la_trig, la_done, la_force, la_prevm;
    reg [31:0] la_divcnt;
    reg [LA_AW:0] la_cnt, la_post;
    reg        la_start, la_stop, la_frc;
    wire la_tick  = la_run && (la_divcnt == 32'd0);
    wire la_match = ((smp ^ la_val) & la_mask) == 64'd0;
    wire la_hit   = (la_mask == 64'd0) || (la_match && (!la_edge || !la_prevm));
    wire la_we    = !rst && !la_start && !la_stop && la_tick && !(la_trig && la_post == 0);
    always @(posedge clk) if (la_we) la_mem[la_wa] <= smp;
    always @(posedge clk) begin
        if (rst) begin
            la_run <= 1'b0; la_trig <= 1'b0; la_done <= 1'b0; la_force <= 1'b0; la_wa <= 0; la_tidx <= 0;
            la_divcnt <= 32'd0; la_cnt <= 0; la_post <= 0; la_prevm <= 1'b1;
        end else if (la_start) begin
            la_run <= 1'b1; la_trig <= 1'b0; la_done <= 1'b0; la_force <= 1'b0;
            la_divcnt <= 32'd0; la_cnt <= 0; la_prevm <= 1'b1;
        end else if (la_stop) begin
            la_run <= 1'b0;
        end else begin
            if (la_frc) la_force <= 1'b1;
            if (la_run) la_divcnt <= (la_divcnt == 32'd0) ? la_div : la_divcnt - 1'b1;
            if (la_tick) begin
                if (la_trig && la_post == 0) begin
                    la_run <= 1'b0; la_done <= 1'b1;
                end else begin
                    la_wa <= la_wa + 1'b1;
                    if (la_trig)
                        la_post <= la_post - 1'b1;
                    else begin
                        if (la_cnt != DEPTH) la_cnt <= la_cnt + 1'b1;
                        la_prevm <= la_match;
                        if (la_cnt >= la_pre && (la_hit || la_force)) begin
                            la_trig <= 1'b1; la_tidx <= la_wa;
                            la_post <= DEPTH - 1 - la_pre;
                        end
                    end
                end
            end
        end
    end

    // ------------------------------------------------------------ Device DNA (read once after reset)
    // DNA_CLK_MODE 0: the DNA block runs on FCLK0 with one-clock READ/SHIFT pulses (any toolchain).
    // DNA_CLK_MODE 1: a slow DNA clock (FCLK0 / 8) made by a register (the first Vivado build).
    reg [2:0]  dna_div = 3'd0;
    reg        dna_clk = 1'b0;
    reg        dna_read, dna_shift, dna_ok;
    reg [5:0]  dna_n;
    reg [56:0] dna;
    wire       dna_dout;
    generate if (DNA_CLK_MODE == 1) begin : dna_slow
        DNA_PORT u_dna (.DOUT(dna_dout), .CLK(dna_clk), .DIN(1'b0), .READ(dna_read), .SHIFT(dna_shift));
        always @(posedge clk) begin
            dna_div <= dna_div + 1'b1;
            dna_clk <= dna_div[2];
            if (rst) begin
                dna_read <= 1'b0; dna_shift <= 1'b0; dna_ok <= 1'b0; dna_n <= 6'd0; dna <= 57'd0;
            end else if (dna_div == 3'd1 && !dna_ok) begin    // the DNA clock is low and rises 4 cycles later
                if (dna_n == 6'd0) begin
                    dna_read <= 1'b1; dna_n <= 6'd1;
                end else begin
                    dna_read <= 1'b0;
                    dna <= {dna[55:0], dna_dout};
                    if (dna_n == 6'd57) begin dna_shift <= 1'b0; dna_ok <= 1'b1; end
                    else begin dna_shift <= 1'b1; dna_n <= dna_n + 1'b1; end
                end
            end
        end
    end else begin : dna_direct
        DNA_PORT u_dna (.DOUT(dna_dout), .CLK(clk), .DIN(1'b0), .READ(dna_read), .SHIFT(dna_shift));
        always @(posedge clk) begin
            dna_div <= dna_div + 1'b1;
            dna_read <= 1'b0; dna_shift <= 1'b0;                 // one-clock pulses
            if (rst) begin
                dna_ok <= 1'b0; dna_n <= 6'd0; dna <= 57'd0;
            end else if (dna_div[1:0] == 2'd0 && !dna_ok) begin  // one step every 4 clocks
                if (dna_n == 6'd0) begin
                    dna_read <= 1'b1; dna_n <= 6'd1;
                end else begin
                    dna <= {dna[55:0], dna_dout};
                    if (dna_n == 6'd57) dna_ok <= 1'b1;
                    else begin dna_shift <= 1'b1; dna_n <= dna_n + 1'b1; end
                end
            end
        end
    end endgenerate

    // ------------------------------------------------------------ AXI write channel
    // (the handshake pattern of the Xilinx AXI4-Lite template, as in version 1)
    reg aw_en;
    wire w_hs = s_axi_awready && s_axi_awvalid && s_axi_wready && s_axi_wvalid;
    wire [9:0] wa = s_axi_awaddr[11:2];
    wire [31:0] wd = s_axi_wdata;
    always @(posedge clk) begin
        tx_push <= 1'b0; rx_clr <= 1'b0; la_start <= 1'b0; la_stop <= 1'b0; la_frc <= 1'b0;
        if (rst) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0; aw_en <= 1'b1;
            fan_ctrl <= 2'b00; fan_period <= 32'd4000; fan_high <= 32'd4000; gate <= 32'd100_000_000;
            for (iw = 0; iw < 7; iw = iw + 1) func[iw] <= 32'd0;
            for (iw = 0; iw < 8; iw = iw + 1) begin pwm_per[iw] <= 32'd100_000; pwm_hi[iw] <= 32'd50_000; end
            for (iw = 0; iw < 4; iw = iw + 1) m_sel[iw] <= iw[5:0];
            u_div <= 16'd868; u_rxsel <= 6'd2; u_en <= 1'b0;
            la_div <= 32'd99; la_pre <= DEPTH / 4; la_mask <= 64'd0; la_val <= 64'd0; la_edge <= 1'b1;
        end else begin
            if (!s_axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
                s_axi_awready <= 1'b1; s_axi_wready <= 1'b1; aw_en <= 1'b0;
            end else begin
                s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            end
            if (w_hs && !s_axi_awaddr[15]) begin
                case (wa)
                    10'h001: fan_ctrl   <= wd[1:0];
                    10'h002: fan_period <= (wd < 32'd2) ? 32'd2 : wd;
                    10'h003: fan_high   <= wd;
                    10'h00A: gate       <= (wd < 32'd1000) ? 32'd1000 : wd;
                    10'h038: begin u_div <= wd[15:0]; u_rxsel <= (wd[21:16] > 6'd55) ? 6'd55 : wd[21:16]; u_en <= wd[31]; end
                    10'h039: begin tx_byte <= wd[7:0]; tx_push <= 1'b1; end
                    10'h03B: rx_clr <= 1'b1;
                    10'h040: begin la_start <= wd[0]; la_stop <= wd[1]; la_frc <= wd[2]; end
                    10'h041: la_div  <= wd;
                    10'h042: la_pre  <= wd[LA_AW-1:0];
                    10'h043: la_mask[31:0]  <= wd;
                    10'h044: la_mask[63:32] <= wd;
                    10'h045: la_val[31:0]   <= wd;
                    10'h046: la_val[63:32]  <= wd;
                    10'h047: la_edge <= wd[0];
                    default: begin
                        if (wa >= 10'h010 && wa <= 10'h016) func[wa - 10'h010] <= wd;
                        if (wa >= 10'h018 && wa <= 10'h027) begin
                            if (wa[0]) pwm_hi[(wa - 10'h018) >> 1] <= wd;
                            else       pwm_per[(wa - 10'h018) >> 1] <= (wd < 32'd2) ? 32'd2 : wd;
                        end
                        if (wa >= 10'h028 && wa <= 10'h037 && wa[1:0] == 2'b00)
                            m_sel[(wa - 10'h028) >> 2] <= (wd[5:0] > 6'd55) ? 6'd55 : wd[5:0];
                    end
                endcase
            end
            if (w_hs && !s_axi_bvalid)
                s_axi_bvalid <= 1'b1;
            else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0; aw_en <= 1'b1;
            end
        end
    end

    // ------------------------------------------------------------ AXI read channel
    // address taken -> one cycle for the block RAMs -> data out (RVALID) -> wait for RREADY
    reg [15:0] ra;
    reg [1:0]  rd_st;
    reg [63:0] la_q;
    reg        rx_has;
    always @(posedge clk) la_q <= la_mem[ra[LA_AW+2:3]];
    wire [9:0] rw = ra[11:2];
    reg  [31:0] rv;
    always @(*) begin
        rv = 32'd0;
        case (rw)
            10'h000: rv = ID;
            10'h001: rv = {30'd0, fan_ctrl};
            10'h002: rv = fan_period;
            10'h003: rv = fan_high;
            10'h004: rv = tach_val[0];
            10'h005: rv = tach_val[1];
            10'h006: rv = tach_val[2];
            10'h007: rv = tach_val[3];
            10'h008: rv = tach_val[4];
            10'h009: rv = tach_val[5];
            10'h00A: rv = gate;
            10'h00B: rv = windows;
            10'h00C: rv = cycles;
            10'h00D: rv = dna[31:0];
            10'h00E: rv = {dna_ok, 6'd0, dna[56:32]};
            10'h00F: rv = {4'd4, 4'd8, 8'd49, DEPTH16};
            10'h038: rv = {u_en, 9'd0, u_rxsel, u_div};
            10'h039: rv = {25'd0, 7'd64 - tx_used};
            10'h03B: rv = {14'd0, rx_ferr, rx_ovf, 5'd0, rx_used};
            10'h040: rv = {29'd0, la_done, la_trig, la_run};
            10'h041: rv = la_div;
            10'h042: rv = la_pre;
            10'h043: rv = la_mask[31:0];
            10'h044: rv = la_mask[63:32];
            10'h045: rv = la_val[31:0];
            10'h046: rv = la_val[63:32];
            10'h047: rv = {31'd0, la_edge};
            10'h048: rv = la_tidx;
            10'h049: rv = la_wa;
            10'h04A: rv = smp[31:0];
            10'h04B: rv = smp[63:32];
            default: begin
                if (rw >= 10'h010 && rw <= 10'h016) rv = func[rw - 10'h010];
                if (rw >= 10'h018 && rw <= 10'h027) rv = rw[0] ? pwm_hi[(rw - 10'h018) >> 1] : pwm_per[(rw - 10'h018) >> 1];
                if (rw >= 10'h028 && rw <= 10'h037)
                    case (rw[1:0])
                        2'd0: rv = m_sel[(rw - 10'h028) >> 2];
                        2'd1: rv = m_count[(rw - 10'h028) >> 2];
                        2'd2: rv = m_high[(rw - 10'h028) >> 2];
                        2'd3: rv = m_period[(rw - 10'h028) >> 2];
                    endcase
            end
        endcase
    end
    always @(posedge clk) begin
        rx_pop <= 1'b0;
        if (rst) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rdata <= 32'd0; ra <= 16'd0; rd_st <= 2'd0;
        end else case (rd_st)
            2'd0: begin
                if (s_axi_arready && s_axi_arvalid) begin
                    s_axi_arready <= 1'b0; ra <= s_axi_araddr; rd_st <= 2'd1;
                end else
                    s_axi_arready <= 1'b1;
            end
            2'd1: begin                                   // block RAMs read 'ra' during this cycle
                rx_has <= (rx_used != 11'd0);
                rd_st <= 2'd2;
            end
            2'd2: begin
                if (ra[15])
                    s_axi_rdata <= ra[2] ? la_q[63:32] : la_q[31:0];
                else if (rw == 10'h03A) begin
                    s_axi_rdata <= {23'd0, rx_has, rx_has ? rx_q : 8'd0};
                    rx_pop <= rx_has;
                end else
                    s_axi_rdata <= rv;
                s_axi_rvalid <= 1'b1;
                rd_st <= 2'd3;
            end
            2'd3: if (s_axi_rready) begin
                s_axi_rvalid <= 1'b0; rd_st <= 2'd0;
            end
        endcase
    end
endmodule