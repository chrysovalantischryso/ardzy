// Testbench for the open-toolchain pin-control design core (ardzy_io_core): an AXI3 master like
// the Zynq GP0 port, with single writes/reads, bursts, an address nobody owns, the GPIO and the
// instruments of ardzy_ctl. Run: sim\run_sim_open.bat
`timescale 1ns / 1ps
module tb_open;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [31:0] awaddr = 0, araddr = 0, wdata = 0;
    reg  [3:0]  awlen = 0, arlen = 0, wstrb = 4'hF;
    reg  [11:0] awid = 0, arid = 0;
    reg         awvalid = 0, wvalid = 0, wlast = 0, bready = 0, arvalid = 0, rready = 0;
    wire        awready, wready, bvalid, arready, rvalid, rlast;
    wire [11:0] bid, rid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    wire [48:0] pins;
    wire        fan_pwm;
    integer errors = 0;
    genvar k;
    generate for (k = 0; k < 49; k = k + 1) begin : pu
        pullup (pins[k]);
    end endgenerate

    ardzy_io_core dut (
        .clk(clk), .rstn(rstn),
        .awaddr(awaddr), .awlen(awlen), .awsize(2'b10), .awburst(2'b01), .awid(awid), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arlen(arlen), .arsize(2'b10), .arburst(2'b01), .arid(arid), .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .pins(pins), .fan_pwm(fan_pwm), .fan_tach(6'd0));
    defparam dut.u_ctl.dna_direct.u_dna.SIM_DNA_VALUE = 57'h0ABCDEF12345678;

    task wait_for(input integer what);   // 0 awready 1 wready 2 bvalid 3 arready 4 rvalid
        integer t;
        begin
            t = 0;
            @(posedge clk);
            while (!(what == 0 ? awready : what == 1 ? wready : what == 2 ? bvalid : what == 3 ? arready : rvalid) && t < 200) begin
                @(posedge clk); t = t + 1;
            end
            if (t >= 200) begin $display("ERROR: timeout waiting for signal %0d", what); errors = errors + 1; end
        end
    endtask

    task wr(input [31:0] a, input [31:0] d);
        begin
            awaddr <= a; awlen <= 0; awid <= 12'h5A; awvalid <= 1;
            wait_for(0); awvalid <= 0;
            wdata <= d; wlast <= 1; wvalid <= 1;
            wait_for(1); wvalid <= 0; wlast <= 0;
            bready <= 1; wait_for(2);
            if (bid !== 12'h5A) begin $display("ERROR: BID %h", bid); errors = errors + 1; end
            bready <= 0;
        end
    endtask

    task rd(input [31:0] a, output [31:0] d);
        begin
            araddr <= a; arlen <= 0; arid <= 12'h3C; arvalid <= 1;
            wait_for(3); arvalid <= 0;
            rready <= 1; wait_for(4);
            d = rdata;
            if (!rlast || rid !== 12'h3C) begin $display("ERROR: single read RLAST/RID"); errors = errors + 1; end
            rready <= 0;
        end
    endtask

    task expect(input [255:0] what, input [31:0] got, input [31:0] want);
        if (got !== want) begin $display("ERROR: %0s = 0x%h, expected 0x%h", what, got, want); errors = errors + 1; end
        else $display("ok   : %0s = 0x%h", what, got);
    endtask

    reg [31:0] v, b [0:3];
    integer i;
    initial begin
        repeat (10) @(posedge clk);
        rstn = 1;
        repeat (5) @(posedge clk);
        rd(32'h43C0_0000, v); expect("ctl ID through the bridge", v, 32'h41525A32);
        rd(32'h4120_0004, v); expect("GPIO TRI reset (all inputs)", v, 32'hFFFFFFFF);
        rd(32'h4500_0000, v); expect("unmapped address reads 0", v, 32'h0);
        wr(32'h4500_0000, 32'h1234);                      // must be answered too
        // GPIO: j1[0] output 0
        wr(32'h4120_0000, 32'h0); wr(32'h4120_0004, 32'hFFFFFFFE);
        repeat (6) @(posedge clk);
        expect("pin 0 driven low", {31'd0, pins[0]}, 0);
        rd(32'h4120_0000, v); expect("GPIO DATA reads the pins", v & 32'h3, 32'h2);
        // byte write (WSTRB) to TRI2: only the low byte changes
        wstrb <= 4'h1; wr(32'h4120_000C, 32'h0000_00F0); wstrb <= 4'hF;
        rd(32'h4120_000C, v); expect("TRI2 after byte write", v, 32'h0001_FFF0);
        wr(32'h4120_000C, 32'h0001_FFFF);
        // PWM registers by a 2-beat burst write (period, high of PWM0)
        awaddr <= 32'h43C0_0060; awlen <= 1; awid <= 12'h7; awvalid <= 1;
        wait_for(0); awvalid <= 0;
        wdata <= 32'd200; wlast <= 0; wvalid <= 1; wait_for(1); wvalid <= 0;
        wdata <= 32'd50;  wlast <= 1; wvalid <= 1; wait_for(1); wvalid <= 0; wlast <= 0;
        bready <= 1; wait_for(2); bready <= 0;
        // 4-beat burst read 0x43C0_0060..6C
        araddr <= 32'h43C0_0060; arlen <= 3; arid <= 12'h9; arvalid <= 1;
        wait_for(3); arvalid <= 0;
        rready <= 1;
        for (i = 0; i < 4; i = i + 1) begin
            wait_for(4);
            b[i] = rdata;
            if ((i == 3) != rlast) begin $display("ERROR: RLAST at beat %0d", i); errors = errors + 1; end
        end
        rready <= 0;
        expect("burst beat 0 (PWM0 period)", b[0], 32'd200);
        expect("burst beat 1 (PWM0 high)", b[1], 32'd50);
        expect("burst beat 2 (PWM1 period)", b[2], 32'd100000);
        // PWM0 on pin 5 and measure it
        wr(32'h43C0_0040, 32'h0010_0000);
        wr(32'h43C0_00A0, 32'd5);
        wr(32'h43C0_0028, 32'd2000);
        repeat (4500) @(posedge clk);
        rd(32'h43C0_00A4, v); expect("measured edges (10 per 2000)", v, 32'd10);
        rd(32'h43C0_00AC, v); expect("measured period", v, 32'd200);
        rd(32'h43C0_0034, v); expect("DNA_LO (direct clock mode)", v, 32'h12345678);
        rd(32'h43C0_0038, v); expect("DNA_HI (direct clock mode)", v, 32'h80ABCDEF);
        if (errors == 0) $display("SIM_PASS"); else $display("SIM_FAIL: %0d errors", errors);
        $finish;
    end
    initial begin #5000000; $display("SIM_FAIL: timeout"); $finish; end
endmodule
