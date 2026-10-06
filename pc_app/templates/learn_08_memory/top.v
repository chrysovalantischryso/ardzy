// Lesson 8: memory inside the FPGA (block RAM). 1024 words of 32 bits that the ARM writes and the FPGA plays
// back: a light show of up to 1024 steps. Each word: [3:0] the LEDs, [31:8] how many milliseconds to show them.
// A block RAM answers one clock after it is asked (it is synchronous): the design asks one step ahead.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [95:0] ctrl;                       // ctrl 0: [9:0] address  ctrl 1: data (writing it stores data at address)
                                            // ctrl 2: [9:0] number of steps to play, [31] play
    wire [95:0] status;                     // status 0: data read at the address  1: the step now  2: sum of all words
    ardzy_soc #(.N_CTRL(3), .N_STAT(3)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    (* ram_style = "block" *) reg [31:0] mem [0:1023];

    // port A: the ARM writes (when ctrl 1 changes) and reads at its address
    reg [31:0] data_last = 32'd0, rd_a = 32'd0;
    always @(posedge clk) begin
        data_last <= ctrl[63:32];
        if (ctrl[63:32] != data_last) mem[ctrl[9:0]] <= ctrl[63:32];
        rd_a <= mem[ctrl[9:0]];
    end

    // port B: the player while playing; when not playing it reads the memory round and round for a checksum
    reg [9:0]  step = 10'd0, sa = 10'd0;
    reg [31:0] rd_b = 32'd0;
    reg [31:0] ms_left = 32'd0;
    reg [16:0] ms_div = 17'd0;
    reg [3:0]  show = 4'd0;
    reg        loaded = 1'b0, s_valid = 1'b0;
    reg [31:0] sum = 32'd0, sum_done = 32'd0;
    wire       playing = ctrl[95];
    wire [9:0] steps = (ctrl[73:64] == 10'd0) ? 10'd1 : ctrl[73:64];
    always @(posedge clk) begin
        rd_b <= mem[playing ? step : sa];                   // the word asked for, 1 clock later
        ms_div <= (ms_div == 17'd99_999) ? 17'd0 : ms_div + 1'b1;
        if (!playing) begin
            step <= 10'd0; loaded <= 1'b0; ms_left <= 32'd0;
            // checksum: rd_b holds the word at sa - 1; at sa = 0 that is word 1023, the last one of a pass
            sa <= sa + 1'b1;
            s_valid <= 1'b1;
            if (s_valid) begin
                if (sa == 10'd0) begin sum_done <= sum + rd_b; sum <= 32'd0; end
                else sum <= sum + rd_b;
            end
        end else begin
            s_valid <= 1'b0; sa <= 10'd0; sum <= 32'd0;
            if (!loaded) loaded <= 1'b1;                    // wait the 1 clock for rd_b
            else if (ms_left == 32'd0) begin
                show <= rd_b[3:0];
                ms_left <= (rd_b[31:8] == 24'd0) ? 32'd1 : rd_b[31:8];
                step <= (step + 1'b1 >= steps) ? 10'd0 : step + 1'b1;
                loaded <= 1'b0;
            end else if (ms_div == 17'd0) ms_left <= ms_left - 1'b1;
        end
    end
    assign leds = ~show;
    assign status = {sum_done, 22'd0, step, rd_a};
endmodule
