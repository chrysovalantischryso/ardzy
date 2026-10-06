`timescale 1ns / 1ps
// 08 Audio: I2S sound out (to a DAC or amplifier module), I2S in, PDM microphone in.
//   slot 0 info (project "AUD0"), slot 1 the audio block
//   J3 pins 5/11/12/15 = MCLK, BCLK, DOUT, LRCLK      J6 pin 5 = DIN, pin 11 = PDM CLK, pin 12 = PDM DATA
module top (
    output wire       mclk,
    output wire       bclk,
    inout  wire       dout,
    inout  wire       lrclk,
    input  wire       din,
    output wire       pdm_clk,
    input  wire       pdm_dat,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_aud;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_aud));
    ardzy_info #(.SLOT(0), .PROJECT("AUD0"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire d_o, d_i, l_o, l_i;
    ardzy_audio #(.SLOT(1)) u_aud (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_aud), .mclk(mclk), .bclk(bclk), .lrclk(l_o), .dout(d_o), .din(din),
        .dout_in(d_i), .lr_in(l_i), .pdm_clk(pdm_clk), .pdm_dat(pdm_dat));
    IOBUF u_d (.I(d_o), .T(1'b0), .O(d_i), .IO(dout));
    IOBUF u_l (.I(l_o), .T(1'b0), .O(l_i), .IO(lrclk));
endmodule
