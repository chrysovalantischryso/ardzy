// __NAME__: Python sets the EBAZ4205's LEDs and header pin DATA1-5 through FPGA registers.
// Press Build FPGA, then Upload (the FPGA design first, then main.py starts).
// Registers (Ardzy library, ardzy_soc):  ctrl  0x4120_0000 + 4*n (written by the ARM)
//                                        status 0x4120_0080 + 4*n (read by the ARM)
// Your pins: pins.xdc (every pin of the board: ardzy_pins.xdc). The Ethernet is kept by the Ardzy build.
module top (
    output wire led_green_n,
    output wire led_red_n,
    output wire data1_5
);
    wire clk, rstn;
    wire [31:0] ctrl;                  // 1 register: bit 0 green, bit 1 red, bit 2 DATA1-5
    reg  [31:0] seconds = 0;
    reg  [26:0] tick = 0;
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) u_soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(seconds));
    assign led_green_n = ~ctrl[0];     // the LEDs are on when the pin is 0
    assign led_red_n = ~ctrl[1];
    assign data1_5 = ctrl[2];
    always @(posedge clk) begin        // status 0: seconds since the design was loaded
        if (tick == 27'd99_999_999) begin tick <= 0; seconds <= seconds + 1'b1; end
        else tick <= tick + 1'b1;
    end
endmodule
