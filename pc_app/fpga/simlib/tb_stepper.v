`timescale 1ns / 1ps
// Testbench: one move of ardzy_stepper axis 0; prints the speed profile.
module tb_stepper;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;
    reg  [15:0] addr = 0;
    reg  [31:0] wdata = 0;
    reg         we = 0, re = 0;
    wire [31:0] rdata;
    wire [1:0]  so, dir;
    ardzy_stepper #(.SLOT(1), .N(2)) dut (.clk(clk), .rstn(rstn), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we),
        .bus_re(re), .bus_rdata(rdata), .step_out(so), .dir_out(dir), .step_in(so));
    task wr(input [9:0] r, input [31:0] v);
        begin @(posedge clk); addr <= 16'h1000 | (r << 2); wdata <= v; we <= 1; @(posedge clk); we <= 0; end
    endtask
    // 20000 steps/s max, 4,000,000 steps/s^2 (fast, to keep the simulation short), start 500 steps/s
    localparam [39:0] VMAX = 40'd21990232556;
    initial begin
        repeat (5) @(posedge clk);
        rstn <= 1;
        wr(2, VMAX[31:0]); wr(3, VMAX[39:32]);
        wr(4, 32'd4398047);           // 4e6 * 2^40 / 1e12
        wr(5, 32'd549755814);         // 500 steps/s
        wr(0, 32'd200);               // target 200
        repeat (12_000_000) @(posedge clk);
        $display("END pos=%0d moving=%0d", $signed(dut.ax[0].pos), dut.ax[0].moving);
        $finish;
    end
    // print every 1000 us
    integer us = 0;
    always @(posedge clk) if (dut.tick) begin
        us = us + 1;
        if (us % 500 == 0 || (dut.ax[0].moving && dut.ax[0].s_slow && us % 50 == 0))
            $display("%6d us pos=%0d inc=%0d acc=%0d slow=%0d low=%0d below=%0d decel=%0d moving=%0d remle0=%0d rema=%0d",
                     us, $signed(dut.ax[0].pos), dut.ax[0].inc, dut.ax[0].acc_steps, dut.ax[0].s_slow, dut.ax[0].s_low,
                     dut.ax[0].s_below, dut.ax[0].decel, dut.ax[0].moving, dut.ax[0].s_remle0, dut.ax[0].s_rema);
    end
endmodule
