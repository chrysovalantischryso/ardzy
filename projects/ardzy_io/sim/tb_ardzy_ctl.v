// Testbench for ardzy_ctl (Vivado xsim). Checks the AXI handshakes and every instrument:
// ID/CAPS, Device DNA, GPIO pass-through, board-ID protection, PWM on a pin, measuring channel,
// UART loopback (TX and RX on the same pin), logic analyzer with an edge trigger, fan registers.
// Run: sim\run_sim.bat
`timescale 1ns / 1ps
module tb;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;                       // 100 MHz

    reg  [15:0] awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [31:0] rdata;
    wire [1:0]  bresp, rresp;
    reg  [31:0] g1o = 0, g1t = 32'hFFFFFFFF;
    reg  [16:0] g2o = 0, g2t = 17'h1FFFF;
    wire [31:0] g1i;
    wire [16:0] g2i;
    wire [48:0] pins;
    wire        fan_pwm;
    reg  [5:0]  tach = 0;
    integer errors = 0;

    genvar k;
    generate for (k = 0; k < 49; k = k + 1) begin : pu
        pullup (pins[k]);
    end endgenerate
    // board-ID straps: tie one of them low (a strap resistor to GND)
    assign (strong0, strong1) pins[42] = 1'b0;

    ardzy_ctl dut (
        .s_axi_aclk(clk), .s_axi_aresetn(rstn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .gpio1_o(g1o), .gpio1_t(g1t), .gpio1_i(g1i), .gpio2_o(g2o), .gpio2_t(g2t), .gpio2_i(g2i),
        .pins(pins), .fan_pwm(fan_pwm), .fan_tach(tach));
    defparam dut.dna_slow.u_dna.SIM_DNA_VALUE = 57'h0ABCDEF12345678;

    // AXI-Lite master: address and data at the same time (like the Zynq GP0 port), with a timeout
    task wr(input [15:0] a, input [31:0] d);
        integer t;
        begin
            @(posedge clk); awaddr <= a; wdata <= d; awvalid <= 1; wvalid <= 1; bready <= 1;
            t = 0;
            while (!(awready && wready) && t < 100) begin @(posedge clk); t = t + 1; end
            if (t >= 100) begin $display("ERROR: write 0x%h: no AWREADY/WREADY", a); errors = errors + 1; end
            awvalid <= 0; wvalid <= 0;
            t = 0;
            while (!bvalid && t < 100) begin @(posedge clk); t = t + 1; end
            if (t >= 100) begin $display("ERROR: write 0x%h: no BVALID", a); errors = errors + 1; end
            @(posedge clk); bready <= 0;
        end
    endtask
    task rd(input [15:0] a, output [31:0] d);
        integer t;
        begin
            @(posedge clk); araddr <= a; arvalid <= 1; rready <= 1;
            t = 0;
            @(posedge clk);
            while (!arready && t < 100) begin @(posedge clk); t = t + 1; end
            arvalid <= 0;
            t = 0;
            while (!rvalid && t < 100) begin @(posedge clk); t = t + 1; end
            if (t >= 100) begin $display("ERROR: read 0x%h: no RVALID", a); errors = errors + 1; end
            d = rdata;
            @(posedge clk); rready <= 0;
        end
    endtask
    task expect(input [255:0] what, input [31:0] got, input [31:0] want);
        begin
            if (got !== want) begin $display("ERROR: %0s = 0x%h, expected 0x%h", what, got, want); errors = errors + 1; end
            else $display("ok   : %0s = 0x%h", what, got);
        end
    endtask

    reg [31:0] v, v2, tidx, pre;
    integer i, n, edges, first;
    reg [63:0] s, prev;
    initial begin
        repeat (20) @(posedge clk);
        rstn = 1;
        repeat (5) @(posedge clk);

        rd(16'h0000, v); expect("ID", v, 32'h41525A32);
        rd(16'h003C, v); expect("CAPS", v, 32'h48311000);
        rd(16'h0008, v); expect("fan PERIOD reset", v, 32'd4000);

        // Device DNA (57 steps of 8 cycles)
        repeat (700) @(posedge clk);
        rd(16'h0034, v); expect("DNA_LO", v, 32'h12345678);
        rd(16'h0038, v); expect("DNA_HI", v, 32'h80ABCDEF);

        // GPIO pass-through: j1[0] (pin 0) output 0, read back
        g1o[0] = 0; g1t[0] = 0;
        repeat (4) @(posedge clk);
        expect("pin0 driven low", {31'd0, pins[0]}, 0);
        expect("gpio1_i[0]", {31'd0, g1i[0]}, 0);
        g1t[0] = 1;
        // board-ID pin 41 must stay an input even when GPIO and FUNC ask for an output
        g2o[9] = 0; g2t[9] = 0;
        wr(16'h0054, 32'h00000010);                 // FUNC5: pin 41 (k=1) = PWM0
        repeat (4) @(posedge clk);
        expect("board-ID pin 41 not driven", {31'd0, pins[41]}, 1);
        expect("board-ID pin 42 reads strap", {31'd0, g2i[10]}, 0);
        wr(16'h0054, 32'h0);
        g2t[9] = 1;

        // PWM0 on j2[1] (pin 5): period 100, high 25
        wr(16'h0060, 32'd100); wr(16'h0064, 32'd25);
        wr(16'h0040, 32'h00100000);                 // FUNC0: pin 5 = 1 (PWM0)
        // measuring channel 0 on pin 5, gate 1000 cycles
        wr(16'h00A0, 32'd5);
        wr(16'h0028, 32'd1000);
        repeat (2300) @(posedge clk);
        rd(16'h00A4, v);  expect("MEAS0 count (10 per 1000)", v, 32'd10);
        rd(16'h00A8, v);  expect("MEAS0 high cycles", v, 32'd250);
        rd(16'h00AC, v);  expect("MEAS0 period", v, 32'd100);
        rd(16'h012C, v2); rd(16'h0128, v);
        $display("info : LIVE = 0x%h_%h", v2, v);

        // UART loopback: TX on j1[1] (pin 1, FUNC 9), RX from signal 1, 16 cycles per bit
        wr(16'h0040, 32'h00100090);                 // pin 1 = UART TX, pin 5 = PWM0
        wr(16'h00E0, 32'h80010010);                 // enable, rx = 1, div 16
        wr(16'h00E4, 32'h55); wr(16'h00E4, 32'hA3); wr(16'h00E4, 32'h0F);
        rd(16'h00E4, v);  $display("info : TX free = %0d", v);
        repeat (700) @(posedge clk);
        rd(16'h00EC, v);  expect("UART RX waiting", v, 32'd3);
        rd(16'h00E8, v);  expect("UART RX byte 1", v, 32'h155);
        rd(16'h00E8, v);  expect("UART RX byte 2", v, 32'h1A3);
        rd(16'h00E8, v);  expect("UART RX byte 3", v, 32'h10F);
        rd(16'h00E8, v);  expect("UART RX empty", v, 32'h0);

        // logic analyzer: every cycle, 1000 samples before the trigger, trigger = rising edge of pin 5
        wr(16'h0104, 32'd0);
        wr(16'h0108, 32'd1000);
        wr(16'h010C, 32'h20); wr(16'h0110, 32'h0);
        wr(16'h0114, 32'h20); wr(16'h0118, 32'h0);
        wr(16'h011C, 32'd1);
        wr(16'h0100, 32'd1);
        repeat (5000) @(posedge clk);
        rd(16'h0100, v);  expect("LA done+triggered", v, 32'd6);
        rd(16'h0120, tidx);
        rd(16'h0108, pre);
        // trigger sample must be high, the one before low; count rising edges over the whole buffer
        rd(16'h8000 + 8 * tidx, v);              expect("LA trigger sample pin5", {31'd0, v[5]}, 1);
        rd(16'h8000 + 8 * ((tidx - 1) & 4095), v); expect("LA sample before trigger pin5", {31'd0, v[5]}, 0);
        edges = 0; first = (tidx - pre) & 4095;
        for (i = 0; i < 4096; i = i + 1) begin
            rd(16'h8000 + 8 * ((first + i) & 4095), v);
            rd(16'h8004 + 8 * ((first + i) & 4095), v2);
            s = {v2, v};
            if (i > 0 && s[5] && !prev[5]) edges = edges + 1;
            prev = s;
        end
        $display("info : LA rising edges of pin 5 in 4096 samples = %0d (expected about 40)", edges);
        if (edges < 39 || edges > 42) begin $display("ERROR: LA edge count"); errors = errors + 1; end

        // fan
        wr(16'h0004, 32'd1); wr(16'h0008, 32'd10); wr(16'h000C, 32'd3);
        rd(16'h000C, v);  expect("fan HIGH", v, 32'd3);

        if (errors == 0) $display("SIM_PASS");
        else $display("SIM_FAIL: %0d errors", errors);
        $finish;
    end
    initial begin #20000000; $display("SIM_FAIL: timeout"); $finish; end
endmodule
