// Ardzy FPGA library: ardzy_pattern, digital pattern generator (the opposite of a logic analyzer).
//
// Plays a table of up to 1024 steps on W pins (default 16), one step every DIV+1 clocks
// (100 MHz / (DIV+1): up to 100 million steps per second).
// Slots: SLOT = registers, SLOT+1 = the table (word n = pin levels of step n, bit k = pin k).
// Registers (word index):
//   0 CTRL      write: [0] run (1 = start from step 0, 0 = stop)  [1] loop (repeat the table)
//               read:  [0] running  [1] loop
//   1 LENGTH    steps in the table, 1..1024
//   2 DIV       clocks per step minus 1 (0 = 10 ns steps, 99 = 1 us steps)
//   3 OE        output enable, bit k = pin k is an output (0 = input, the pin floats)
//   4 IDLE      pin levels when stopped
//   5 STEP      (read) the step being played
//   6 LOOPS     (read) how many times the table was played to the end
//   7 MISMATCH  (read) steps where an output pin did not show the level it should (read back at the pad)
//   8 INPUTS    (read) the pins' levels now
//   9 ID        (read) "PATG"
`timescale 1ns / 1ps
module ardzy_pattern #(parameter [3:0] SLOT = 4'd0, parameter W = 16) (
    input  wire         clk,
    input  wire         rstn,
    input  wire [15:0]  bus_addr,
    input  wire [31:0]  bus_wdata,
    input  wire         bus_we,
    input  wire         bus_re,
    output reg  [31:0]  bus_rdata = 32'd0,
    output reg  [W-1:0] pin_out = {W{1'b0}},
    output reg  [W-1:0] pin_oe = {W{1'b0}},          // 1 = drive the pin
    input  wire [W-1:0] pin_in
);
    wire reg_sel = (bus_addr[15:12] == SLOT);
    wire tab_sel = (bus_addr[15:12] == SLOT + 4'd1);
    wire [9:0] idx = bus_addr[11:2];

    // pipeline: step -> table read (q, qv) -> pins (pin_out, pv); qv/pv say "this came from the table"
    (* ram_style = "block" *) reg [W-1:0] tab [0:1023];
    reg [9:0]  step = 10'd0;
    reg [W-1:0] q = {W{1'b0}};
    reg        run = 1'b0, loop = 1'b0, qv = 1'b0, pv = 1'b0;
    always @(posedge clk) begin
        if (bus_we && tab_sel) tab[idx] <= bus_wdata[W-1:0];
        q <= tab[step];
        qv <= run;
    end

    reg [10:0] length = 11'd1024;
    reg [31:0] div = 32'd0, dc = 32'd0;
    reg [W-1:0] oe = {W{1'b0}}, idle = {W{1'b0}};
    reg [31:0] loops = 32'd0, mismatch = 32'd0;
    reg [W-1:0] in1 = 0, in2 = 0, o1 = 0, o2 = 0, o3 = 0;
    reg        r1 = 1'b0, r2 = 1'b0, r3 = 1'b0;

    always @(posedge clk) begin
        pin_oe <= oe;
        pin_out <= qv ? q : idle;
        pv <= qv;
        // the pads, two clocks later: compare with what was driven (only stable table outputs)
        in1 <= pin_in; in2 <= in1;
        o1 <= pin_out; o2 <= o1; o3 <= o2;
        r1 <= pv; r2 <= r1; r3 <= r2;
        if (r2 && r3 && o2 == o3 && ((in2 ^ o2) & oe) != 0) mismatch <= mismatch + 1'b1;

        if (!rstn) begin
            run <= 1'b0; loop <= 1'b0; length <= 11'd1024; div <= 32'd0; oe <= 0; idle <= 0;
        end else begin
            if (run) begin
                if (dc >= div) begin
                    dc <= 32'd0;
                    if (step + 1'b1 >= length) begin
                        loops <= loops + 1'b1;
                        if (loop) step <= 10'd0;
                        else run <= 1'b0;
                    end else step <= step + 1'b1;
                end else dc <= dc + 1'b1;
            end
            if (bus_we && reg_sel) case (idx)
                10'd0: begin
                    loop <= bus_wdata[1];
                    if (bus_wdata[0]) begin run <= 1'b1; step <= 10'd0; dc <= 32'd0; mismatch <= 32'd0; loops <= 32'd0; end
                    else run <= 1'b0;
                end
                10'd1: length <= (bus_wdata[10:0] == 0) ? 11'd1 : (bus_wdata[10:0] > 11'd1024 ? 11'd1024 : bus_wdata[10:0]);
                10'd2: div <= bus_wdata;
                10'd3: oe <= bus_wdata[W-1:0];
                10'd4: idle <= bus_wdata[W-1:0];
                default: ;
            endcase
        end
        if (bus_re) begin
            if (!reg_sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {30'd0, loop, run};
                10'd1: bus_rdata <= {21'd0, length};
                10'd2: bus_rdata <= div;
                10'd3: bus_rdata <= oe;
                10'd4: bus_rdata <= idle;
                10'd5: bus_rdata <= {22'd0, step};
                10'd6: bus_rdata <= loops;
                10'd7: bus_rdata <= mismatch;
                10'd8: bus_rdata <= in2;
                10'd9: bus_rdata <= 32'h50415447;          // "PATG"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
