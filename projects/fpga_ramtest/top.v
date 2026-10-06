`timescale 1ns / 1ps
// fpga_ramtest: block RAM shapes on the real XC7Z010 with Ardzy's open toolchain.
// Each tester fills a memory with a hash of the address, reads everything back and counts errors.
// Status 0x4120_0080: magic "RAMT"; 0x84: done flags (bit n = tester n finished);
// 0x88 + 4n: errors of tester n (0 = this RAM shape works).
module top (output wire [3:0] leds);
    wire clk, rstn;
    localparam N = 11;
    wire [32*1-1:0] ctrl;
    wire [32*(N+2)-1:0] status;
    ardzy_soc #(.N_CTRL(1), .N_STAT(N + 2)) u_soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));
    wire [N-1:0] done;
    wire [32*N-1:0] errs;
    // the ARM starts a run: write ctrl0 bit 0 = 1 (a new 0 -> 1 starts the test again)
    reg [1:0] go_q = 0;
    always @(posedge clk) go_q <= {go_q[0], ctrl[0]};
    wire start = go_q[0] & ~go_q[1];
    //                                depth      x width
    rt_ram #(.AW(12), .DW(32)) t0  (clk, start, done[0],  errs[0*32 +: 32]);   // 4096 x 32  (the failing case)
    rt_ram #(.AW(12), .DW(9))  t1  (clk, start, done[1],  errs[1*32 +: 32]);   // 4096 x 9
    rt_ram #(.AW(11), .DW(9))  t2  (clk, start, done[2],  errs[2*32 +: 32]);   // 2048 x 9   (RAMB18 x9)
    rt_ram #(.AW(10), .DW(18)) t3  (clk, start, done[3],  errs[3*32 +: 32]);   // 1024 x 18  (RAMB18 x18)
    rt_ram #(.AW(10), .DW(36)) t4  (clk, start, done[4],  errs[4*32 +: 32]);   // 1024 x 36  (RAMB36 x36)
    rt_ram #(.AW(11), .DW(18)) t5  (clk, start, done[5],  errs[5*32 +: 32]);   // 2048 x 18  (RAMB36 x18)
    rt_ram #(.AW(9),  .DW(72)) t6  (clk, start, done[6],  errs[6*32 +: 32]);   // 512 x 72   (RAMB36 SDP)
    rt_ram #(.AW(15), .DW(1))  t7  (clk, start, done[7],  errs[7*32 +: 32]);   // 32768 x 1  (RAMB36 x1)
    rt_ram #(.AW(14), .DW(2))  t8  (clk, start, done[8],  errs[8*32 +: 32]);   // 16384 x 2  (RAMB36 x2)
    rt_ram #(.AW(13), .DW(4))  t9  (clk, start, done[9],  errs[9*32 +: 32]);   // 8192 x 4   (RAMB36 x4)
    rt_ram #(.AW(13), .DW(16)) t10 (clk, start, done[10], errs[10*32 +: 32]);  // 8192 x 16  (several RAMs)
    assign status = {errs, {{(32-N){1'b0}}, done}, 32'h52414D54};
    assign leds = ~{&done, 3'b000};
endmodule

module rt_ram #(parameter AW = 10, parameter DW = 32) (input wire clk, input wire start,
                                                       output reg done = 1'b0, output reg [31:0] errs = 0);
    (* ram_style = "block" *) reg [DW-1:0] mem [0:(1 << AW) - 1];
    reg [AW-1:0] wa = 0, ra = 0, ca1 = 0, ca2 = 0;
    reg [DW-1:0] wd = 0, rd = 0;
    reg we = 1'b0, cv1 = 1'b0, cv2 = 1'b0, phase = 1'b0, run = 1'b0;
    reg [AW:0] i = 0;
    always @(posedge clk) begin
        if (we) mem[wa] <= wd;
        rd <= mem[ra];
    end
    function [DW-1:0] pat(input [AW-1:0] a);
        reg [95:0] h;
        begin
            h = {a * 32'h9E3779B1, a * 32'h85EBCA77 ^ 32'h5A5A5A5A, a * 32'hC2B2AE3D ^ {a, 4'h3}};
            pat = h[DW-1:0];
        end
    endfunction
    always @(posedge clk) begin
        we <= 1'b0; cv1 <= 1'b0;
        cv2 <= cv1; ca2 <= ca1;
        // errs = [31:16] first wrong address, [15:0] number of wrong words
        if (cv2 && rd != pat(ca2) && errs[15:0] != 16'hFFFF) begin
            errs[15:0] <= errs[15:0] + 1'b1;
            if (errs[15:0] == 0) errs[31:16] <= ca2;
        end
        if (start) begin
            run <= 1'b1; phase <= 1'b0; i <= 0; done <= 1'b0; errs <= 0;
        end else if (!run) begin
        end else if (!phase) begin
            we <= 1'b1; wa <= i[AW-1:0]; wd <= pat(i[AW-1:0]);
            i <= i + 1'b1;
            if (i[AW-1:0] == {AW{1'b1}}) begin phase <= 1'b1; i <= 0; end
        end else if (!i[AW]) begin
            ra <= i[AW-1:0]; ca1 <= i[AW-1:0]; cv1 <= 1'b1;
            i <= i + 1'b1;
        end else if (!cv1 && !cv2) begin
            done <= 1'b1; run <= 1'b0;
        end
    end
endmodule
