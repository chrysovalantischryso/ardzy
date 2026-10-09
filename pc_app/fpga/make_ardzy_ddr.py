"""Writes hdl/ardzy_ddr.v (run: python pc_app/fpga/make_ardzy_ddr.py): the PS7 with the DDR read ports, and ardzy_bus_ddr (= ardzy_bus + those ports).
ardzy_bus_ddr's body is copied from ardzy_bus, so the register bus behaves exactly the same."""
import os, re
HDL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hdl')
axi = open(os.path.join(HDL, 'ardzy_axi.v'), encoding='utf-8').read()
bus = open(os.path.join(HDL, 'ardzy_bus.v'), encoding='utf-8').read()

ps7 = re.search(r'module ardzy_ps7 \(.*?\nendmodule\n', axi, re.S).group(0)
P = ['ACP', 'HP0', 'HP1', 'HP2', 'HP3']
port_decl = '''    // DDR read ports (ACP = coherent with the ARM's caches; HP0..HP3 = straight to the DDR controller), each:
    // AR channel (address, beats - 1 of 8 bytes, valid / ready) and R channel (64-bit data, valid, last, ready)
    input  wire [5 * 32 - 1:0] dr_araddr, input wire [5 * 4 - 1:0] dr_arlen, input wire [4:0] dr_arvalid,
    output wire [4:0] dr_arready, output wire [5 * 64 - 1:0] dr_rdata, output wire [4:0] dr_rvalid,
    output wire [4:0] dr_rlast, output wire [9:0] dr_rresp, input wire [4:0] dr_rready'''
ps7_ddr = ps7.replace('module ardzy_ps7 (', 'module ardzy_ps7_ddr (', 1)
ps7_ddr = ps7_ddr.replace('module ardzy_ps7_ddr (', 'module ardzy_ps7_ddr #(parameter CLK_DIV = 0) (', 1)
old_clk = '    BUFG u_bufg (.I(fclk[0]), .O(clk));\n'
assert old_clk in ps7_ddr
ps7_ddr = ps7_ddr.replace(old_clk, """    // CLK_DIV = 0: clk = FCLK0 (100 MHz). Otherwise the design makes its own clock, 900 MHz / CLK_DIV
    // (12: 75 MHz), with an MMCM from FCLK0; the PS's ports run on it too, so nothing crosses clocks.
    // FCLK0 itself is not changed: the next project finds it as it was.
    wire locked;
    generate if (CLK_DIV == 0) begin : direct
        BUFG u_bufg (.I(fclk[0]), .O(clk));
        assign locked = 1'b1;
    end else begin : own
        wire f0, fb_o, fb_i, c_o;
        BUFG u_bin (.I(fclk[0]), .O(f0));
        MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(CLK_DIV)) u_mmcm (
            .CLKIN1(f0), .CLKFBIN(fb_i), .CLKFBOUT(fb_o), .RST(~fclk_rstn[0]), .PWRDWN(1'b0), .CLKOUT0(c_o), .LOCKED(locked));
        BUFG u_bfb (.I(fb_o), .O(fb_i));
        BUFG u_bufg (.I(c_o), .O(clk));
    end endgenerate
""", 1)
old_rs = '    always @(posedge clk) rs <= {rs[1:0], fclk_rstn[0]};\n'
assert old_rs in ps7_ddr
ps7_ddr = ps7_ddr.replace(old_rs, '    always @(posedge clk) rs <= {rs[1:0], fclk_rstn[0] & locked};\n', 1)
ps7_ddr = ps7_ddr.replace('    input wire rvalid, output wire rready\n);', '    input wire rvalid, output wire rready,\n' + port_decl + '\n);', 1)
USED = ('HP0', 'HP2')        # the ports wired up; the others only get their valid inputs held at 0
conn, unused_assign = [], []
for k, p in enumerate(P):
    s = 'SAXI' + p
    if p not in USED:
        conn.append("        .%sARVALID(1'b0), .%sAWVALID(1'b0), .%sWVALID(1'b0)," % (s, s, s))
        unused_assign.append("    assign dr_arready[%d] = 1'b0; assign dr_rvalid[%d] = 1'b0; assign dr_rlast[%d] = 1'b0; "
                             "assign dr_rdata[%d +: 64] = 64'd0; assign dr_rresp[%d +: 2] = 2'd0;" % (k, k, k, 64 * k, 2 * k))
        continue
    extra = ('.%sARCACHE(4\'b1111), .%sARUSER(5\'b11111), .%sARID(3\'d0), ' % (s, s, s)) if p == 'ACP' else \
            ('.%sARCACHE(4\'b0011), .%sARID(6\'d0), .%sRDISSUECAP1EN(1\'b0), .%sWRISSUECAP1EN(1\'b0), ' % (s, s, s, s))
    conn.append(
        '        .%sACLK(clk), .%sARADDR(dr_araddr[%d +: 32]), .%sARLEN(dr_arlen[%d +: 4]), .%sARSIZE(2\'d3), .%sARBURST(2\'d1),\n'
        '        %s.%sARPROT(3\'d0), .%sARQOS(4\'d0), .%sARLOCK(2\'d0),\n'
        '        .%sARVALID(dr_arvalid[%d]), .%sARREADY(dr_arready[%d]), .%sRDATA(dr_rdata[%d +: 64]), .%sRVALID(dr_rvalid[%d]),\n'
        '        .%sRLAST(dr_rlast[%d]), .%sRRESP(dr_rresp[%d +: 2]), .%sRREADY(dr_rready[%d]),\n'
        '        .%sAWVALID(1\'b0), .%sWVALID(1\'b0), .%sBREADY(1\'b1),'
        % (s, s, 32 * k, s, 4 * k, s, s, extra, s, s, s, s, k, s, k, s, 64 * k, s, k, s, k, s, 2 * k, s, k, s, s, s))
