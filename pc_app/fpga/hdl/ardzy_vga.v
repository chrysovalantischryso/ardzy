// Ardzy FPGA library: ardzy_vga, VGA picture 640 x 480 from a 320 x 240 frame buffer, 16 colours.
//
// Pixel clock 25.0 MHz from an MMCM (100 MHz * 10 / 40): 31.25 kHz lines, 59.5 Hz frames
// (the standard is 25.175 MHz; monitors take 25.0). Every frame-buffer pixel is shown as 2 x 2.
// Colours: 2 bits each for red, green, blue (64 colours) through a 16-entry palette.
// Slots: SLOT = registers, SLOT+1 .. SLOT+10 = frame buffer (9600 words used, 10240 there):
//   word w = 8 pixels of one row: pixel x = (w % 40) * 8 + k is bits 4k+3..4k, k = 0 on the left;
//   row y = w / 40. Word address in the window: (SLOT + 1) * 0x1000 + 4 * w.
// Registers (word index):
//   0 CTRL      [0] picture on  [1] test pattern (colour bars) instead of the frame buffer
//   1 FRAMES    (read) frames shown
//   2 HS_PERIOD (read) time between line syncs at the pin, in 10 ns (should be 3200)
//   3 VS_PERIOD (read) time between frame syncs at the pin, in 10 ns (should be 1,680,000)
//   4 ID        "VGA6"
//   5 PROBE_XY  screen position to look at: [9:0] x (0..639), [25:16] y (0..479)
//   6 PROBE     (read) what the picture shows there: [9:6] frame-buffer value, [5:0] colour at the pins
//   16..31      palette: entry n = colour of value n, [5:4] red [3:2] green [1:0] blue
// The frame buffer can only be written by the ARM (the picture side reads it); use PROBE to check it.
`timescale 1ns / 1ps
module ardzy_vga #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,                  // 100 MHz bus clock
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg  [1:0]  red = 2'd0,
    output reg  [1:0]  green = 2'd0,
    output reg  [1:0]  blue = 2'd0,
    output reg         hsync = 1'b1,
    output reg         vsync = 1'b1,
    input  wire        hs_in,                // the sync pins read back at the pad
    input  wire        vs_in
);
    // ---- pixel clock
    wire fb_o, fb_i, p25_o, pclk, locked;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(40.0)) u_mmcm (
        .CLKIN1(clk), .CLKFBIN(fb_i), .CLKFBOUT(fb_o), .RST(~rstn), .PWRDWN(1'b0), .CLKOUT0(p25_o), .LOCKED(locked));
    BUFG u_bfb (.I(fb_o), .O(fb_i));
    BUFG u_bp (.I(p25_o), .O(pclk));

    // ---- bus side
    wire reg_sel = (bus_addr[15:12] == SLOT);
    wire [3:0] fslot = bus_addr[15:12] - SLOT - 4'd1;
    wire fb_sel = (bus_addr[15:12] > SLOT) && (bus_addr[15:12] <= SLOT + 4'd10);
    wire [9:0] idx = bus_addr[11:2];
    wire [13:0] fb_a = {fslot, idx};
    reg [1:0] ctrl = 2'b01;
    reg [5:0] pal [0:15];
    integer k;
    initial begin                                   // default palette (RGB222), like the classic 16 PC colours
        pal[0] = 6'b000000; pal[1] = 6'b000010; pal[2] = 6'b001000; pal[3] = 6'b001010;
        pal[4] = 6'b100000; pal[5] = 6'b100010; pal[6] = 6'b100100; pal[7] = 6'b101010;
        pal[8] = 6'b010101; pal[9] = 6'b010111; pal[10] = 6'b011101; pal[11] = 6'b011111;
        pal[12] = 6'b110101; pal[13] = 6'b110111; pal[14] = 6'b111101; pal[15] = 6'b111111;
    end

    // frame buffer: written by the ARM (100 MHz), read by the picture side (25 MHz)
    (* ram_style = "block" *) reg [31:0] fb [0:10239];
    always @(posedge clk) begin
        if (bus_we && fb_sel) fb[fb_a] <= bus_wdata;
    end
    // pixel probe: the picture side captures what it really shows at (probe_x, probe_y) every frame
    reg [9:0] probe_x = 10'd0, probe_y = 10'd0;
    reg [9:0] probe_val = 10'd0;              // [9:6] frame-buffer value, [5:0] colour sent to the pins

    // sync measurement at the pins (100 MHz)
    reg [2:0]  hs3 = 3'b111, vs3 = 3'b111;
    reg [31:0] hcnt = 32'd0, vcnt = 32'd0, hper = 32'd0, vper = 32'd0, frames = 32'd0;
    always @(posedge clk) begin
        hs3 <= {hs3[1:0], hs_in}; vs3 <= {vs3[1:0], vs_in};
        hcnt <= hcnt + 1'b1; vcnt <= vcnt + 1'b1;
        if (hs3[2] && !hs3[1]) begin hper <= hcnt; hcnt <= 32'd1; end
        if (vs3[2] && !vs3[1]) begin vper <= vcnt; vcnt <= 32'd1; frames <= frames + 1'b1; end
    end

    always @(posedge clk) begin
        if (!rstn) ctrl <= 2'b01;
        else if (bus_we && reg_sel) begin
            if (idx == 10'd0) ctrl <= bus_wdata[1:0];
            if (idx == 10'd5) begin probe_x <= bus_wdata[9:0]; probe_y <= bus_wdata[25:16]; end
            if (idx >= 10'd16 && idx < 10'd32) pal[idx[3:0]] <= bus_wdata[5:0];
        end
        if (bus_re) begin
            if (!reg_sel) bus_rdata <= 32'd0;
            else if (idx >= 10'd16 && idx < 10'd32) bus_rdata <= {26'd0, pal[idx[3:0]]};
            else case (idx)
                10'd0: bus_rdata <= {29'd0, locked, ctrl};
                10'd1: bus_rdata <= frames;
                10'd2: bus_rdata <= hper;
                10'd3: bus_rdata <= vper;
                10'd4: bus_rdata <= 32'h56474136;          // "VGA6"
                10'd5: bus_rdata <= {6'd0, probe_y, 6'd0, probe_x};
                10'd6: bus_rdata <= {22'd0, probe_val};
                default: bus_rdata <= 32'd0;
            endcase
        end
    end

    // ---- picture side (25 MHz)
    reg [1:0] cs1 = 2'b00, cs2 = 2'b00;
    always @(posedge pclk) begin cs1 <= ctrl; cs2 <= cs1; end
    reg [9:0] hc = 10'd0, vc = 10'd0;
    always @(posedge pclk) begin
        if (hc == 10'd799) begin
            hc <= 10'd0;
            vc <= (vc == 10'd524) ? 10'd0 : vc + 1'b1;
        end else hc <= hc + 1'b1;
    end
    wire vis = (hc < 10'd640) && (vc < 10'd480);
    // stage 1: word address = (y / 2) * 40 + x / 16
    reg [13:0] fa = 14'd0;
    reg [9:0]  h1 = 10'd0, h2 = 10'd0, v1c = 10'd0, v2c = 10'd0;
    reg        v1 = 1'b0, v2 = 1'b0, hs1 = 1'b1, hs2 = 1'b1, vs1 = 1'b1, vs2 = 1'b1;
    reg [31:0] q = 32'd0;
    always @(posedge pclk) begin
        fa <= ({5'd0, vc[9:1]} << 5) + ({5'd0, vc[9:1]} << 3) + {10'd0, hc[9:4]};
        h1 <= hc; v1 <= vis; v1c <= vc;
        hs1 <= ~((hc >= 10'd656) && (hc < 10'd752));
        vs1 <= ~((vc >= 10'd490) && (vc < 10'd492));
        q <= fb[fa];                                             // stage 2
        h2 <= h1; v2 <= v1; v2c <= v1c; hs2 <= hs1; vs2 <= vs1;
    end
    // stage 3: pick the pixel, colour through the palette (or the test pattern)
    wire [3:0] nib = q[{h2[3:1], 2'b00} +: 4];
    wire [2:0] bar = h2[8:6];                                    // colour bars, 64 pixels wide
    wire grid = (h2[4:0] == 5'd0) || (v2c[4:0] == 5'd0);
    wire [5:0] test_c = grid ? 6'b111111 : {bar[2], bar[2], bar[1], bar[1], bar[0], bar[0]};
    always @(posedge pclk) begin
        hsync <= hs2;
        vsync <= vs2;
        if (v2 && cs2[0]) {red, green, blue} <= cs2[1] ? test_c : pal[nib];
        else {red, green, blue} <= 6'd0;
        if (v2 && h2 == probe_x && v2c == probe_y) probe_val <= {nib, cs2[1] ? test_c : pal[nib]};
    end
endmodule
