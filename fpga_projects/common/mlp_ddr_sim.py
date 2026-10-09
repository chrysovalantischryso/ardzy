"""Simulation of mlp_ddr.v (the DDR network engine) with Icarus Verilog, against a fake DDR (PC only).

The fake DDR answers the four HP ports with random delays and gaps; the program's memory pages are scattered
over it in random order (like Linux does). Networks are laid out by the real MLPDDR driver, run, and every
output is compared with mlp_reference(): the hardware must give exactly the same integers.
"""
import os, shutil, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from blocks import MLPDDR, mlp_reference      # noqa: E402

PAGES = 64                     # the fake DDR: 64 pages of 4 KB

TB = r'''`timescale 1ns / 1ps
module tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg [15:0] addr = 0;
    reg [31:0] wdata = 0;
    reg we = 0, re = 0;
    wire [31:0] bus_rdata;
    reg [31:0] rdata;
    wire [159:0] araddr; wire [19:0] arlen; wire [4:0] arvalid, rready;
    reg [4:0] arready = 0, rvalid = 0, rlast = 0;
    reg [319:0] rd = 0;
    mlp_ddr #(.SLOT(4'd1), .NP(__NP__)) dut (.clk(clk), .rstn(1'b1), .bus_addr(addr), .bus_wdata(wdata), .bus_we(we), .bus_re(re),
        .bus_rdata(bus_rdata), .busy_led(), .dr_araddr(araddr), .dr_arlen(arlen), .dr_arvalid(arvalid), .dr_arready(arready),
        .dr_rdata(rd), .dr_rvalid(rvalid), .dr_rlast(rlast), .dr_rresp(10'd0), .dr_rready(rready));
    // the fake DDR
    reg [63:0] mem [0:__WORDS__ - 1];
    initial $readmemh("__MEM__", mem);
    reg [31:0] lfsr = 32'h1234567;
    always @(posedge clk) lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
    reg [31:0] q [0:4][0:31];
    reg [5:0] qn [0:4];
    reg [4:0] qh [0:4], qt [0:4];
    reg [3:0] beat [0:4];
    integer k;
    initial for (k = 0; k < 5; k = k + 1) begin qn[k] = 0; qh[k] = 0; qt[k] = 0; beat[k] = 0; end
    always @(posedge clk) begin
        for (k = 1; k < 5; k = k + 1) begin
            arready[k] <= lfsr[k] & (qn[k] < 6);
            if (arvalid[k] && arready[k]) begin q[k][qt[k]] = araddr[32 * k +: 32]; qt[k] = qt[k] + 1; qn[k] = qn[k] + 1; end
            if (rvalid[k] && rready[k]) begin
                if (rlast[k]) begin qh[k] = qh[k] + 1; qn[k] = qn[k] - 1; beat[k] = 0; end
                else beat[k] = beat[k] + 1;
            end
            rvalid[k] <= 0; rlast[k] <= 0;
            if (qn[k] != 0 && lfsr[k + 8] && !(rvalid[k] && rready[k] && rlast[k] && qn[k] == 0)) begin
                rvalid[k] <= 1;
                rd[64 * k +: 64] <= mem[(q[k][qh[k]] >> 3) + beat[k]];
                rlast[k] <= beat[k] == 15;
            end
        end
    end
    task wr(input [9:0] i, input [31:0] v);
        begin @(posedge clk); addr <= 16'h1000 | (i << 2); wdata <= v; we <= 1; @(posedge clk); we <= 0; end
    endtask
    task rd_(input [9:0] i);
        begin @(posedge clk); addr <= 16'h1000 | (i << 2); re <= 1; @(posedge clk); re <= 0; @(posedge clk); @(posedge clk); rdata = bus_rdata; end
    endtask
    task waitdone;
        begin rd_(1); while (rdata[0]) rd_(1); end
    endtask
    initial begin #(__LIMIT__); $display("TIMEOUT"); $finish; end
    initial begin
        repeat (3) @(posedge clk);
__STEPS__
        $finish;
    end
endmodule
'''


class Recorder:
    def __init__(self):
        self.L = []

    def wr(self, slot, i, v):
        self.L.append("    wr(%d, 32'h%08x);" % (i, int(v) & 0xFFFFFFFF))


