`timescale 1ns / 1ps
// 05 SPI and I2C in hardware: an SPI controller on J2 and an I2C controller on the board's I2C bus.
//   slot 0 info (project "SPIC"), slot 1 SPI, slot 2 I2C
//   SPI: CS = J2 pin 5, MOSI = J2 pin 11, MISO = J2 pin 12, SCLK = J2 pin 15
//   I2C: SDA = pin 3, SCL = pin 4 of J1..J8 (1 kohm pull-ups on the board)
module top (
    output wire       spi_cs,
    output wire       spi_mosi,
    input  wire       spi_miso,
    output wire       spi_sclk,
    inout  wire       i2c_scl,
    inout  wire       i2c_sda,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_spi, rd_i2c;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_spi | rd_i2c));
    ardzy_info #(.SLOT(0), .PROJECT("SPIC"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    ardzy_spi #(.SLOT(1)) u_spi (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_spi), .sclk(spi_sclk), .mosi(spi_mosi), .miso(spi_miso), .cs_n(spi_cs));
    wire scl_low, sda_low, scl_in, sda_in;
    ardzy_i2c #(.SLOT(2)) u_i2c (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_i2c), .scl_low(scl_low), .sda_low(sda_low), .scl_in(scl_in), .sda_in(sda_in));
    IOBUF u_scl (.I(1'b0), .T(~scl_low), .O(scl_in), .IO(i2c_scl));
    IOBUF u_sda (.I(1'b0), .T(~sda_low), .O(sda_in), .IO(i2c_sda));
endmodule
