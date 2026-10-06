// Ardzy FPGA library: ardzy_sensors, three sensor helpers in hardware.
//
//  * HC-SR04 ultrasonic distance: a 10 us TRIG pulse every PERIOD, the ECHO pulse is timed in us.
//    distance in mm = echo_us * 343 / 2000 (sound at 20 C). ECHO is 5 V on the HC-SR04: use a divider!
//  * IR remote, NEC protocol (most cheap remotes; receiver like VS1838B / TSOP38238, output low = light):
//    address, command, repeat codes.
//  * Capacitive touch: the pin is pulled low, let go, and the time until it reads high is counted
//    (a 1 Mohm resistor from the pin to 3.3 V, a wire or a coin as the touch pad). A finger adds time.
// Registers (word index):
//   0 CTRL        [0] distance measuring on  [1] echo simulator (no sensor needed)  [2] touch on
//                 [3] IR test: an IR transmitter inside sends TEST_CODE to the decoder
//   1 PERIOD      clocks between distance measurements (default 6,000,000 = 60 ms)
//   2 ECHO_US     (read) last echo length in us (0 = no echo: out of range)
//   3 DIST_MM     (read) distance in mm
//   4 RANGINGS    (read) measurements done           5 TIMEOUTS (read) measurements without an echo
//   6 SIM_US      echo simulator: echo length in us
//   7 IR_CODE     (read) last NEC code: [7:0] address [15:8] ~address [23:16] command [31:24] ~command
//   8 IR_COUNT    (read) codes received   9 IR_REPEATS (read) repeat codes   10 IR_ERRORS (read)
//  11 TEST_CODE   code the IR test sends (write starts sending it once)
//  12 TOUCH_RAW   (read) charge time now, clocks (average of 8)
//  13 TOUCH_BASE  (read) the untouched level (follows slowly)
//  14 TOUCHED     (read) [0] touched now  [31:8] touches counted
//  15 TOUCH_DIFF  clocks above the base that mean "touched" (default 20)
//  16 ID          "SENS"
`timescale 1ns / 1ps
module ardzy_sensors #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg         trig = 1'b0,
    input  wire        echo,
    input  wire        ir,                  // demodulated IR, low = light
    output reg         touch_low = 1'b0,    // 1 = pull the touch pin low (discharge)
    input  wire        touch_in
);
    wire sel = (bus_addr[15:12] == SLOT);
    wire [9:0] idx = bus_addr[11:2];
    reg [3:0]  ctrl = 4'b0000;
    reg [6:0]  us_c = 7'd0;
    wire us = (us_c == 7'd99);
    always @(posedge clk) us_c <= us ? 7'd0 : us_c + 1'b1;

    // ---------------- HC-SR04
    reg [31:0] period = 32'd6_000_000, pcnt = 32'd0;
    reg [15:0] sim_us = 16'd1000, sim_c = 16'd0;
    reg        sim_echo = 1'b0, measuring = 1'b0, sim_wait = 1'b0;
    reg [2:0]  es = 3'd0;
    reg [15:0] e_us = 16'd0, echo_us = 16'd0, wait_us = 16'd0;
    reg [31:0] rangings = 32'd0, timeouts = 32'd0, dist_mm = 32'd0;
    wire e = ctrl[1] ? sim_echo : es[2];
    reg  e0 = 1'b0;
    always @(posedge clk) begin
        es <= {es[1:0], echo};
        e0 <= e;
        if (ctrl[0]) begin
            if (pcnt + 1'b1 >= period) pcnt <= 32'd0; else pcnt <= pcnt + 1'b1;
            trig <= (pcnt < 32'd1000);                                // 10 us trigger
            if (pcnt == 32'd1000) begin measuring <= 1'b1; e_us <= 16'd0; wait_us <= 16'd0; sim_wait <= 1'b1; sim_c <= 16'd0; end
        end else begin trig <= 1'b0; measuring <= 1'b0; end
        // echo simulator: echo starts 50 us after the trigger and lasts SIM_US
        if (sim_wait && us) begin
            sim_c <= sim_c + 1'b1;
            if (sim_c == 16'd50) sim_echo <= 1'b1;
            if (sim_c == 16'd50 + sim_us) begin sim_echo <= 1'b0; sim_wait <= 1'b0; end
        end
        if (measuring && us) begin
            if (e) begin
                e_us <= e_us + 1'b1;
                if (e_us == 16'd38000) begin measuring <= 1'b0; timeouts <= timeouts + 1'b1; echo_us <= 16'd0; end   // longer than any real echo
            end
            else if (e_us == 16'd0) begin
                wait_us <= wait_us + 1'b1;
                if (wait_us == 16'd30000) begin measuring <= 1'b0; timeouts <= timeouts + 1'b1; echo_us <= 16'd0; end
            end
        end
        if (measuring && e0 && !e) begin                              // echo ended
            measuring <= 1'b0; echo_us <= e_us; rangings <= rangings + 1'b1;
            dist_mm <= (e_us * 32'd11239) >> 16;                         // * 0.1715 = mm
        end
    end

    // ---------------- IR NEC decoder (times in us)
    reg [2:0]  is = 3'b111;
    reg        il = 1'b0;            // light (1 = IR seen)
    reg [15:0] ic = 16'd0;           // us since the last change
    reg [2:0]  ist = 3'd0;           // 0 idle 1 leader mark 2 leader space 3 bit mark 4 bit space
    reg [31:0] ish = 32'd0, icode = 32'd0, icount = 32'd0, irep = 32'd0, ierr = 32'd0;
    reg [5:0]  ibits = 6'd0;
    // IR test transmitter: makes the light pattern of one NEC frame
    reg [31:0] tcode = 32'h00FF00FF, tsh = 32'd0;
    reg        tx_on = 1'b0, tx_light = 1'b0;
    reg [2:0]  tst = 3'd0;
    reg [15:0] tcnt = 16'd0;
    reg [5:0]  tbits = 6'd0;
    wire light = ctrl[3] ? tx_light : il;
    reg  light0 = 1'b0;
    always @(posedge clk) begin
        is <= {is[1:0], ir};
        il <= ~is[2];
        light0 <= light;
        if (light != light0) begin
            // an edge: judge the time of the part that just ended
            case (ist)
                3'd0: if (light) ist <= 3'd1;
                3'd1: if (ic > 16'd8000 && ic < 16'd10000) ist <= 3'd2; else ist <= light ? 3'd1 : 3'd0;
                3'd2: if (ic > 16'd4000 && ic < 16'd5000) begin ist <= 3'd3; ibits <= 6'd0; end
                      else if (ic > 16'd1800 && ic < 16'd2700) begin irep <= irep + 1'b1; ist <= 3'd0; end
                      else begin ierr <= ierr + 1'b1; ist <= 3'd0; end
                3'd3: if (ic > 16'd350 && ic < 16'd800) ist <= 3'd4; else begin ierr <= ierr + 1'b1; ist <= 3'd0; end
                3'd4: begin
                    if (ic > 16'd350 && ic < 16'd800 || ic > 16'd1400 && ic < 16'd1900) begin
                        ish <= {ic > 16'd1100, ish[31:1]};                // LSB first
                        if (ibits == 6'd31) begin
                            icode <= {ic > 16'd1100, ish[31:1]}; icount <= icount + 1'b1; ist <= 3'd0;
                        end else begin ibits <= ibits + 1'b1; ist <= 3'd3; end
                    end else begin ierr <= ierr + 1'b1; ist <= 3'd0; end
                end
                default: ist <= 3'd0;
            endcase
            ic <= 16'd0;
        end else if (us && ic != 16'hFFFF) begin
            ic <= ic + 1'b1;
            if (ist != 3'd0 && ic > 16'd12000) ist <= 3'd0;              // nothing for 12 ms: start over
        end
        // transmitter: 9 ms light, 4.5 ms dark, 32 bits (560 us light + 560 or 1690 us dark), 560 us light
        if (tx_on && us) begin
            tcnt <= tcnt + 1'b1;
            case (tst)
                3'd0: begin tx_light <= 1'b1; if (tcnt == 16'd8999) begin tst <= 3'd1; tcnt <= 16'd0; end end
                3'd1: begin tx_light <= 1'b0; if (tcnt == 16'd4499) begin tst <= 3'd2; tcnt <= 16'd0; tbits <= 6'd0; end end
                3'd2: begin tx_light <= 1'b1; if (tcnt == 16'd559) begin tst <= 3'd3; tcnt <= 16'd0; end end
                3'd3: begin
                    tx_light <= 1'b0;
                    if (tbits == 6'd32) begin tx_on <= 1'b0; tst <= 3'd0; end
                    else if (tcnt == (tsh[0] ? 16'd1689 : 16'd559)) begin
                        tsh <= tsh >> 1; tbits <= tbits + 1'b1; tst <= 3'd2; tcnt <= 16'd0;
                    end
                end
                default: tst <= 3'd0;
            endcase
        end
        if (bus_we && sel && idx == 10'd11) begin tcode <= bus_wdata; tsh <= bus_wdata; tx_on <= 1'b1; tst <= 3'd0; tcnt <= 16'd0; tx_light <= 1'b0; end
    end

    // ---------------- capacitive touch: 10 us discharge, then count until the pin reads high
    reg [2:0]  ts = 3'd0;
    reg [1:0]  tph = 2'd0;
    reg [15:0] tc = 16'd0;
    reg [18:0] tsum = 19'd0;
    reg [2:0]  tn = 3'd0;
    reg [15:0] raw = 16'd0, base = 16'd0, tdiff = 16'd20;
    reg [23:0] touches = 24'd0;
    reg        touched = 1'b0, base_ok = 1'b0;
    reg [9:0]  slowc = 10'd0;
    always @(posedge clk) begin
        ts <= {ts[1:0], touch_in};
        if (!ctrl[2]) begin touch_low <= 1'b0; tph <= 2'd0; end
        else case (tph)
            2'd0: begin touch_low <= 1'b1; tc <= 16'd0; tph <= 2'd1; end
            2'd1: if (tc == 16'd1000) begin touch_low <= 1'b0; tc <= 16'd0; tph <= 2'd2; end else tc <= tc + 1'b1;
            2'd2: if (ts[2] || tc == 16'd60000) begin
                      tsum <= tsum + tc; tn <= tn + 1'b1;
                      if (tn == 3'd7) begin
                          raw <= (tsum + tc) >> 3; tsum <= 19'd0;
                          if (!base_ok) begin base <= (tsum + tc) >> 3; base_ok <= 1'b1; end
                      end
                      tph <= 2'd0;
                  end else tc <= tc + 1'b1;
            default: tph <= 2'd0;
        endcase
        // touched? the base follows slowly while not touched
        if (raw > base + tdiff) begin if (!touched) touches <= touches + 1'b1; touched <= 1'b1; end
        else if (raw < base + (tdiff >> 1)) touched <= 1'b0;
        slowc <= slowc + 1'b1;
        if (us && slowc == 10'd0 && !touched && base_ok) base <= (raw > base) ? base + 1'b1 : (raw < base ? base - 1'b1 : base);
    end

    always @(posedge clk) begin
        if (!rstn) begin ctrl <= 4'd0; period <= 32'd6_000_000; end
        else if (bus_we && sel) case (idx)
            10'd0: ctrl <= bus_wdata[3:0];
            10'd1: period <= (bus_wdata < 32'd100_000) ? 32'd100_000 : bus_wdata;
            10'd6: sim_us <= bus_wdata[15:0];
            10'd15: tdiff <= bus_wdata[15:0];
            default: ;
        endcase
        if (bus_re) begin
            if (!sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {28'd0, ctrl};
                10'd1: bus_rdata <= period;
                10'd2: bus_rdata <= {16'd0, echo_us};
                10'd3: bus_rdata <= dist_mm;
                10'd4: bus_rdata <= rangings;
                10'd5: bus_rdata <= timeouts;
                10'd6: bus_rdata <= {16'd0, sim_us};
                10'd7: bus_rdata <= icode;
                10'd8: bus_rdata <= icount;
                10'd9: bus_rdata <= irep;
                10'd10: bus_rdata <= ierr;
                10'd11: bus_rdata <= tcode;
                10'd12: bus_rdata <= {16'd0, raw};
                10'd13: bus_rdata <= {16'd0, base};
                10'd14: bus_rdata <= {touches, 7'd0, touched};
                10'd15: bus_rdata <= {16'd0, tdiff};
                10'd16: bus_rdata <= 32'h53454E53;         // "SENS"
                default: bus_rdata <= 32'd0;
            endcase
        end
    end
endmodule
