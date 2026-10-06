// top: 4 LEDs set by the ARM. main.py writes register 0 at 0x4120_0000 (the LEDs are active low,
// main.py inverts the pattern). Registers from the Ardzy library (ardzy_soc):
//   ctrl  0x4120_0000 + 4*n  (written by the ARM)     status  0x4120_0080 + 4*n  (read by the ARM)
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [63:0] ctrl;                 // 2 registers
    reg  [31:0] seconds = 0;
    reg  [26:0] tick = 0;
    ardzy_soc #(.N_CTRL(2), .N_STAT(1)) u_soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(seconds));
    assign leds = ctrl[3:0];
    always @(posedge clk) begin        // status 0: seconds since the design was loaded
        if (tick == 27'd99_999_999) begin tick <= 0; seconds <= seconds + 1'b1; end
        else tick <= tick + 1'b1;
    end
endmodule
