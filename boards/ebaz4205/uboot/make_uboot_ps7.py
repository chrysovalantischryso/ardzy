"""Turns a Vivado ps7_init_gpl.c (Xilinx format) into U-Boot's format (like uboot/ps7_init_gpl.c of the S9):
only the tables for silicon 3.0 (every XC7Z010 sold for years), U-Boot's own header, and ps7_init / ps7_post_config.

    python make_uboot_ps7.py vivado_ps7_init_gpl.c > ps7_init_gpl.c
"""
import re, sys

src = open(sys.argv[1], encoding='utf-8').read()
src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
TABLES = ['pll_init', 'clock_init', 'ddr_init', 'mio_init', 'peripherals_init', 'post_config']
out = ['// SPDX-License-Identifier: GPL-2.0+',
       '/*',
       ' * EBAZ4205, 256 MB DDR3 (MT41K128M16, 16 bit, 533 MHz). Register tables for silicon 3.0 from the',
       ' * Vivado-generated ps7_init_gpl.c of https://github.com/KeitetsuWorks/EBAZ4205 (Xilinx, GPL-2.0+),',
       ' * one change for Ardzy: FCLK0 = 100 MHz (0xF8000170). Made by boards/ebaz4205/uboot/make_uboot_ps7.py.',
       ' */', '', '#include <asm/arch/ps7_init_gpl.h>', '']
for t in TABLES:
    name = 'ps7_%s_3_0' % (t if t == 'post_config' else t + '_data')
    m = re.search(r'unsigned long %s\[\]\s*=\s*\{(.*?)\n\};' % name, src, re.S)
    if not m:
        sys.exit('table %s not found' % name)
    body = []
    for line in m.group(1).splitlines():
        line = line.split('//')[0].strip()
        if line.startswith('EMIT_'):
            line = re.sub(r'0[xX]([0-9A-Fa-f]+)[uU]?', lambda x: '0x' + x.group(1).lower(), line)
            body.append('\t' + re.sub(r'\s*,\s*', ', ', line).replace(', )', ')').rstrip())
    if not body or not body[-1].startswith('\tEMIT_EXIT'):
        sys.exit('table %s does not end with EMIT_EXIT' % name)
    out += ['static unsigned long %s[] = {' % name] + body + ['};', '']
out += ['int ps7_init(void)', '{', '\tint ret;', '']
for t in ('mio_init', 'pll_init', 'clock_init', 'ddr_init', 'peripherals_init'):
    out += ['\tret = ps7_config(ps7_%s_data_3_0);' % t, '\tif (ret != PS7_INIT_SUCCESS)', '\t\treturn ret;']
out += ['', '\treturn PS7_INIT_SUCCESS;', '}', '', 'int ps7_post_config(void)', '{',
        '\treturn ps7_config(ps7_post_config_3_0);', '}', '']
sys.stdout.write('\n'.join(out))