class FakeStore:
    """The program's memory as the engine sees it: regions of 'region' bytes, pages scattered over the fake DDR."""
    def __init__(self, region, seed=1, ports=4):
        self.region, self.ports = region, ports
        self.a = np.zeros(ports * region, np.uint8)
        rs = np.random.RandomState(seed)
        self.pages = list(rs.permutation(PAGES)[:ports * region // 4096])
        self.next = 0

    def put(self, streams):
        n = len(streams[0])
        ofs = self.next
        for p, s in enumerate(streams):
            self.a[p * self.region + ofs:p * self.region + ofs + n] = s
        self.next += n
        return ofs

    def flush(self):
        pass

    def ddr_image(self):
        mem = np.zeros(PAGES * 512, np.uint64)
        words = self.a.view('<u8')
        for i, pf in enumerate(self.pages):
            mem[pf * 512:(pf + 1) * 512] = words[i * 512:(i + 1) * 512]
        return mem


def find_iverilog():
    for d in (os.environ.get('ARDZY_IVERILOG'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Ardzy', 'icarus', 'bin')):
        if d and os.path.exists(os.path.join(d, 'iverilog.exe')):
            return d
    exe = shutil.which('iverilog')
    if exe:
        return os.path.dirname(exe)
    sys.exit('Icarus Verilog not found: open Simulation once in the Ardzy app, or set ARDZY_IVERILOG')


def simulate(nets, check, region=32768, runs=2, seed=7, ports=4):
    """nets: [(name, layers)]. Loads all into one fake store, runs each `runs` times on random inputs."""
    rec = Recorder()
    store = FakeStore(region, seed, ports)
    eng = MLPDDR(rec, slot=1, store=store)
    handles = [(name, eng.load(layers), layers) for name, layers in nets]
    rs = np.random.RandomState(seed)
    cases = []
    for name, h, layers in handles:
        for r in range(runs):
            tag = '%s_%d' % (name.replace(' ', '_'), len(cases))
            eng.use(h)
            x = rs.randint(0, 256, layers[0]['w'].shape[1]).astype(np.uint8)
            b = np.zeros(h['cfg'][0][0] * 4, np.uint8); b[:len(x)] = x
            for i, v in enumerate(b.view('<u4').tolist()):
                rec.L.append("    wr(%d, 32'h%08x);" % (256 + i, v))
            rec.L.append('    wr(0, 1);'); rec.L.append('    waitdone;')
            rec.L.append('    rd_(3); $display("%s_C %%08x", rdata);' % tag)
            rec.L.append('    rd_(6); $display("%s_ST %%08x", rdata);' % tag)
            last = h['cfg'][-1]
            if last[3] == 0:
                rec.L.append('    rd_(2); $display("%s_R %%08x", rdata);' % tag)
                for j in range(last[4]):
                    rec.L.append('    rd_(%d); $display("%s_S%d %%08x", rdata);' % (768 + j, tag, j))
            else:
                base = 512 if len(h['cfg']) % 2 else 256
                for w in range((last[4] + 3) // 4):
                    rec.L.append('    rd_(%d); $display("%s_O%d %%08x", rdata);' % (base + w, tag, w))
            cases.append((tag, h, layers, x))
    rec.L.append('    rd_(1023); $display("ID %08x", rdata);')
    work = os.path.join(os.environ.get('TEMP', '.'), 'ardzy_mlpddr_sim')
    os.makedirs(work, exist_ok=True)
    mem = store.ddr_image()
    open(os.path.join(work, 'mem.hex'), 'w').write('\n'.join('%016x' % int(v) for v in mem))
    tb = TB.replace('__STEPS__', '\n'.join(rec.L)).replace('__WORDS__', str(len(mem))).replace(
        '__MEM__', os.path.join(work, 'mem.hex').replace('\\', '/')).replace('__LIMIT__', '200000000').replace('__NP__', str(ports))
    open(os.path.join(work, 'tb.v'), 'w').write(tb)
    d = find_iverilog()
    env = dict(os.environ, PATH=d + os.pathsep + os.environ['PATH'])
    vfiles = [os.path.join(HERE, f) for f in ('mlp_ddr.v', 'mlp_sigmoid.v')]
    subprocess.run([os.path.join(d, 'iverilog.exe'), '-g2005', '-o', os.path.join(work, 'tb.vvp'), os.path.join(work, 'tb.v')] + vfiles,
                   check=True, env=env)
    r = subprocess.run([os.path.join(d, 'vvp.exe'), '-n', os.path.join(work, 'tb.vvp')], capture_output=True, text=True, env=env)
    got = {}
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) == 2:
            try:
                got[p[0]] = int(p[1], 16)
            except ValueError:
                got[p[0]] = None
    check('the simulation finished', 'TIMEOUT' not in r.stdout, r.stdout[-200:] if 'TIMEOUT' in r.stdout else '')
    sgn = lambda v: v - (1 << 32) if v is not None and v & 0x80000000 else v
    for tag, h, layers, x in cases:
        d_ref, out_ref = mlp_reference(layers, x)
        last = h['cfg'][-1]
        if last[3] == 0:
            hw = [sgn(got.get('%s_S%d' % (tag, j))) for j in range(last[4])]
            good = hw == out_ref and got.get(tag + '_R') == d_ref
        else:
            ws = [got.get('%s_O%d' % (tag, w)) or 0 for w in range((last[4] + 3) // 4)]
            hw = [int(v) for v in np.array(ws, dtype='<u4').view(np.uint8)[:last[4]]]
            good = hw == out_ref
        if not good and os.environ.get('MLPDDR_DEBUG'):
            print('  hw ', hw[:16]); print('  ref', out_ref[:16])
        check('%s: every output = the math' % tag, good, '%d layers, %s clocks, %s waiting for the DDR'
              % (len(h['cfg']), got.get(tag + '_C'), got.get(tag + '_ST')))
    check('ID', got.get('ID') == 0x4D4C5032, '%08x' % (got.get('ID') or 0))
