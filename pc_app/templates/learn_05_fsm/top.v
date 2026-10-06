// Lesson 5: a state machine (FSM). A traffic light with a pedestrian button. The design is always in one of a
// few STATES; a timer and the button decide when it moves to the next one. LED 0 red, LED 1 yellow,
// LED 2 green, LED 3 "walk". The times are short (seconds) so you can watch it.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl[0]: the pedestrian presses the button (a pulse from the ARM)
    wire [63:0] status;                     // status 0: [2:0] the state, [3] someone waits  status 1: clocks left
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    localparam GREEN = 3'd0, YELLOW = 3'd1, RED = 3'd2, WALK = 3'd3, RED_YELLOW = 3'd4;
    reg [2:0] state = RED;
    reg [31:0] timer = 32'd0;               // clocks left in this state
    reg waiting = 1'b0;                     // someone pressed the button
    localparam SEC = 32'd100_000_000;

    reg btn_last = 1'b0;
    always @(posedge clk) begin
        btn_last <= ctrl[0];
        if (ctrl[0] && !btn_last) waiting <= 1'b1;          // remember a press (rising edge)

        if (timer != 32'd0) timer <= timer - 1'b1;
        else case (state)                                   // the timer ran out: where next?
            GREEN:      if (waiting) begin state <= YELLOW; timer <= 2 * SEC; end
            YELLOW:     begin state <= RED; timer <= 1 * SEC; end
            RED:        if (waiting) begin state <= WALK; timer <= 4 * SEC; waiting <= 1'b0; end
                        else begin state <= RED_YELLOW; timer <= 1 * SEC; end
            WALK:       begin state <= RED_YELLOW; timer <= 2 * SEC; end
            RED_YELLOW: begin state <= GREEN; timer <= 3 * SEC; end
            default:    state <= RED;
        endcase
    end

    reg [3:0] lamp;                                         // which lamps each state lights
    always @(*) case (state)
        GREEN:      lamp = 4'b0100;
        YELLOW:     lamp = 4'b0010;
        RED:        lamp = 4'b0001;
        WALK:       lamp = 4'b1001;
        RED_YELLOW: lamp = 4'b0011;
        default:    lamp = 4'b0001;
    endcase
    assign leds = ~lamp;
    assign status = {timer, 28'd0, waiting, state};       // (Python divides by 100 000 000 for seconds)
endmodule
