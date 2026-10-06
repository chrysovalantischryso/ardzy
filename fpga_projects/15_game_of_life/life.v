// 15 Game of Life: Conway's cellular automaton on a 64 x 64 grid that wraps around (a torus), in hardware.
//
// The rules, for every cell at the same time:  a live cell with 2 or 3 live neighbours stays alive,
// a dead cell with exactly 3 live neighbours is born, every other cell is dead in the next generation.
//
// How the FPGA does it: the grid is two banks of 64 rows x 64 bits (LUT RAM). A generation reads the old bank
// one row per clock and keeps three rows in registers (above, this one, below); 64 copies of the rule then make
// the whole new row at once, written into the other bank one clock later. 64 rows + 6 clocks = 70 clocks per
// generation: about 1.43 million generations per second. Then the banks swap.
//
// Registers (word index, slot SLOT):
//   0  CTRL       write: [0] clear the grid  [1] run (generations without end)  [2] fill at random  [3] sparse random
//   1  STATUS     read : [0] busy  [1] running
//   2  STEPS      write n: do n generations, then stop
//   3  GENERATION (r)    4  POPULATION (r) live cells after the last generation
//   5  RATE       clocks between generations while running (0 = as fast as it goes; 100000000 = 1 per second)
//   6  PER_SEC    (r) generations in the last second
//  64 + 2r, 65 + 2r   row r: bits 0..31 and 32..63 (bit n = column n); read and written while not busy
// 1023 ID "LIFE"
`timescale 1ns / 1ps
module life #(parameter [3:0] SLOT = 4'd1) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output wire        gen_led
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    (* ram_style = "distributed" *) reg [63:0] bank0 [0:63];
    (* ram_style = "distributed" *) reg [63:0] bank1 [0:63];
    reg cur = 1'b0;                                   // the bank that holds the grid now

    reg running = 1'b0;
    reg [31:0] steps = 32'd0, generation = 32'd0, population = 32'd0, rate = 32'd0, wait_c = 32'd0;
    reg [31:0] per_sec = 32'd0, gen_s = 32'd0, sec_c = 32'd0, pop = 32'd0;
    reg [31:0] la = 32'h1234ABCD, lb = 32'h9E3779B9;   // random bits for the fill
    reg sparse = 1'b0;
    // xorshift32: x ^= x << 13; x ^= x >> 17; x ^= x << 5 (a whole new random word per clock)
    function [31:0] xorshift(input [31:0] x);
        reg [31:0] y;
        begin y = x ^ (x << 13); y = y ^ (y >> 17); xorshift = y ^ (y << 5); end
    endfunction
    wire [31:0] xs_a = xorshift(la), xs_b = xorshift(lb);

    localparam S_IDLE = 3'd0, S_P0 = 3'd1, S_P1 = 3'd2, S_P2 = 3'd6, S_RUN = 3'd3, S_FLUSH = 3'd7, S_DONE = 3'd4, S_FILL = 3'd5;
    reg [2:0] st = S_IDLE;
    reg [5:0] r = 6'd0, wr_r = 6'd0;
    reg [63:0] above = 64'd0, here = 64'd0, below = 64'd0, next_r = 64'd0;
    reg        wr_v = 1'b0;
    reg fill_rand = 1'b0;
    wire busy = (st != S_IDLE);

    // one read address for the bank being read (the engine while busy, else the ARM's row)
    wire [5:0] arm_row = idx[6:1];
    reg  [5:0] ra;
    always @(*) begin
        case (st)
            S_P0: ra = 6'd63;
            S_P1: ra = 6'd0;
            S_P2: ra = 6'd1;
            S_RUN: ra = r + 2'd2;                     // read one row ahead: the row below the NEXT row (wraps)
            default: ra = arm_row;
        endcase
    end
    wire [63:0] rd = cur ? bank1[ra] : bank0[ra];

    // the rule for all 64 cells of the row at once
    reg [63:0] next_row;
    reg [3:0]  n;
    integer i;
    always @(*) begin
        for (i = 0; i < 64; i = i + 1) begin
            n = above[(i + 63) % 64] + above[i] + above[(i + 1) % 64]
              + here[(i + 63) % 64]               + here[(i + 1) % 64]
              + below[(i + 63) % 64] + below[i] + below[(i + 1) % 64];
            next_row[i] = (n == 4'd3) || (here[i] && n == 4'd2);
        end
    end
    // live cells in the row being written (one clock after it was made)
    reg [6:0] ones;
    always @(*) begin
        ones = 7'd0;
        for (i = 0; i < 64; i = i + 1) ones = ones + next_r[i];
    end

    always @(posedge clk) begin
        la <= xs_a;                                    // a new random word every clock
        lb <= xs_b;
        // generations per second
        if (sec_c == 32'd99_999_999) begin sec_c <= 32'd0; per_sec <= gen_s; gen_s <= 32'd0; end
        else sec_c <= sec_c + 1'b1;
        if (wait_c != 32'd0) wait_c <= wait_c - 1'b1;

        if (bus_we && sel) begin
            if (idx == 10'd0) begin
                running <= bus_wdata[1];
                if (bus_wdata[0] || bus_wdata[2]) begin
                    st <= S_FILL; r <= 6'd0; fill_rand <= bus_wdata[2]; sparse <= bus_wdata[3];
                    running <= 1'b0; steps <= 32'd0;
                end
            end
            if (idx == 10'd2) steps <= bus_wdata;
            if (idx == 10'd5) rate <= bus_wdata;
            // the ARM writes a row (only while nothing else changes the grid)
            if (!busy && idx >= 10'd64 && idx <= 10'd191) begin
                if (cur) bank1[arm_row] <= idx[0] ? {bus_wdata, rd[31:0]} : {rd[63:32], bus_wdata};   // (rd = this row now)
                else     bank0[arm_row] <= idx[0] ? {bus_wdata, rd[31:0]} : {rd[63:32], bus_wdata};
            end
        end

        // the write stage: the row made in the clock before goes into the other bank
        wr_v <= 1'b0;
        if (wr_v) begin
            if (cur) bank0[wr_r] <= next_r; else bank1[wr_r] <= next_r;
            pop <= pop + ones;
        end
        case (st)
            S_IDLE: if ((steps != 32'd0 || running) && wait_c == 32'd0 && !(bus_we && sel)) st <= S_P0;
            S_P0: begin above <= rd; st <= S_P1; end                  // row 63 is above row 0
            S_P1: begin here <= rd; st <= S_P2; end
            S_P2: begin below <= rd; r <= 6'd0; pop <= 32'd0; st <= S_RUN; end
            S_RUN: begin                                              // make row r from three registers
                next_r <= next_row;
                wr_r <= r;
                wr_v <= 1'b1;
                above <= here;
                here <= below;
                below <= rd;
                r <= r + 1'b1;
                if (r == 6'd63) st <= S_FLUSH;
            end
            S_FLUSH: st <= S_DONE;                                    // (the last row is written now)
            S_DONE: begin
                cur <= !cur;
                generation <= generation + 1'b1;
                gen_s <= gen_s + 1'b1;
                population <= pop;
                if (steps != 32'd0) steps <= steps - 1'b1;
                wait_c <= rate;
                st <= S_IDLE;
            end
            S_FILL: begin
                if (cur) bank1[r] <= fill_rand ? (sparse ? {la & lb, {la[15:0], lb[31:16]} & {lb[15:0], la[31:16]}} : {la, lb}) : 64'd0;
                else     bank0[r] <= fill_rand ? (sparse ? {la & lb, {la[15:0], lb[31:16]} & {lb[15:0], la[31:16]}} : {la, lb}) : 64'd0;
                r <= r + 1'b1;
                if (r == 6'd63) begin st <= S_IDLE; generation <= 32'd0; population <= 32'd0; end
            end
            default: st <= S_IDLE;
        endcase
        if (!rstn) begin st <= S_IDLE; running <= 1'b0; steps <= 32'd0; end
    end

    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx >= 10'd64 && idx <= 10'd191) bus_rdata <= busy ? 32'd0 : (idx[0] ? rd[63:32] : rd[31:0]);
        else case (idx)
            10'd1: bus_rdata <= {30'd0, running, busy};
            10'd2: bus_rdata <= steps;
            10'd3: bus_rdata <= generation;
            10'd4: bus_rdata <= population;
            10'd5: bus_rdata <= rate;
            10'd6: bus_rdata <= per_sec;
            10'd1023: bus_rdata <= 32'h4C494645;          // "LIFE"
            default: bus_rdata <= 32'd0;
        endcase
    end
    assign gen_led = generation[16];
endmodule
