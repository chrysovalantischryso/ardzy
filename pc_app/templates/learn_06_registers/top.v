// Lesson 6: registers on the bus. The ARM and the FPGA talk through memory addresses: writing 0x4120_0000
// changes a register in the FPGA, reading 0x4120_0080 reads a value the FPGA makes. Here: a small calculator.
// The ARM writes A and B, the FPGA answers at once with A+B, A-B, A*B (a hardware multiplier), the larger one,
// A AND B and a count of how many times A was written.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [63:0]  ctrl;                      // ctrl 0 = A (0x4120_0000), ctrl 1 = B (0x4120_0004)
    wire [255:0] status;                    // 8 results at 0x4120_0080 .. 0x4120_009C
    ardzy_soc #(.N_CTRL(2), .N_STAT(8)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire [31:0] a = ctrl[31:0];
    wire [31:0] b = ctrl[63:32];
    reg  [63:0] product = 64'd0;            // registered: the multiplier needs a clock
    always @(posedge clk) product <= a * b;

    reg [31:0] writes = 32'd0;              // count changes of A
    reg [31:0] a_last = 32'd0;
    always @(posedge clk) begin
        a_last <= a;
        if (a != a_last) writes <= writes + 1'b1;
    end

    assign status = {32'h4C524547,          // 7: "LREG", the design's name
                     writes,                // 6: how often A changed
                     a & b,                 // 5: bitwise AND
                     (a > b) ? a : b,       // 4: the larger one (unsigned)
                     product[63:32],        // 3: A*B, high 32 bits
                     product[31:0],         // 2: A*B, low 32 bits
                     a - b,                 // 1
                     a + b};                // 0
    assign leds = ~a[3:0];                  // A's lowest 4 bits on the LEDs
endmodule
