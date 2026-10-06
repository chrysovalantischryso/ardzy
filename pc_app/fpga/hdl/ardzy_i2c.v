// Ardzy FPGA library: ardzy_i2c, I2C controller (master) with a command queue.
//
// The ARM queues commands; the hardware runs them with exact timing and queues the results.
//   commands (CMD register, [10:8] = command, [7:0] = data):
//     1 START (or repeated start)   2 STOP   3 WRITE data (result: ACK or not)
//     4 READ, answer ACK (more bytes follow)   5 READ, answer NACK (the last byte)
//   results (RESULT register): [31] 1 = a result was there  [9] 1 = from a READ  [8] ACK received (WRITE)
//                              [7:0] the byte read
// Registers (word index):
//   0 CMD      write: queue a command (16 places)
//   1 RESULT   read: take the oldest result
//   2 STATUS   [4:0] commands waiting [12:8] results waiting [16] busy [17] SCL level [18] SDA level
//              [19] clock stretching timeout happened (write STATUS to clear)
//   3 DIV      quarter of an SCL period minus 1: 249 = 100 kHz, 61 = 400 kHz (403), 24 = 1 MHz
//   4 TIMEOUT  longest clock stretching in clocks (default 1,000,000 = 10 ms)
//   5 ID       "I2CM"
// Pins are open drain: scl_low / sda_low = 1 pulls the line low, else it is released (pull-ups).
`timescale 1ns / 1ps
module ardzy_i2c #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg         scl_low = 1'b0,
    output reg         sda_low = 1'b0,
    input  wire        scl_in,
    input  wire        sda_in
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];

    reg [10:0] cq [0:15];
    reg [9:0]  rq [0:15];
    reg [4:0]  cw = 5'd0, cr = 5'd0, rw = 5'd0, rr = 5'd0;
    wire [4:0] c_n = cw - cr, r_n = rw - rr;
    reg [15:0] div = 16'd249, qc = 16'd0;
    reg [31:0] tmo = 32'd1_000_000, sc = 32'd0;
    reg        tmo_err = 1'b0;
    reg [2:0]  ss = 3'b111, ds = 3'b111;
    always @(posedge clk) begin ss <= {ss[1:0], scl_in}; ds <= {ds[1:0], sda_in}; end
    wire scl = ss[2], sda = ds[2];

    localparam IDLE = 2'd0, START = 2'd1, BYTE = 2'd2, STOP = 2'd3;
    reg [1:0] st = IDLE, ph = 2'd0;
    reg [3:0] bitn = 4'd0;
    reg [7:0] sh = 8'd0;
    reg       rd = 1'b0, ack_out = 1'b0, ack_in = 1'b0;
    wire [10:0] cmd = cq[cr[3:0]];
    wire tick = (qc >= div);

    always @(posedge clk) begin
        qc <= (st == IDLE || tick) ? 16'd0 : qc + 1'b1;
        if (!rstn) begin
            st <= IDLE; scl_low <= 1'b0; sda_low <= 1'b0; div <= 16'd249; tmo <= 32'd1_000_000;
        end else case (st)
        IDLE: if (c_n != 0) begin
            cr <= cr + 1'b1; ph <= 2'd0; bitn <= 4'd0; sc <= 32'd0;
            case (cmd[10:8])
                3'd1: st <= START;
                3'd2: st <= STOP;
                3'd3: begin st <= BYTE; rd <= 1'b0; sh <= cmd[7:0]; end
                3'd4: begin st <= BYTE; rd <= 1'b1; ack_out <= 1'b1; sh <= 8'd0; end
                3'd5: begin st <= BYTE; rd <= 1'b1; ack_out <= 1'b0; sh <= 8'd0; end
                default: ;
            endcase
        end
        START: if (tick) case (ph)
            2'd0: begin sda_low <= 1'b0; ph <= 2'd1; end            // SDA up (for a repeated start)
            2'd1: begin scl_low <= 1'b0; ph <= 2'd2; end            // SCL up
            2'd2: if (scl) begin sda_low <= 1'b1; ph <= 2'd3; end   // SDA down while SCL is high = START
                  else if (sc >= tmo) begin tmo_err <= 1'b1; st <= IDLE; end else sc <= sc + div + 1'b1;
            2'd3: begin scl_low <= 1'b1; st <= IDLE; end
        endcase
        STOP: if (tick) case (ph)
            2'd0: if (!scl_low) st <= IDLE;                         // we do not hold the bus: nothing to stop
                  else begin sda_low <= 1'b1; ph <= 2'd1; end
            2'd1: begin scl_low <= 1'b0; ph <= 2'd2; end
            2'd2: if (scl) begin sda_low <= 1'b0; ph <= 2'd3; end   // SDA up while SCL is high = STOP
                  else if (sc >= tmo) begin tmo_err <= 1'b1; st <= IDLE; end else sc <= sc + div + 1'b1;
            2'd3: st <= IDLE;                                        // bus free time
        endcase
        BYTE: if (tick) case (ph)
            2'd0: begin                                              // SCL is low: put the bit on SDA
                if (bitn < 4'd8) sda_low <= rd ? 1'b0 : ~sh[7];
                else sda_low <= rd ? ack_out : 1'b0;                 // 9th bit: our ACK, or listen for theirs
                ph <= 2'd1;
            end
            2'd1: begin scl_low <= 1'b0; ph <= 2'd2; end
            2'd2: if (scl) begin                                     // SCL is high (device may stretch it)
                if (bitn < 4'd8) sh <= rd ? {sh[6:0], sda} : {sh[6:0], 1'b0};
                else ack_in <= ~sda;
                ph <= 2'd3; sc <= 32'd0;
            end else if (sc >= tmo) begin tmo_err <= 1'b1; scl_low <= 1'b1; sda_low <= 1'b0; st <= IDLE; end
            else sc <= sc + div + 1'b1;
            2'd3: begin
                scl_low <= 1'b1;
                ph <= 2'd0;
                if (bitn == 4'd8) begin
                    sda_low <= 1'b0;
                    st <= IDLE;
                    if (r_n != 5'd16) begin rq[rw[3:0]] <= {rd, rd ? 1'b0 : ack_in, rd ? sh : 8'd0}; rw <= rw + 1'b1; end
                end
                bitn <= bitn + 1'b1;
            end
        endcase
        endcase

        if (bus_we && sel) case (idx)
            10'd0: if (c_n != 5'd16) begin cq[cw[3:0]] <= bus_wdata[10:0]; cw <= cw + 1'b1; end
            10'd2: tmo_err <= 1'b0;
            10'd3: div <= (bus_wdata[15:0] < 16'd4) ? 16'd4 : bus_wdata[15:0];
            10'd4: tmo <= bus_wdata;
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd1: if (r_n != 0) begin bus_rdata <= {22'h200000, rq[rr[3:0]]}; rr <= rr + 1'b1; end
                       else bus_rdata <= 32'd0;
                10'd2: bus_rdata <= {12'd0, tmo_err, sda, scl, (st != IDLE) | (c_n != 0), 3'd0, r_n, 3'd0, c_n};
                10'd3: bus_rdata <= {16'd0, div};
                10'd4: bus_rdata <= tmo;
                10'd5: bus_rdata <= 32'h4932434D;          // "I2CM"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
