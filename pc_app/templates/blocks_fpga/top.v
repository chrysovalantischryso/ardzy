// __NAME__: an FPGA design made with Ardzy blocks. Open the Blocks view to make it.
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    ardzy_clock u_clock (.clk(clk), .rstn(rstn));
    assign leds = 4'hF;
endmodule
