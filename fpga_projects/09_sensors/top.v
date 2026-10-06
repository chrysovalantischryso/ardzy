`timescale 1ns / 1ps
// 09 Sensor helpers: HC-SR04 ultrasonic distance, NEC IR remote decoder, capacitive touch.
//   slot 0 info (project "SENS"), slot 1 the sensors
//   J8 pin 5 = TRIG, pin 11 = ECHO (through a divider: 5 V!), pin 12 = IR receiver out, pin 15 = touch pad
module top (
    output wire       trig,
    input  wire       echo,
    input  wire       ir,
    inout  wire       touch,
    output wire [3:0] leds
);
    wire clk, rstn, we, re;
    wire [15:0] addr;
    wire [31:0] wdata, rd_info, rd_s;
    wire [3:0]  wstrb;
    ardzy_bus u_bus (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_wstrb(wstrb),
                     .bus_we(we), .bus_re(re), .bus_rdata(rd_info | rd_s));
    ardzy_info #(.SLOT(0), .PROJECT("SENS"), .VERSION(1)) u_info (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_info), .leds_n(leds));
    wire t_low, t_in;
    ardzy_sensors #(.SLOT(1)) u_s (
        .clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(rd_s), .trig(trig), .echo(echo), .ir(ir), .touch_low(t_low), .touch_in(t_in));
    IOBUF u_t (.I(1'b0), .T(~t_low), .O(t_in), .IO(touch));
endmodule
