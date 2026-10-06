// Lesson 7: serial data, a UART. One wire carries bytes one bit after the other: a start bit (0), 8 data
// bits (lowest first), a stop bit (1). Both sides agree on the speed (baud rate). Here a transmitter sends what
// the ARM writes, out of J1 pin 11 (TXD), and a receiver reads J1 pin 12 (RXD), or the transmitter itself
// (loopback) when nothing is connected. Received bytes wait in a small FIFO for the ARM.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    output wire       txd,                  // J1 pin 11
    input  wire       rxd                   // J1 pin 12 (pull-up)
);
    wire clk, rstn;
    wire [63:0] ctrl;                       // ctrl 0: [7:0] a byte to send (write = send)   ctrl 1: clocks per bit, [31] loopback
    wire [63:0] status;                     // status 0: [7:0] oldest received byte, [15:8] bytes waiting, [16] sending
    ardzy_soc #(.N_CTRL(2), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));
    wire [15:0] bit_clocks = (ctrl[47:32] < 16'd16) ? 16'd868 : ctrl[47:32];   // 868 = 100 MHz / 115200
    wire loopback = ctrl[63];

    // ---- transmitter: a shift register of 10 bits and a bit timer
    reg [9:0]  tx_shift = 10'h3FF;
    reg [3:0]  tx_left = 4'd0;
    reg [15:0] tx_timer = 16'd0;
    reg [31:0] last_ctrl0 = 32'd0;
    reg [31:0] sent = 32'd0;
    always @(posedge clk) begin
        last_ctrl0 <= ctrl[31:0];
        if (tx_left == 4'd0 && ctrl[31:0] != last_ctrl0) begin      // the ARM wrote a byte
            tx_shift <= {1'b1, ctrl[7:0], 1'b0};                     // stop, data (LSB first), start
            tx_left <= 4'd10;
            tx_timer <= bit_clocks;
        end else if (tx_left != 4'd0) begin
            if (tx_timer == 16'd1) begin
                tx_shift <= {1'b1, tx_shift[9:1]};                   // next bit
                tx_left <= tx_left - 1'b1;
                tx_timer <= bit_clocks;
                if (tx_left == 4'd1) sent <= sent + 1'b1;
            end else tx_timer <= tx_timer - 1'b1;
        end
    end
    assign txd = tx_shift[0];

    // ---- receiver: wait for a start bit, sample each bit in its middle
    wire line = loopback ? txd : rxd;
    reg r1 = 1'b1, r2 = 1'b1;               // synchronizer (lesson 3)
    always @(posedge clk) begin r1 <= line; r2 <= r1; end
    reg [3:0]  rx_n = 4'd0;
    reg [15:0] rx_timer = 16'd0;
    reg [7:0]  rx_byte = 8'd0;
    reg        rx_busy = 1'b0, rx_done = 1'b0;
    always @(posedge clk) begin
        rx_done <= 1'b0;
        if (!rx_busy) begin
            if (!r2) begin rx_busy <= 1'b1; rx_timer <= bit_clocks + (bit_clocks >> 1); rx_n <= 4'd0; end
        end else if (rx_timer != 16'd0) rx_timer <= rx_timer - 1'b1;
        else if (rx_n < 4'd8) begin
            rx_byte <= {r2, rx_byte[7:1]};                           // LSB first
            rx_n <= rx_n + 1'b1;
            rx_timer <= bit_clocks - 1'b1;
        end else begin
            rx_busy <= 1'b0;                                         // (this is the stop bit)
            rx_done <= r2;                                           // a byte only if the stop bit is 1
        end
    end

    // ---- a 16-byte FIFO for the ARM; reading status 0 takes the oldest byte (the ARM writes ctrl 1 [30] to pop)
    reg [7:0] fifo [0:15];
    reg [4:0] wp = 5'd0, rp = 5'd0;
    reg pop_last = 1'b0;
    always @(posedge clk) begin
        pop_last <= ctrl[62];
        if (rx_done && (wp - rp) != 5'd16) begin fifo[wp[3:0]] <= rx_byte; wp <= wp + 1'b1; end
        if (ctrl[62] && !pop_last && wp != rp) rp <= rp + 1'b1;
    end
    wire [4:0] level = wp - rp;
    assign status = {sent, 15'd0, (tx_left != 4'd0), 3'd0, level, (level != 0) ? fifo[rp[3:0]] : 8'd0};
    assign leds = ~{2'b00, rx_busy, tx_left != 4'd0};
endmodule
