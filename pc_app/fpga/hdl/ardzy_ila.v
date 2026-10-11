// ardzy_ila: the signal analyzer inside the FPGA (like Vivado's ILA).
// The Ardzy build adds it when signals of the design carry (* mark_debug *) (or are named in fpga.json "debug"):
// every tick of the chosen clock it keeps one sample of them in block RAM, around a trigger.
// The ARM reads it through EMIO GPIO (no AXI bus needed, so it works with every design):
//   ctl  = EMIO GPIO 16..31 (bank 2, from the ARM): a command each time ctl[15] changes:
//          ctl[14:12] what, ctl[11:0] value:
//          0 read address, 1 word to read (7 = status), 2 shift a trigger byte in (mask bytes, then value bytes,
//          most significant first), 3 samples before the trigger, 4 trigger mode, 5 arm (1) / stop (0)
//   dout = EMIO GPIO 32..63 (bank 3, to the ARM): [31] the last command seen + 31 bits of the chosen sample word
//          (word k = sample bits 31k .. 31k+30), so the ARM knows the answer belongs to its command; or the status:
//          [31] last command seen, [30] armed, [29] triggered, [28] done, [27:16] trigger address,
//          [15:12] log2 of the depth, [11:8] 4'hA (an analyzer is there), [7:0] sample width
// Trigger modes: 0 at once, 1 while (probe & mask) == value, 2 when it becomes equal, 3 when a masked bit changes.
module ardzy_ila #(parameter W = 8, parameter AW = 10) (
    input wire          sclk,          // the design's clock: one sample per tick
    input wire [W-1:0]  probe,
    input wire          fclk,          // the ARM's clock FCLK0: the control side
    input wire [15:0]   ctl,
    output reg [31:0]   dout
);
    localparam D  = 1 << AW;
    localparam TB = ((W + 7) / 8) * 8;              // trigger value / mask bits (whole bytes)
    localparam [3:0] AW4 = AW;
    localparam [7:0] W8 = W;

    // ---------------- control side (fclk)
    reg [15:0] c1 = 16'd0, c2 = 16'd0;              // two flip-flops against metastability
    reg        ack = 1'b0, arm_f = 1'b0;
    reg [AW-1:0] raddr = 0, pre = 0;
    reg [2:0]  wsel = 3'd7;
    reg [1:0]  mode = 2'd0;
    reg [2*TB-1:0] tsr = 0;
    always @(posedge fclk) begin
        c1 <= ctl; c2 <= c1;
        if (c2[15] != ack && c1 == c2) begin           // a new command (and the bits have settled)
            ack <= c2[15];
            case (c2[14:12])
                3'd0: raddr <= c2[AW-1:0];
                3'd1: wsel  <= c2[2:0];
                3'd2: tsr   <= {tsr[2*TB-9:0], c2[7:0]};
                3'd3: pre   <= c2[AW-1:0];
                3'd4: mode  <= c2[1:0];
                3'd5: arm_f <= c2[0];
                default: ;
            endcase
        end
    end
    wire [W-1:0] tval  = tsr[W-1:0];
    wire [W-1:0] tmask = tsr[TB+W-1:TB];

    // ---------------- capture side (sclk)
    reg [2:0]  as = 3'd0;
    always @(posedge sclk) as <= {as[1:0], arm_f};
    wire arm = as[2];
    reg        arm_d = 1'b0, first = 1'b1, trig = 1'b0, done = 1'b0;
    reg [AW-1:0] wptr = 0, tptr = 0;
    reg [AW:0] cnt = 0;
    reg [W-1:0] prev = 0;
    reg [1:0]  mode_s = 2'd0;
    reg [AW-1:0] pre_s = 0;
    wire match  = ((probe ^ tval) & tmask) == {W{1'b0}};
    wire pmatch = ((prev ^ tval) & tmask) == {W{1'b0}};
    reg hit;
    always @(*) case (mode_s)
        2'd0: hit = 1'b1;
        2'd1: hit = match;
        2'd2: hit = match && !pmatch && !first;
        default: hit = (((probe ^ prev) & tmask) != {W{1'b0}}) && !first;
    endcase
    reg [W-1:0] mem [0:D-1];
    wire run = arm && arm_d && !done;
    always @(posedge sclk) if (run) mem[wptr] <= probe;
    always @(posedge sclk) begin
        arm_d <= arm;
        mode_s <= mode;                             // (set before arming: steady while armed, except "trigger now")
        if (arm && !arm_d) begin
            wptr <= 0; cnt <= 0; trig <= 1'b0; done <= 1'b0; first <= 1'b1; pre_s <= pre;
        end else if (run) begin
            wptr <= wptr + 1'b1;
            prev <= probe; first <= 1'b0;
            if (!trig) begin
                if (cnt < pre_s) cnt <= cnt + 1'b1;          // first the samples before the trigger
                else if (hit) begin
                    trig <= 1'b1; tptr <= wptr; cnt <= 1;
                    if (D - pre_s == 1) done <= 1'b1;
                end
            end else begin
                cnt <= cnt + 1'b1;
                if (cnt == D - pre_s - 1) done <= 1'b1;
            end
        end
    end

    // ---------------- read side (fclk): the second port of the block RAM
    reg [W-1:0] rd;
    always @(posedge fclk) rd <= mem[raddr];
    reg [2:0] ds = 3'd0, ts = 3'd0;
    always @(posedge fclk) begin ds <= {ds[1:0], done}; ts <= {ts[1:0], trig}; end
    wire [31*7-1:0] rdp = {{(31*7-W){1'b0}}, rd};
    wire [11:0] tp = tptr;
    reg ack_d = 1'b0;                               // (lines up with rd: one tick after a new read address)
    always @(posedge fclk) begin
        ack_d <= ack;
        dout <= wsel == 3'd7 ? {ack, arm_f, ts[2], ds[2], tp, AW4, 4'hA, W8} : {ack_d, rdp[wsel*31 +: 31]};
    end
endmodule
