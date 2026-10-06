// Lesson 9: making and measuring frequencies. A divider makes a square wave on J1 pin 11; a counter at the pin
// itself (the pad, read back through the input buffer) counts its rising edges for exactly 1 second (the gate)
// = the frequency in Hz, and measures one period in clocks (10 ns each) for fine resolution at low frequencies.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    inout  wire       sig                   // J1 pin 11: an output we also read back at the pad
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: half period in clocks (frequency = 50 MHz / ctrl)
    wire [95:0] status;                     // 0: edges in the last second (Hz)  1: last period in clocks  2: gates done
    ardzy_soc #(.N_CTRL(1), .N_STAT(3)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    // the generator: toggle every ctrl clocks
    reg [31:0] div = 32'd0;
    reg out = 1'b0;
    wire [31:0] half = (ctrl == 32'd0) ? 32'd50_000 : ctrl;          // default 1 kHz
    always @(posedge clk) begin
        if (div + 1'b1 >= half) begin div <= 32'd0; out <= ~out; end
        else div <= div + 1'b1;
    end
    wire pad;                                            // the pin as its input buffer sees it
    IOBUF iob (.IO(sig), .I(out), .T(1'b0), .O(pad));    // T = 0: always driven, and read back at the pad

    reg p1 = 1'b0, p2 = 1'b0, p3 = 1'b0;                 // synchronizer + edge detector (lessons 3)
    always @(posedge clk) begin p1 <= pad; p2 <= p1; p3 <= p2; end
    wire rise = p2 & ~p3;

    // frequency: count edges during a 1-second gate
    reg [26:0] gate = 27'd0;
    reg [31:0] edges = 32'd0, hz = 32'd0, gates = 32'd0;
    always @(posedge clk) begin
        if (gate == 27'd99_999_999) begin
            gate <= 27'd0; hz <= edges + rise; edges <= 32'd0; gates <= gates + 1'b1;
        end else begin
            gate <= gate + 1'b1;
            if (rise) edges <= edges + 1'b1;
        end
    end
    // period: clocks between two rising edges
    reg [31:0] pc = 32'd0, period = 32'd0;
    always @(posedge clk) begin
        if (rise) begin period <= pc + 1'b1; pc <= 32'd0; end
        else if (pc != 32'hFFFFFFFF) pc <= pc + 1'b1;
    end
    assign status = {gates, period, hz};
    assign leds = ~{3'b000, (hz != 32'd0)};
endmodule
