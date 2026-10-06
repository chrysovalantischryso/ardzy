// Ardzy FPGA library: ardzy_quad, quadrature encoder counters (rotary encoders, motor encoders).
//
// N channels, each with inputs A and B. Every edge of A or B counts (4 counts per encoder line).
// A glitch filter takes a level only after it was stable for FILTER clocks.
// Registers, channel c at word 8*c:
//   +0 COUNT   position (signed); write sets it
//   +1 SPEED   counts in the last gate time (signed), see GATE
//   +2 ERRORS  impossible jumps (A and B changed together: too fast or noise)
//   +3 CFG     [0] reverse direction  [15:8] filter clocks (default 20 = 0.2 us)
// Global registers:
//   64 GATE    speed gate in clocks (default 10,000,000 = 0.1 s)
//   65 TEST    [0] internal generator feeds all counters (pins not used)
//              [1] the generator drives channel 0's pins A and B (pin test; nothing may be connected!)
//   66 GEN_PERIOD clocks between generator steps (default 1000 = 100,000 counts per second)
//   67 GEN_RUN write: [31] direction (1 = backwards), [30:0] steps to make (0 = run on); read: steps left
//   68 GEN_DONE (read) steps the generator made
//   69 ID      "QUAD"
`timescale 1ns / 1ps
module ardzy_quad #(parameter [3:0] SLOT = 4'd0, parameter N = 2) (
    input  wire         clk,
    input  wire         rstn,
    input  wire [15:0]  bus_addr,
    input  wire [31:0]  bus_wdata,
    input  wire         bus_we,
    input  wire         bus_re,
    output reg  [31:0]  bus_rdata = 32'd0,
    input  wire [N-1:0] a_in,
    input  wire [N-1:0] b_in,
    output wire         gen_a,             // generator outputs (driven onto channel 0's pins in pin test)
    output wire         gen_b,
    output wire         gen_drive          // 1 = drive channel 0's pins with the generator
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    reg [31:0] gate = 32'd10_000_000, gc = 32'd0;
    reg [1:0]  test = 2'd0;
    reg [31:0] gen_period = 32'd1000, gen_pc = 32'd0, gen_left = 32'd0, gen_done = 32'd0;
    reg        gen_dir = 1'b0, gen_free = 1'b0, gen_on = 1'b0;
    reg [1:0]  gen_ph = 2'd0;                   // (A,B) = 00 10 11 01: A leads = counting up
    assign gen_a = gen_ph[0] ^ gen_ph[1];
    assign gen_b = gen_ph[1];
    assign gen_drive = test[1];
    wire gate_tick = (gc == 32'd0);

    always @(posedge clk) begin
        gc <= (gc + 1'b1 >= gate) ? 32'd0 : gc + 1'b1;
        // generator: one quadrature step every gen_period clocks
        if (gen_on) begin
            if (gen_pc + 1'b1 >= gen_period) begin
                gen_pc <= 32'd0;
                gen_ph <= gen_dir ? gen_ph - 1'b1 : gen_ph + 1'b1;
                gen_done <= gen_done + 1'b1;
                if (!gen_free) begin
                    gen_left <= gen_left - 1'b1;
                    if (gen_left == 32'd1) gen_on <= 1'b0;
                end
            end else gen_pc <= gen_pc + 1'b1;
        end
        if (!rstn) begin
            gate <= 32'd10_000_000; test <= 2'd0; gen_period <= 32'd1000; gen_on <= 1'b0;
        end else if (bus_we && sel) case (idx)
            10'd64: gate <= (bus_wdata < 32'd1000) ? 32'd1000 : bus_wdata;
            10'd65: test <= bus_wdata[1:0];
            10'd66: gen_period <= (bus_wdata < 32'd4) ? 32'd4 : bus_wdata;
            10'd67: begin
                gen_dir <= bus_wdata[31]; gen_free <= (bus_wdata[30:0] == 0);
                gen_left <= {1'b0, bus_wdata[30:0]}; gen_on <= 1'b1; gen_pc <= 32'd0; gen_done <= 32'd0;
            end
            default: ;
        endcase
    end

    // counters
    wire [N*32-1:0] cnt_w, spd_w, err_w;
    wire [N*8-1:0]  flt_w;
    wire [N-1:0]    rev_w;
    genvar c;
    generate for (c = 0; c < N; c = c + 1) begin : ch
        reg [31:0] count = 32'd0, last = 32'd0, speed = 32'd0, errors = 32'd0;
        reg [7:0]  filter = 8'd20, fa = 8'd0, fb = 8'd0;
        reg        rev = 1'b0;
        reg [2:0]  sa = 3'd0, sb = 3'd0;
        reg        a = 1'b0, b = 1'b0, a0 = 1'b0, b0 = 1'b0, primed = 1'b0;
        wire ra = test[0] ? gen_a : a_in[c];
        wire rb = test[0] ? gen_b : b_in[c];
        always @(posedge clk) begin
            sa <= {sa[1:0], ra}; sb <= {sb[1:0], rb};
            // glitch filter
            if (sa[2] == a) fa <= 8'd0; else if (fa >= filter) begin a <= sa[2]; fa <= 8'd0; end else fa <= fa + 1'b1;
            if (sb[2] == b) fb <= 8'd0; else if (fb >= filter) begin b <= sb[2]; fb <= 8'd0; end else fb <= fb + 1'b1;
            a0 <= a; b0 <= b;
            primed <= 1'b1;
            if (primed && (a != a0) && (b != b0)) errors <= errors + 1'b1;
            else if (primed && ((a != a0) || (b != b0))) count <= ((a ^ b0) ^ rev) ? count + 1'b1 : count - 1'b1;
            if (gate_tick) begin speed <= count - last; last <= count; end
            if (bus_we && sel && idx == 8 * c) count <= bus_wdata;
            if (bus_we && sel && idx == 8 * c + 3) begin rev <= bus_wdata[0]; filter <= bus_wdata[15:8]; end
            if (!rstn) begin errors <= 32'd0; filter <= 8'd20; rev <= 1'b0; end
        end
        assign cnt_w[c*32 +: 32] = count;
        assign spd_w[c*32 +: 32] = speed;
        assign err_w[c*32 +: 32] = errors;
        assign flt_w[c*8 +: 8] = filter;
        assign rev_w[c] = rev;
    end endgenerate

    wire [2:0] rch = idx[5:3];
    always @(posedge clk) if (bus_re) begin
        if (!sel) bus_rdata <= 32'd0;
        else if (idx < 10'd64) begin
            if (rch >= N) bus_rdata <= 32'd0;
            else case (idx[2:0])
                3'd0: bus_rdata <= cnt_w[rch*32 +: 32];
                3'd1: bus_rdata <= spd_w[rch*32 +: 32];
                3'd2: bus_rdata <= err_w[rch*32 +: 32];
                3'd3: bus_rdata <= {16'd0, flt_w[rch*8 +: 8], 7'd0, rev_w[rch]};
                default: bus_rdata <= 32'd0;
            endcase
        end else case (idx)
            10'd64: bus_rdata <= gate;
            10'd65: bus_rdata <= {30'd0, test};
            10'd66: bus_rdata <= gen_period;
            10'd67: bus_rdata <= gen_on ? (gen_free ? 32'hFFFFFFFF : gen_left) : 32'd0;
            10'd68: bus_rdata <= gen_done;
            10'd69: bus_rdata <= 32'h51554144;              // "QUAD"
            default: bus_rdata <= 32'd0;
        endcase
    end
endmodule
