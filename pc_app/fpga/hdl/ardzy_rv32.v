// Ardzy FPGA library: ardzy_rv32, a small RISC-V processor (RV32I, the base integer instructions).
//
// Multi-cycle (about 5 clocks per instruction: about 20 million instructions per second at 100 MHz).
// Every RV32I instruction except the system ones: ECALL and EBREAK stop the processor (halted),
// FENCE does nothing, CSR instructions and unknown codes stop it with "illegal".
// Memory interface: the core holds mem_valid with mem_addr (and mem_wstrb / mem_wdata for a store)
// until mem_ready; for a load mem_rdata is the word at mem_addr (the core picks the byte / half).
`timescale 1ns / 1ps
module ardzy_rv32 #(parameter [31:0] RESET_PC = 32'h0000_0000) (
    input  wire        clk,
    input  wire        rst,                 // 1 = hold at the reset address
    output reg         mem_valid = 1'b0,
    output reg  [31:0] mem_addr = 32'd0,
    output reg  [31:0] mem_wdata = 32'd0,
    output reg  [3:0]  mem_wstrb = 4'd0,    // 0 = read
    input  wire [31:0] mem_rdata,
    input  wire        mem_ready,
    output reg  [31:0] pc = RESET_PC,
    output reg         halted = 1'b0,
    output reg         illegal = 1'b0,
    output reg  [31:0] retired = 32'd0      // instructions done
);
    localparam FETCH = 3'd0, DECODE = 3'd1, EXEC = 3'd2, MEM = 3'd3, HALT = 3'd4;
    reg [2:0]  st = FETCH;
    reg [31:0] ir = 32'd0;
    reg [31:0] rf [0:31];
    integer i;
    initial for (i = 0; i < 32; i = i + 1) rf[i] = 32'd0;

    // instruction fields
    wire [6:0] op = ir[6:0];
    wire [4:0] rd = ir[11:7], rs1 = ir[19:15], rs2 = ir[24:20];
    wire [2:0] f3 = ir[14:12];
    wire       f7b = ir[30];
    wire [31:0] imm_i = {{20{ir[31]}}, ir[31:20]};
    wire [31:0] imm_s = {{20{ir[31]}}, ir[31:25], ir[11:7]};
    wire [31:0] imm_b = {{19{ir[31]}}, ir[31], ir[7], ir[30:25], ir[11:8], 1'b0};
    wire [31:0] imm_u = {ir[31:12], 12'd0};
    wire [31:0] imm_j = {{11{ir[31]}}, ir[31], ir[19:12], ir[20], ir[30:21], 1'b0};

    // DECODE registers the operands; EXEC computes
    reg [31:0] a = 32'd0, b = 32'd0;
    reg [31:0] imm;
    always @(*) begin
        case (op)
            7'b0100011: imm = imm_s;
            7'b1100011: imm = imm_b;
            7'b0110111, 7'b0010111: imm = imm_u;
            7'b1101111: imm = imm_j;
            default: imm = imm_i;
        endcase
    end
    reg [31:0] immr = 32'd0;

    // ALU (register-register or register-immediate)
    wire is_imm = (op == 7'b0010011);
    wire [31:0] y = is_imm ? immr : b;
    wire [4:0]  sh = y[4:0];
    // the arithmetic shift on its own: inside a ?: with an unsigned operand Verilog would make it unsigned
    // (a logical shift) - found by the self-test against the simulator
    wire signed [31:0] a_s = a;
    wire [31:0] sra_v = a_s >>> sh;
    reg  [31:0] alu;
    always @(*) begin
        case (f3)
            3'd0: alu = (!is_imm && f7b) ? a - y : a + y;
            3'd1: alu = a << sh;
            3'd2: alu = ($signed(a) < $signed(y)) ? 32'd1 : 32'd0;
            3'd3: alu = (a < y) ? 32'd1 : 32'd0;
            3'd4: alu = a ^ y;
            3'd5: alu = f7b ? sra_v : (a >> sh);
            3'd6: alu = a | y;
            default: alu = a & y;
        endcase
    end
    reg take;
    always @(*) begin
        case (f3)
            3'd0: take = (a == b);
            3'd1: take = (a != b);
            3'd4: take = ($signed(a) < $signed(b));
            3'd5: take = ($signed(a) >= $signed(b));
            3'd6: take = (a < b);
            3'd7: take = (a >= b);
            default: take = 1'b0;
        endcase
    end
    wire [31:0] maddr = a + immr;
    wire [1:0]  boff = maddr[1:0];

    // load data: pick the byte / half from the word
    wire [31:0] lw = mem_rdata >> {mem_addr[1:0], 3'b000};
    reg  [31:0] ld;
    always @(*) begin
        case (f3)
            3'd0: ld = {{24{lw[7]}}, lw[7:0]};
            3'd1: ld = {{16{lw[15]}}, lw[15:0]};
            3'd4: ld = {24'd0, lw[7:0]};
            3'd5: ld = {16'd0, lw[15:0]};
            default: ld = mem_rdata;
        endcase
    end

    // register write port: results in EXEC, load data in MEM
    reg        rf_we;
    reg [31:0] rf_wd;
    always @(*) begin
        rf_we = 1'b0;
        rf_wd = alu;
        if (st == EXEC) case (op)
            7'b0110111: begin rf_we = 1'b1; rf_wd = immr; end                  // LUI
            7'b0010111: begin rf_we = 1'b1; rf_wd = pc + immr; end             // AUIPC
            7'b1101111, 7'b1100111: begin rf_we = 1'b1; rf_wd = pc + 32'd4; end // JAL, JALR
            7'b0010011, 7'b0110011: begin rf_we = 1'b1; rf_wd = alu; end      // ALU
            default: ;
        endcase
        else if (st == MEM && mem_ready && mem_wstrb == 4'd0) begin rf_we = 1'b1; rf_wd = ld; end
        if (rd == 5'd0 || rst) rf_we = 1'b0;
    end
    always @(posedge clk) if (rf_we) rf[rd] <= rf_wd;

    always @(posedge clk) begin
        if (rst) begin
            st <= FETCH; pc <= RESET_PC; halted <= 1'b0; illegal <= 1'b0; mem_valid <= 1'b0; retired <= 32'd0;
        end else case (st)
        FETCH: begin
            if (!mem_valid) begin mem_valid <= 1'b1; mem_addr <= pc; mem_wstrb <= 4'd0; end
            else if (mem_ready) begin mem_valid <= 1'b0; ir <= mem_rdata; st <= DECODE; end
        end
        DECODE: begin
            a <= rf[rs1]; b <= rf[rs2]; immr <= imm;
            st <= EXEC;
        end
        EXEC: begin
            st <= FETCH;
            retired <= retired + 1'b1;
            case (op)
                7'b0110111, 7'b0010111: pc <= pc + 4;                               // LUI, AUIPC
                7'b1101111: pc <= pc + immr;                                        // JAL
                7'b1100111: pc <= (a + immr) & ~32'd1;                              // JALR
                7'b1100011: pc <= take ? pc + immr : pc + 4;                        // branches
                7'b0010011, 7'b0110011: pc <= pc + 4;                               // ALU
                7'b0000011: begin                                                   // loads
                    mem_valid <= 1'b1; mem_addr <= maddr; mem_wstrb <= 4'd0; st <= MEM;
                end
                7'b0100011: begin                                                   // stores
                    mem_valid <= 1'b1; mem_addr <= maddr;
                    case (f3)
                        3'd0: begin mem_wstrb <= 4'b0001 << boff; mem_wdata <= {4{b[7:0]}}; end
                        3'd1: begin mem_wstrb <= boff[1] ? 4'b1100 : 4'b0011; mem_wdata <= {2{b[15:0]}}; end
                        default: begin mem_wstrb <= 4'b1111; mem_wdata <= b; end
                    endcase
                    st <= MEM;
                end
                7'b0001111: pc <= pc + 4;                                           // FENCE
                7'b1110011: begin halted <= 1'b1; illegal <= (f3 != 3'd0); st <= HALT; end   // ECALL / EBREAK / CSR
                default: begin halted <= 1'b1; illegal <= 1'b1; st <= HALT; end
            endcase
        end
        MEM: if (mem_ready) begin
            mem_valid <= 1'b0;
            pc <= pc + 4;
            st <= FETCH;
        end
        default: ;                                                                   // HALT
        endcase
    end
endmodule

// The RISC-V computer: core + 16 KB RAM + peripherals, controlled by the ARM over ardzy_bus.
//   ARM side: slot SLOT registers, slots SLOT+1 .. SLOT+4 = the 16 KB RAM (4096 words) for programs and data.
//     0 CTRL     [0] run (0 = hold in reset; 0 -> 1 starts the program at address 0)
//     1 STATUS   (read) [0] running [1] halted [2] illegal instruction
//     2 PC       (read) program counter
//     3 CONSOLE  read: one character the program printed ([31] = 1 if there was one, [7:0] the character)
//     4 CON_LEVEL (read) characters waiting
//     5 MAIL_IN  write: a value the program can read (0x80000014)
//     6 MAIL_OUT (read) the value the program wrote (0x80000018)
//     7 RETIRED  (read) instructions done since the start
//     8 GPIO     (read) [3:0] the program's GPIO outputs [11:8] LEDs
//     9 ID       "RV32"
//   Program side (addresses the RISC-V uses):
//     0x0000_0000 .. 0x0000_3FFF RAM (the program starts at 0, the stack can start at 0x4000)
//     0x8000_0000 LEDS (write, 4 bits)          0x8000_0004 GPIO_OUT (write, 4 bits)
//     0x8000_0008 GPIO_IN (read, 4 bits)        0x8000_000C CYCLES (read, 100 MHz counter)
//     0x8000_0010 CONSOLE (write one character) 0x8000_0014 MAIL_IN (read)
//     0x8000_0018 MAIL_OUT (write)              0x8000_001C MICROS (read, microseconds)
module ardzy_rv32_system #(parameter [3:0] SLOT = 4'd0) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [15:0] bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    input  wire        bus_re,
    output reg  [31:0] bus_rdata = 32'd0,
    output reg  [3:0]  leds = 4'd0,
    output reg  [3:0]  gpio_out = 4'd0,
    input  wire [3:0]  gpio_in
);
    wire reg_sel = (bus_addr[15:12] == SLOT);
    wire ram_sel = (bus_addr[15:12] > SLOT) && (bus_addr[15:12] <= SLOT + 4'd4);
    wire [11:0] ram_a = {bus_addr[15:12] - SLOT - 4'd1, bus_addr[11:2]};
    wire [9:0] idx = bus_addr[11:2];

    reg run = 1'b0;
    wire core_rst = !run || !rstn;
    wire mv, halted, illegal;
    wire [31:0] ma, mwd, pc, retired;
    wire [3:0] mws;
    reg [31:0] mrd = 32'd0;
    reg mrdy = 1'b0;
    ardzy_rv32 u_core (.clk(clk), .rst(core_rst), .mem_valid(mv), .mem_addr(ma), .mem_wdata(mwd), .mem_wstrb(mws),
                       .mem_rdata(mrd), .mem_ready(mrdy), .pc(pc), .halted(halted), .illegal(illegal), .retired(retired));

    // 16 KB RAM: port A = processor (byte writes), port B = ARM
    (* ram_style = "block" *) reg [31:0] ram [0:4095];
    reg [31:0] qa = 32'd0, qb = 32'd0;
    wire core_ram = (ma[31:14] == 18'd0);
    always @(posedge clk) begin
        if (mv && core_ram && !mrdy) begin
            if (mws[0]) ram[ma[13:2]][7:0] <= mwd[7:0];
            if (mws[1]) ram[ma[13:2]][15:8] <= mwd[15:8];
            if (mws[2]) ram[ma[13:2]][23:16] <= mwd[23:16];
            if (mws[3]) ram[ma[13:2]][31:24] <= mwd[31:24];
        end
        qa <= ram[ma[13:2]];
    end
    always @(posedge clk) begin
        if (bus_we && ram_sel) ram[ram_a] <= bus_wdata;
        qb <= ram[ram_a];
    end

    // peripherals
    reg [31:0] cycles = 32'd0, micros = 32'd0, mail_in = 32'd0, mail_out = 32'd0;
    reg [6:0]  uc = 7'd0;
    reg [3:0]  gi1 = 4'd0, gi2 = 4'd0;
    (* ram_style = "distributed" *) reg [7:0] con [0:255];
    reg [8:0]  cw = 9'd0, cr = 9'd0;
    wire [8:0] con_n = cw - cr;
    // memory answers one clock after the request (RAM read latency); mrdy is a one-clock pulse
    reg pend = 1'b0;
    reg [31:0] io_q = 32'd0;
    always @(posedge clk) begin
        cycles <= cycles + 1'b1;
        if (uc == 7'd99) begin uc <= 7'd0; micros <= micros + 1'b1; end else uc <= uc + 1'b1;
        gi1 <= gpio_in; gi2 <= gi1;
        mrdy <= 1'b0;
        if (mv && !mrdy && !pend) begin
            pend <= 1'b1;
            if (!core_ram) begin
                if (mws != 4'd0) case (ma[5:2])
                    4'd0: leds <= mwd[3:0];
                    4'd1: gpio_out <= mwd[3:0];
                    4'd4: if (con_n != 9'd256) begin con[cw[7:0]] <= mwd[7:0]; cw <= cw + 1'b1; end
                    4'd6: mail_out <= mwd;
                    default: ;
                endcase
                case (ma[5:2])
                    4'd0: io_q <= {28'd0, leds};
                    4'd1: io_q <= {28'd0, gpio_out};
                    4'd2: io_q <= {28'd0, gi2};
                    4'd3: io_q <= cycles;
                    4'd5: io_q <= mail_in;
                    4'd6: io_q <= mail_out;
                    4'd7: io_q <= micros;
                    default: io_q <= 32'd0;
                endcase
            end
        end else if (pend) begin
            pend <= 1'b0; mrdy <= 1'b1;
            mrd <= core_ram ? qa : io_q;
        end
        if (core_rst) begin pend <= 1'b0; mrdy <= 1'b0; end

        if (bus_re && reg_sel && idx == 10'd3 && con_n != 0) cr <= cr + 1'b1;      // the ARM took a character
        if (!rstn) begin run <= 1'b0; end
        else if (bus_we && reg_sel) case (idx)
            10'd0: begin run <= bus_wdata[0]; if (bus_wdata[0] && !run) begin cr <= cw; end end
            10'd5: mail_in <= bus_wdata;
            default: ;
        endcase
    end

    reg rd_ram = 1'b0;
    always @(posedge clk) begin
        rd_ram <= bus_re && ram_sel;
        if (bus_re) begin
            if (ram_sel || !reg_sel) bus_rdata <= 32'd0;
            else case (idx)
                10'd0: bus_rdata <= {31'd0, run};
                10'd1: bus_rdata <= {29'd0, illegal, halted, run && !halted};
                10'd2: bus_rdata <= pc;
                10'd3: bus_rdata <= (con_n != 0) ? {1'b1, 23'd0, con[cr[7:0]]} : 32'd0;   // (cr moves on above)
                10'd4: bus_rdata <= {23'd0, con_n};
                10'd5: bus_rdata <= mail_in;
                10'd6: bus_rdata <= mail_out;
                10'd7: bus_rdata <= retired;
                10'd8: bus_rdata <= {20'd0, leds, 4'd0, gpio_out};
                10'd9: bus_rdata <= 32'h52563332;           // "RV32"
                default: bus_rdata <= 32'd0;
            endcase
        end
        if (rd_ram) bus_rdata <= qb;
    end
endmodule
