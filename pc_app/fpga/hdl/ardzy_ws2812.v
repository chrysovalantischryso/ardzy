// Ardzy FPGA library: ardzy_ws2812, driver for WS2812 / WS2812B / SK6812 RGB LEDs ("NeoPixel").
//
// Slots: SLOT = registers, SLOT+1 = pixel memory (1024 words, 0x00RRGGBB, word n = LED n).
// Registers (word index):
//   0 CTRL     write 1: send the pixels to the strip.  read: [0] busy  [31:8] frames sent
//   1 COUNT    number of LEDs (1..1024)
//   2 BRIGHT   brightness 0..255 (applied while sending; 255 = as stored)
//   3 ORDER    0 = GRB (WS2812B), 1 = RGB, 2 = BRG, 3 = RBG, 4 = BGR, 5 = GBR
//   4 T0H      high time of a 0 bit, clock cycles (default 40 = 0.40 us at 100 MHz)
//   5 T1H      high time of a 1 bit (default 80 = 0.80 us)
//   6 TBIT     length of one bit (default 125 = 1.25 us)
//   7 TRESET   low time after the last LED (default 30000 = 300 us)
//   8 PULSES   (read) high pulses seen at the pin during the last frame (24 per LED)
//   9 HI0      (read) last short pulse seen at the pin, cycles
//  10 HI1      (read) last long pulse seen at the pin, cycles
//  11 ID       (read) "WS28"
// The pin is read back at the pad (pin_in) for the self-test: PULSES, HI0 and HI1.
`timescale 1ns / 1ps
module ardzy_ws2812 #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg         dout = 1'b0,          // to the strip's DIN (through a level shifter for 5 V strips)
    input  wire        pin_in                // the same pin read back at the pad
);
    wire reg_sel = (bus_addr[15:12] == SLOT);
    wire pix_sel = (bus_addr[15:12] == SLOT + 4'd1);
    wire [9:0] idx = bus_addr[11:2];

    reg [10:0] count = 11'd60;
    reg [7:0]  bright = 8'd255;
    reg [2:0]  order = 3'd0;
    reg [15:0] t0h = 16'd40, t1h = 16'd80, tbit = 16'd125;
    reg [19:0] treset = 20'd30000;
    reg [23:0] frames = 24'd0;
    reg        busy = 1'b0, start = 1'b0;

    // pixel memory: port A written by the ARM, port B read by the sender
    (* ram_style = "block" *) reg [23:0] pix [0:1023];
    reg [9:0]  raddr = 10'd0;
    reg [23:0] rpix = 24'd0;
    always @(posedge clk) begin
        if (bus_we && pix_sel) pix[idx] <= bus_wdata[23:0];
        rpix <= pix[raddr];
    end

    // pin read-back measurement
    reg [2:0]  ps = 3'd0;
    reg [15:0] hw = 16'd0, hi0 = 16'd0, hi1 = 16'd0;
    reg [31:0] pulses = 32'd0;
    always @(posedge clk) begin
        ps <= {ps[1:0], pin_in};
        if (start) pulses <= 32'd0;
        if (ps[1]) hw <= hw + 1'b1;
        else hw <= 16'd0;
        if (ps[2] && !ps[1]) begin                       // falling edge: a pulse ended
            pulses <= pulses + 1'b1;
            if (hw < ((t0h + t1h) >> 1)) hi0 <= hw; else hi1 <= hw;   // hw = clocks the pin was high
        end
    end

    // registers
    always @(posedge clk) begin
        start <= 1'b0;
        if (!rstn) begin
            count <= 11'd60; bright <= 8'd255; order <= 3'd0; t0h <= 16'd40; t1h <= 16'd80; tbit <= 16'd125; treset <= 20'd30000;
        end else if (bus_we && reg_sel) case (idx)
            10'd0: start <= bus_wdata[0] & ~busy;
            10'd1: count <= (bus_wdata[10:0] == 0) ? 11'd1 : (bus_wdata[10:0] > 11'd1024 ? 11'd1024 : bus_wdata[10:0]);
            10'd2: bright <= bus_wdata[7:0];
            10'd3: order <= bus_wdata[2:0];
            10'd4: t0h <= bus_wdata[15:0];
            10'd5: t1h <= bus_wdata[15:0];
            10'd6: tbit <= bus_wdata[15:0];
            10'd7: treset <= bus_wdata[19:0];
            default: ;
        endcase
        if (bus_re) begin
            if (!reg_sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {frames, 7'd0, busy};
                10'd1: bus_rdata <= {21'd0, count};
                10'd2: bus_rdata <= {24'd0, bright};
                10'd3: bus_rdata <= {29'd0, order};
                10'd4: bus_rdata <= {16'd0, t0h};
                10'd5: bus_rdata <= {16'd0, t1h};
                10'd6: bus_rdata <= {16'd0, tbit};
                10'd7: bus_rdata <= {12'd0, treset};
                10'd8: bus_rdata <= pulses;
                10'd9: bus_rdata <= {16'd0, hi0};
                10'd10: bus_rdata <= {16'd0, hi1};
                10'd11: bus_rdata <= 32'h57533238;          // "WS28"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end

    // sender: LOAD (read pixel) -> SCALE -> 24 bits -> next LED ... -> RESET low time
    localparam S_IDLE = 3'd0, S_READ = 3'd1, S_WAIT = 3'd2, S_SCALE = 3'd3, S_BITS = 3'd4, S_RESET = 3'd5;
    reg [2:0]  s = S_IDLE;
    reg [10:0] led = 11'd0;
    reg [23:0] sh = 24'd0;
    reg [4:0]  nbit = 5'd0;
    reg [15:0] tc = 16'd0;
    reg [19:0] rc = 20'd0;
    reg [15:0] r16, g16, b16;
    wire [7:0] r8 = rpix[23:16], g8 = rpix[15:8], b8 = rpix[7:0];
    always @(posedge clk) begin
        if (!rstn) begin
            s <= S_IDLE; busy <= 1'b0; dout <= 1'b0;
        end else case (s)
        S_IDLE: begin
            dout <= 1'b0;
            if (start) begin busy <= 1'b1; led <= 11'd0; raddr <= 10'd0; s <= S_WAIT; end
        end
        S_READ: begin raddr <= led[9:0]; s <= S_WAIT; end
        S_WAIT: s <= S_SCALE;                                 // memory output arrives
        S_SCALE: begin
            // brightness: c * (bright + 1) / 256
            r16 = r8 * ({1'b0, bright} + 9'd1);
            g16 = g8 * ({1'b0, bright} + 9'd1);
            b16 = b8 * ({1'b0, bright} + 9'd1);
            case (order)
                3'd1: sh <= {r16[15:8], g16[15:8], b16[15:8]};
                3'd2: sh <= {b16[15:8], r16[15:8], g16[15:8]};
                3'd3: sh <= {r16[15:8], b16[15:8], g16[15:8]};
                3'd4: sh <= {b16[15:8], g16[15:8], r16[15:8]};
                3'd5: sh <= {g16[15:8], b16[15:8], r16[15:8]};
                default: sh <= {g16[15:8], r16[15:8], b16[15:8]};
            endcase
            nbit <= 5'd0; tc <= 16'd0; s <= S_BITS;
        end
        S_BITS: begin
            dout <= (tc < (sh[23] ? t1h : t0h));
            if (tc + 1'b1 >= tbit) begin
                tc <= 16'd0;
                sh <= {sh[22:0], 1'b0};
                if (nbit == 5'd23) begin
                    if (led + 1'b1 >= count) begin rc <= 20'd0; s <= S_RESET; end
                    else begin led <= led + 1'b1; s <= S_READ; end
                end else nbit <= nbit + 1'b1;
            end else tc <= tc + 1'b1;
        end
        S_RESET: begin
            dout <= 1'b0;
            if (rc >= treset) begin busy <= 1'b0; frames <= frames + 1'b1; s <= S_IDLE; end
            else rc <= rc + 1'b1;
        end
        default: s <= S_IDLE;
        endcase
    end
endmodule
