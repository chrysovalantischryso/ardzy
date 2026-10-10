// ardzy_io_ebaz: the Ardzy pin-control design for the EBAZ4205.
// The same core as the Antminer S9's (projects/ardzy_io: AXI GPIO compatible pins, PWM, measuring, UART,
// logic analyzer, fan control, same addresses and registers), with the EBAZ4205's pins in its 49 places:
//   0..13  DATA1-5,6,7,8,9,11,13..20      14..27  DATA2 (same)      28..40  DATA3-5..19      45  DATA3-20
//   46     J5 fan PWM (the second fan header's output)               41..44, 47, 48: not connected
//   fan_pwm = J3 fan PWM, fan speed 0 = J3, 1 = J5
// The Ethernet and the two LEDs are added by the Ardzy build (fpga/flow.py), like in every EBAZ4205 design.
`timescale 1ns / 1ps
module ardzy_io_ebaz (
    inout  wire [13:0] data1,
    inout  wire [13:0] data2,
    inout  wire [13:0] data3,
    inout  wire        j5_pwm,
    output wire        fan_pwm,
    input  wire        j3_tach,
    input  wire        j5_tach
);
    wire clk, rstn;
    wire [31:0] awaddr, wdata, araddr, rdata;
    wire [3:0]  awlen, wstrb, arlen;
    wire [1:0]  awsize, awburst, arsize, arburst, bresp, rresp;
    wire [11:0] awid, arid, bid, rid;
    wire awvalid, awready, wlast, wvalid, wready, bvalid, bready, arvalid, arready, rlast, rvalid, rready;
    wire [3:0] nc_id;                   // places 41..44 (the S9's board-ID straps): no pin here
    wire [1:0] nc_hi;                   // places 47, 48
    ardzy_ps7 u_ps7 (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready));
    ardzy_io_core #(.PIN_MASK(49'h0_61FF_FFFF_FFFF)) u_core (   // places 0..40, 45, 46
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .pins({nc_hi, j5_pwm, data3[13], nc_id, data3[12:0], data2, data1}),
        .fan_pwm(fan_pwm), .fan_tach({4'b0000, j5_tach, j3_tach}));
endmodule
