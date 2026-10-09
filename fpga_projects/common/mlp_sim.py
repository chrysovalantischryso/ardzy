"""Simulation of mlp_engine.v with Icarus Verilog (PC only), shared by projects 17 and 18 (their sim/run_sim.py).

Networks are loaded with the real MLP driver from blocks.py (its register writes are recorded and become the
testbench), then run, and every result is compared with mlp_reference(): the hardware must give exactly the
same integers.
"""
import os, shutil, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from blocks import MLP, mlp_reference, mlp_pad      # noqa: E402

TB = r'''`timescale 1ns / 1ps
module tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg [15:0] addr = 0;
    reg [31:0] wdata = 0;
    reg we = 0, re = 0;
    wire [31:0] bus_rdata;
    reg [31:0] rdata;
    mlp_engine #(.SLOT(4'd1), .ID(32'h4D4C5031)) dut (.clk(clk), .rstn(1'b1), .bus_addr(addr), .bus_wdata(wdata),
        .bus_we(we), .bus_re(re), .bus_rdata(bus_rdata), .busy_led());
    task wr(input [9:0] i, input [31:0] v);
        begin @(posedge clk); addr <= 16'h1000 | (i << 2); wdata <= v; we <= 1; @(posedge clk); we <= 0; end
    endtask
    task rd(input [9:0] i);
        begin @(posedge clk); addr <= 16'h1000 | (i << 2); re <= 1; @(posedge clk); re <= 0; @(posedge clk); @(posedge clk); rdata = bus_rdata; end
    endtask
    task waitdone;
        begin rd(1); while (rdata[0]) rd(1); end
    endtask
    initial begin
        repeat (3) @(posedge clk);
__STEPS__
        $finish;
    end
endmodule
'''


def find_iverilog():
    for d in (os.environ.get('ARDZY_IVERILOG'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Ardzy', 'icarus', 'bin')):
        if d and os.path.exists(os.path.join(d, 'iverilog.exe')):
            return d
    exe = shutil.which('iverilog')
    if exe:
        return os.path.dirname(exe)
    sys.exit('Icarus Verilog not found: open Simulation once in the Ardzy app, or set ARDZY_IVERILOG')


class Recorder:
    """Stands in for the FPGA bus: MLP's writes become testbench lines."""
    def __init__(self):
        self.L = []

    def wr(self, slot, i, v):
        self.L.append("    wr(%d, 32'h%08x);" % (i, int(v) & 0xFFFFFFFF))


class Sim:
    def __init__(self):
        self.rec = Recorder()
        self.mlp = MLP(self.rec, slot=1)
        self.cases = []

    def load(self, layers):
        return self.mlp.load(layers)

    def run(self, tag, cfg, layers, x):
        """Run network cfg (with float-free integer layers) on x, and remember what the math says."""
        L = self.rec.L
        self.mlp.use(cfg)
        b = np.zeros(cfg[0][0] * 4, np.uint8)
        b[:len(x)] = x
        for i, v in enumerate(b.view('<u4').tolist()):
            L.append("    wr(%d, 32'h%08x);" % (256 + i, v))
        L.append("    wr(0, 1);")
        L.append('    waitdone;')
        last = cfg[-1]
        L.append('    rd(3); $display("%s_C %%08x", rdata);' % tag)
        if last[5] == 0:
            L.append('    rd(2); $display("%s_R %%08x", rdata);' % tag)
            for j in range(last[6]):
                L.append('    rd(%d); $display("%s_S%d %%08x", rdata);' % (768 + j, tag, j))
        else:
            base = 512 if len(cfg) % 2 else 256
            for w in range((last[6] + 3) // 4):
                L.append('    rd(%d); $display("%s_O%d %%08x", rdata);' % (base + w, tag, w))
        self.cases.append((tag, cfg, layers, np.asarray(x, np.uint8)))

    def finish(self, vfiles, check):
        d = find_iverilog()
        work = os.path.join(os.environ.get('TEMP', '.'), 'ardzy_mlp_sim')
        os.makedirs(work, exist_ok=True)
        self.rec.L.append('    rd(1023); $display("ID %08x", rdata);')
        open(os.path.join(work, 'tb.v'), 'w').write(TB.replace('__STEPS__', '\n'.join(self.rec.L)))
        env = dict(os.environ, PATH=d + os.pathsep + os.environ['PATH'])
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
        sgn = lambda v: v - (1 << 32) if v is not None and v & 0x80000000 else v
        for tag, cfg, layers, x in self.cases:
            d_ref, out_ref = mlp_reference(layers, x)
            last = cfg[-1]
            if last[5] == 0:
                hw = [sgn(got.get('%s_S%d' % (tag, j))) for j in range(last[6])]
                good = hw == out_ref and got.get(tag + '_R') == d_ref
            else:
                ws = [got.get('%s_O%d' % (tag, w)) or 0 for w in range((last[6] + 3) // 4)]
                hw = list(np.array(ws, dtype='<u4').view(np.uint8)[:last[6]])
                good = [int(v) for v in hw] == out_ref
            check('%s: every output = the math' % tag, good, '%d layers, %s clocks' % (len(cfg), got.get(tag + '_C')))
        check('ID', got.get('ID') is not None, '%08x' % (got.get('ID') or 0))


def random_layers(rs, sizes, acts, shifts):
    layers = []
    for k, act in enumerate(acts):
        layers.append({'w': rs.randint(-127, 128, (sizes[k + 1], sizes[k])).astype(np.int8),
                       'b': rs.randint(-30000, 30000, sizes[k + 1]), 'shift': shifts[k], 'act': act})
    return layers