ps7_ddr = ps7_ddr.replace('        .MAXIGP0ACLK(clk),\n', '        .MAXIGP0ACLK(clk),\n' + '\n'.join(conn) + '\n', 1)
ps7_ddr = ps7_ddr.replace('// ------------------------------------------------------------------------------------- PS7\n', '')
ps7_ddr = ps7_ddr.replace('\nendmodule\n', '\n    // ports not wired up (see USED in the generator): never ready, never data\n'
                          + '\n'.join(unused_assign) + '\nendmodule\n', 1)

b = re.search(r'module ardzy_bus \(.*?\nendmodule\n', bus, re.S).group(0)
b = b.replace('module ardzy_bus (', 'module ardzy_bus_ddr #(parameter CLK_DIV = 0) (', 1)
b = b.replace('    input  wire [31:0] bus_rdata\n);', '    input  wire [31:0] bus_rdata,\n' + port_decl + '\n);', 1)
b = b.replace('    ardzy_ps7 u_ps7 (', '    ardzy_ps7_ddr #(.CLK_DIV(CLK_DIV)) u_ps7 (', 1)
b = re.sub(r'(\.rvalid\(rvalid\), \.rready\(rready\))\);', r'\1,\n        .dr_araddr(dr_araddr), .dr_arlen(dr_arlen), .dr_arvalid(dr_arvalid), .dr_arready(dr_arready), .dr_rdata(dr_rdata),\n        .dr_rvalid(dr_rvalid), .dr_rlast(dr_rlast), .dr_rresp(dr_rresp), .dr_rready(dr_rready));', b, 1)
assert 'dr_araddr(dr_araddr)' in b and 'SAXIHP2ARADDR' in ps7_ddr and 'SAXIHP3ARADDR' not in ps7_ddr

head = '''// Ardzy FPGA library: the DDR read ports. Like ardzy_bus (the ARM's register bus), plus 5 ports through which
// the FPGA reads the board's DDR memory by itself (DMA): port 0 = ACP (sees the ARM's caches, so data the ARM just
// wrote is always right), ports 1..4 = HP0..HP3 (straight to the DDR controller, the fastest; the ARM's caches
// must be written back first). Only reading: the FPGA can not change Linux's memory through these.
//
//   ardzy_bus_ddr  = ardzy_bus + dr_* ports      ardzy_ps7_ddr  = ardzy_ps7 + the same ports
//   CLK_DIV: 0 = FCLK0 as the clock (100 MHz); else an own clock of 900 MHz / CLK_DIV (12 = 75 MHz)
// Wired up: HP0 and HP2 only (dr_ ports 1 and 3): with all four HP ports the many wires at the PS edge did not
// route. The others (ACP, HP1, HP3) only get their valid inputs held at 0 and never answer.
// (generated from ardzy_bus.v / ardzy_axi.v, so the register bus works exactly like in every other project)
`timescale 1ns / 1ps
'''
open(os.path.join(HDL, 'ardzy_ddr.v'), 'w', encoding='utf-8', newline='\n').write(head + '\n' + ps7_ddr + '\n' + b)
print('wrote ardzy_ddr.v')
