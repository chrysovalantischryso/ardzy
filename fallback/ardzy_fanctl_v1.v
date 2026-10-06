// ardzy_fanctl: AXI4-Lite peripheral for the Ardzy "pin control" design.
//   - PWM output for the 6 fan headers (pin J18, shared)
//   - 6 edge counters on the fan speed inputs (also usable as frequency counters)
//   - a free-running clock counter, so software can measure the real FCLK0 frequency
//
// Registers (byte offsets, 32 bit):
//   0x00 ID       read-only  0x41525A31 ("ARZ1")
//   0x04 CTRL     bit0 = PWM on (off: output held high = fans at full speed), bit1 = invert
//   0x08 PERIOD   PWM period in clock cycles (reset: 4000 = 25 kHz at 100 MHz)
//   0x0C HIGH     PWM high time in clock cycles (reset: 4000 = 100 %)
//   0x10..0x24    TACH0..5 read-only: rising edges counted in the last gate window
//   0x28 GATE     gate window in clock cycles (reset: 100,000,000 = 1 s at 100 MHz)
//   0x2C WINDOWS  read-only: number of completed gate windows
//   0x30 CYCLES   read-only: free-running clock cycle counter
module ardzy_fanctl (
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,
    input  wire [5:0]  s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [5:0]  s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,
    output wire        fan_pwm,
    input  wire [5:0]  fan_tach
);
    localparam [31:0] ID = 32'h41525A31;
    wire clk = s_axi_aclk;
    wire rst = ~s_axi_aresetn;

    reg [1:0]  ctrl;
    reg [31:0] period, high, gate;
    reg [31:0] cycles, windows, gate_cnt, pwm_cnt;
    reg [31:0] tach_cnt [0:5];
    reg [31:0] tach_val [0:5];
    reg [5:0]  t_s1, t_s2, t_s3;          // input synchronizers + previous value

    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;

    // ---------------- write channel (same handshake pattern as the Xilinx AXI4-Lite template:
    // ready is raised once both address and data are valid, the register is written on the
    // handshake edge, and BVALID follows one clock later)
    reg aw_en;
    wire w_hs = s_axi_awready && s_axi_awvalid && s_axi_wready && s_axi_wvalid;
    always @(posedge clk) begin
        if (rst) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0; aw_en <= 1'b1;
            ctrl <= 2'b00; period <= 32'd4000; high <= 32'd4000; gate <= 32'd100_000_000;
        end else begin
            if (!s_axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
                s_axi_awready <= 1'b1; s_axi_wready <= 1'b1; aw_en <= 1'b0;
            end else begin
                s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            end
            if (w_hs) begin
                case (s_axi_awaddr[5:2])
                    4'h1: ctrl   <= s_axi_wdata[1:0];
                    4'h2: period <= (s_axi_wdata < 32'd2) ? 32'd2 : s_axi_wdata;
                    4'h3: high   <= s_axi_wdata;
                    4'hA: gate   <= (s_axi_wdata < 32'd1000) ? 32'd1000 : s_axi_wdata;
                    default: ;
                endcase
            end
            if (w_hs && !s_axi_bvalid)
                s_axi_bvalid <= 1'b1;
            else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0; aw_en <= 1'b1;
            end
        end
    end

    // ---------------- read channel (address latched on its handshake, RVALID one clock later)
    reg [5:0] rd_addr;
    always @(posedge clk) begin
        if (rst) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rdata <= 32'd0; rd_addr <= 6'd0;
        end else begin
            if (!s_axi_arready && s_axi_arvalid && !s_axi_rvalid) begin
                s_axi_arready <= 1'b1; rd_addr <= s_axi_araddr;
            end else
                s_axi_arready <= 1'b0;
            if (s_axi_arready && s_axi_arvalid && !s_axi_rvalid) begin
                case (rd_addr[5:2])
                    4'h0: s_axi_rdata <= ID;
                    4'h1: s_axi_rdata <= {30'd0, ctrl};
                    4'h2: s_axi_rdata <= period;
                    4'h3: s_axi_rdata <= high;
                    4'h4: s_axi_rdata <= tach_val[0];
                    4'h5: s_axi_rdata <= tach_val[1];
                    4'h6: s_axi_rdata <= tach_val[2];
                    4'h7: s_axi_rdata <= tach_val[3];
                    4'h8: s_axi_rdata <= tach_val[4];
                    4'h9: s_axi_rdata <= tach_val[5];
                    4'hA: s_axi_rdata <= gate;
                    4'hB: s_axi_rdata <= windows;
                    4'hC: s_axi_rdata <= cycles;
                    default: s_axi_rdata <= 32'd0;
                endcase
                s_axi_rvalid <= 1'b1;
            end else if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
        end
    end

    // ---------------- PWM
    always @(posedge clk) begin
        if (rst || pwm_cnt >= period - 1) pwm_cnt <= 32'd0;
        else                              pwm_cnt <= pwm_cnt + 1'b1;
    end
    wire pwm_raw = ctrl[0] ? (pwm_cnt < high) : 1'b1;
    assign fan_pwm = pwm_raw ^ ctrl[1];

    // ---------------- counters
    integer i;
    wire gate_end = (gate_cnt >= gate - 1);
    always @(posedge clk) begin
        cycles <= rst ? 32'd0 : cycles + 1'b1;
        t_s1 <= fan_tach; t_s2 <= t_s1; t_s3 <= t_s2;
        if (rst) begin
            gate_cnt <= 32'd0; windows <= 32'd0;
            for (i = 0; i < 6; i = i + 1) begin tach_cnt[i] <= 32'd0; tach_val[i] <= 32'd0; end
        end else begin
            gate_cnt <= gate_end ? 32'd0 : gate_cnt + 1'b1;
            if (gate_end) windows <= windows + 1'b1;
            for (i = 0; i < 6; i = i + 1) begin
                if (gate_end) begin
                    tach_val[i] <= tach_cnt[i] + (t_s2[i] & ~t_s3[i]);
                    tach_cnt[i] <= 32'd0;
                end else if (t_s2[i] & ~t_s3[i])
                    tach_cnt[i] <= tach_cnt[i] + 1'b1;
            end
        end
    end
endmodule
