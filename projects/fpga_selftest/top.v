`timescale 1ns / 1ps
// fpga_selftest: checks which parts of the XC7Z010 work with Ardzy's built-in (open) toolchain,
// on the real chip. The design measures itself; main.py reads the results (status registers).
//
//   block RAM    4096 x 32 (4 x RAMB36) written and read back by a self-test, then by the ARM
//   DSP48E1      25 x 18 signed multiply of two ARM registers
//   MMCM         100 MHz -> 25 / 100 / 125 / 200 MHz          PLL   100 MHz -> 50 / 133.3 MHz
//   BUFGCTRL     glitch-free switch between 25 MHz (MMCM) and 50 MHz (PLL), chosen by the ARM
//   I/O          12.5 MHz from a fabric flip-flop on LED pin 0, read back at the pad
//   ODDR         25 MHz clock forwarded to LED pin 1, read back at the pad
//   (OSERDESE2 is left out: with the open toolchain its pin never toggles yet; use Vivado for it)
//   SRL, LUT RAM shift register (SRLC32E) and distributed RAM self-tests
// Every clock and pad signal is counted in its own clock domain and measured against the 100 MHz
// system clock over 0.1 s gates (status value x 10 = Hz).
//
// ARM registers (ardzy_soc):  ctrl0 0x4120_0000: [11:0] block RAM address, [16] clock switch,
//                             [31] write strobe (0 -> 1 writes ctrl1 to the address)
//                             ctrl1 0x4120_0004: data to write      ctrl2/ctrl3: DSP inputs A (25 bit), B (18 bit)
//                             status 0x4120_0080 + 4n: see the list at the end
module top (
    inout  wire [1:0] lio,      // LED 0, 1: serializer and DDR outputs, read back at the pad
    output wire [1:0] lout      // LED 2, 3: slow blinks from the MMCM and the PLL
);
    wire clk, rstn;
    wire [32*4-1:0]  ctrl;
    wire [32*16-1:0] status;
    ardzy_soc #(.N_CTRL(4), .N_STAT(16)) u_soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));
    wire [31:0] ctrl0 = ctrl[31:0], ctrl1 = ctrl[63:32];

    // ---------------------------------------------------------------- MMCM
    wire m_fb, m_fb_b, m_25, m_100, m_125, m_200, m_locked;
    MMCME2_BASE #(
        .CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1),
        .CLKOUT0_DIVIDE_F(40.0), .CLKOUT1_DIVIDE(10), .CLKOUT2_DIVIDE(8), .CLKOUT3_DIVIDE(5)
    ) u_mmcm (
        .CLKIN1(clk), .CLKFBIN(m_fb_b), .CLKFBOUT(m_fb), .RST(~rstn), .PWRDWN(1'b0),
        .CLKOUT0(m_25), .CLKOUT1(m_100), .CLKOUT2(m_125), .CLKOUT3(m_200), .LOCKED(m_locked));
    wire c25, c100, c125, c200;
    BUFG u_bfb  (.I(m_fb),  .O(m_fb_b));
    BUFG u_b25  (.I(m_25),  .O(c25));
    BUFG u_b100 (.I(m_100), .O(c100));
    BUFG u_b125 (.I(m_125), .O(c125));
    BUFG u_b200 (.I(m_200), .O(c200));

    // ---------------------------------------------------------------- PLL
    wire p_fb, p_50, p_133, p_locked;
    PLLE2_BASE #(
        .CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT(12), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE(24), .CLKOUT1_DIVIDE(9)
    ) u_pll (
        .CLKIN1(clk), .CLKFBIN(p_fb), .CLKFBOUT(p_fb), .RST(~rstn), .PWRDWN(1'b0),
        .CLKOUT0(p_50), .CLKOUT1(p_133), .LOCKED(p_locked));
    wire c50, c133;
    BUFG u_b50  (.I(p_50),  .O(c50));
    BUFG u_b133 (.I(p_133), .O(c133));

    // ---------------------------------------------------------------- clock switch (BUFGCTRL)
    reg sel = 1'b0;
    always @(posedge clk) sel <= ctrl0[16];
    wire cmux;
    BUFGCTRL #(.INIT_OUT(0), .PRESELECT_I0("TRUE"), .PRESELECT_I1("FALSE")) u_mux (
        .I0(c25), .I1(c50), .S0(~sel), .S1(sel), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(cmux));

    // ---------------------------------------------------------------- fabric output on LED 0
    // (OSERDESE2 does not work with the open toolchain yet: tested on this chip, the pin never toggles)
    reg tog = 1'b0;
    always @(posedge c25) tog <= ~tog;                   // 12.5 MHz from a flip-flop in the fabric
    wire pad0;
    IOBUF u_io0 (.I(tog), .T(1'b0), .O(pad0), .IO(lio[0]));

    // ---------------------------------------------------------------- DDR output on LED 1
    wire dq, pad1;
    ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")) u_oddr (
        .C(c25), .CE(1'b1), .D1(1'b1), .D2(1'b0), .R(1'b0), .S(1'b0), .Q(dq));
    IOBUF u_io1 (.I(dq), .T(1'b0), .O(pad1), .IO(lio[1]));

    // ---------------------------------------------------------------- frequency counting
    reg [2:0] s0 = 0, s1 = 0;
    always @(posedge c200) begin s0 <= {s0[1:0], pad0}; s1 <= {s1[1:0], pad1}; end
    wire [31:0] g25, g100, g125, g200, g50, g133, gmux, ge0, ge1;
    st_count u_k25  (.fclk(c25),  .en(1'b1), .gray(g25));
    st_count u_k100 (.fclk(c100), .en(1'b1), .gray(g100));
    st_count u_k125 (.fclk(c125), .en(1'b1), .gray(g125));
    st_count u_k200 (.fclk(c200), .en(1'b1), .gray(g200));
    st_count u_k50  (.fclk(c50),  .en(1'b1), .gray(g50));
    st_count u_k133 (.fclk(c133), .en(1'b1), .gray(g133));
    st_count u_kmux (.fclk(cmux), .en(1'b1), .gray(gmux));
    st_count u_ke0  (.fclk(c200), .en(s0[1] & ~s0[2]), .gray(ge0));
    st_count u_ke1  (.fclk(c200), .en(s1[1] & ~s1[2]), .gray(ge1));

    reg [23:0] gate_cnt = 0;
    reg gate = 1'b0;
    reg [15:0] gates = 0;
    always @(posedge clk) begin
        gate <= (gate_cnt == 24'd9_999_999);
        gate_cnt <= (gate_cnt == 24'd9_999_999) ? 24'd0 : gate_cnt + 1'b1;
        if (gate) gates <= gates + 1'b1;
    end
    wire [31:0] f25, f100, f125, f200, f50, f133, fmux, fe0, fe1;
    st_meter u_m25  (.clk(clk), .gray_in(g25),  .gate(gate), .per_gate(f25));
    st_meter u_m100 (.clk(clk), .gray_in(g100), .gate(gate), .per_gate(f100));
    st_meter u_m125 (.clk(clk), .gray_in(g125), .gate(gate), .per_gate(f125));
    st_meter u_m200 (.clk(clk), .gray_in(g200), .gate(gate), .per_gate(f200));
    st_meter u_m50  (.clk(clk), .gray_in(g50),  .gate(gate), .per_gate(f50));
    st_meter u_m133 (.clk(clk), .gray_in(g133), .gate(gate), .per_gate(f133));
    st_meter u_mmux (.clk(clk), .gray_in(gmux), .gate(gate), .per_gate(fmux));
    st_meter u_me0  (.clk(clk), .gray_in(ge0),  .gate(gate), .per_gate(fe0));
    st_meter u_me1  (.clk(clk), .gray_in(ge1),  .gate(gate), .per_gate(fe1));

    // ---------------------------------------------------------------- block RAM self-test
    (* ram_style = "block" *) reg [31:0] mem [0:4095];
    reg [11:0] wa = 0, ra = 0;
    reg [31:0] wd = 0, rd = 0;
    reg we = 1'b0;
    always @(posedge clk) begin
        if (we) mem[wa] <= wd;
        rd <= mem[ra];
    end
    function [31:0] pat(input [11:0] a);
        pat = {a, ~a, 8'hA5};
    endfunction
    reg [1:0] bt_phase = 0;           // 0 write all, 1 read all, 2 done (ARM access), 3 waiting to start
    // block RAM writes in the very first clock cycles after configuration can be lost (measured),
    // so the self-test starts 65536 cycles (0.65 ms) after the design starts
    reg [16:0] bt_wait = 0;
    wire bt_go = bt_wait[16];
    always @(posedge clk) if (!bt_go) bt_wait <= bt_wait + 1'b1;
    reg [12:0] bt_i = 0;
    reg [11:0] chk_a = 0;
    reg chk_v = 1'b0, chk_v2 = 1'b0;
    reg [11:0] chk_a2 = 0;
    reg [31:0] bt_err = 0;
    reg strobe_q = 1'b0;
    always @(posedge clk) begin
        we <= 1'b0;
        chk_v <= 1'b0;
        chk_v2 <= chk_v; chk_a2 <= chk_a;
        if (chk_v2 && rd != pat(chk_a2)) bt_err <= bt_err + 1'b1;
        strobe_q <= ctrl0[31];
        case (bt_phase)
        2'd0: if (bt_go) begin
            we <= 1'b1; wa <= bt_i[11:0]; wd <= pat(bt_i[11:0]);
            bt_i <= bt_i + 1'b1;
            if (bt_i == 13'd4095) begin bt_phase <= 2'd1; bt_i <= 0; end
        end
        2'd1: begin
            ra <= bt_i[11:0]; chk_a <= bt_i[11:0]; chk_v <= 1'b1;
            bt_i <= bt_i + 1'b1;
            if (bt_i == 13'd4095) bt_phase <= 2'd2;
        end
        default: begin
            ra <= ctrl0[11:0];
            if (ctrl0[31] && !strobe_q) begin we <= 1'b1; wa <= ctrl0[11:0]; wd <= ctrl1; end
        end
        endcase
    end

    // ---------------------------------------------------------------- DSP multiply
    reg signed [24:0] da = 0;
    reg signed [17:0] db = 0;
    reg signed [42:0] dp = 0;
    always @(posedge clk) begin
        da <= ctrl[2*32 +: 25];
        db <= ctrl[3*32 +: 18];
        dp <= da * db;
    end

    // ---------------------------------------------------------------- shift register (SRL) test
    reg [7:0] c8 = 0;
    reg [7:0] srl [0:31];
    reg [5:0] warm = 0;
    reg [15:0] srl_err = 0;
    integer k;
    always @(posedge clk) begin
        c8 <= c8 + 1'b1;
        srl[0] <= c8;
        for (k = 1; k < 32; k = k + 1) srl[k] <= srl[k - 1];
        if (warm != 6'd63) warm <= warm + 1'b1;
        else if (srl[31] != c8 - 8'd32) srl_err <= srl_err + 1'b1;
    end

    // ---------------------------------------------------------------- distributed (LUT) RAM test
    (* ram_style = "distributed" *) reg [7:0] lram [0:63];
    reg [6:0] li = 0;
    reg lphase = 1'b0, ldone = 1'b0;
    reg [15:0] lram_err = 0;
    always @(posedge clk) begin
        if (!lphase) begin
            lram[li[5:0]] <= li[5:0] * 8'd3 + 8'd1;
            li <= li + 1'b1;
            if (li == 7'd63) begin lphase <= 1'b1; li <= 0; end
        end else if (!ldone) begin
            if (lram[li[5:0]] != li[5:0] * 8'd3 + 8'd1) lram_err <= lram_err + 1'b1;
            li <= li + 1'b1;
            if (li == 7'd63) ldone <= 1'b1;
        end
    end

    // ---------------------------------------------------------------- slow blinks
    reg [24:0] bl25 = 0;
    reg [25:0] bl50 = 0;
    always @(posedge c25) bl25 <= bl25 + 1'b1;
    always @(posedge c50) bl50 <= bl50 + 1'b1;
    assign lout[0] = ~bl25[24];
    assign lout[1] = ~bl50[25];

    // ---------------------------------------------------------------- results
    //  0 magic "STST"        1 flags: [0] MMCM locked [1] PLL locked [2] RAM test done [3] LUT RAM test done
    //                               [4] clock switch = PLL   [31:16] number of 0.1 s gates so far
    //  2 block RAM errors    3 block RAM word at ctrl0[11:0]   4/5 DSP product low / high (signed)
    //  6..12 counts per 0.1 s: 25, 100, 125, 200 (MMCM), 50, 133 (PLL), switched clock
    //  13/14 rising edges per 0.1 s at LED pin 0 (serializer) / 1 (DDR)   15 [31:16] LUT RAM errors [15:0] SRL errors
    assign status = {
        {lram_err, srl_err}, fe1, fe0, fmux, f133, f50, f200, f125, f100, f25,
        {{21{dp[42]}}, dp[42:32]}, dp[31:0], rd, bt_err,
        {gates, 11'd0, sel, ldone, bt_phase == 2'd2, p_locked, m_locked},
        32'h53545354 };
endmodule

// free-running counter in its own clock domain, given out as Gray code (safe to sample elsewhere)
module st_count (input wire fclk, input wire en, output reg [31:0] gray = 0);
    reg [31:0] bin = 0;
    always @(posedge fclk) begin
        if (en) bin <= bin + 1'b1;
        gray <= bin ^ (bin >> 1);
    end
endmodule

// sample a Gray counter in the system clock domain; counts per gate
module st_meter (input wire clk, input wire [31:0] gray_in, input wire gate, output reg [31:0] per_gate = 0);
    (* ASYNC_REG = "TRUE" *) reg [31:0] g1 = 0, g2 = 0;
    reg [31:0] bin = 0, last = 0;
    integer i;
    always @(posedge clk) begin
        g1 <= gray_in;
        g2 <= g1;
        bin[31] <= g2[31];
        for (i = 30; i >= 0; i = i - 1) bin[i] <= ^g2[31:i];
        if (gate) begin per_gate <= bin - last; last <= bin; end
    end
endmodule
