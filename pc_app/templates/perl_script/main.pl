#!/usr/bin/perl
# __NAME__: a Perl program on the Ardzy board.
# Press Upload: it runs on the board; everything it prints shows up in the Monitor.
# Ardzy.pm has the board: led, beep, button, peek/poke (FPGA registers), watch.
#   - the green status LED blinks
#   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
#   - press the Reset button (S1): the program ends
use strict;
use warnings;
use Time::HiRes qw(sleep);
use Ardzy;

print "hello from __NAME__ (Perl): press the IP button, or Reset to end\n";
my $presses = 0;
for (my $t = 0; ; $t++) {
    led('green', $t % 10 < 5);
    if (button('ip')) {
        $presses++;
        print "IP button pressed ($presses)\n";
        watch(presses => $presses);
        beep(0.08);
        sleep(0.02) while button('ip');     # wait until it is released
    }
    if (button('reset')) {
        print "Reset button pressed: bye!\n";
        beep(0.4);
        last;
    }
    # An FPGA register (only with an FPGA design that has it), for example:
    #   my $v = reg(1, 0);
    sleep(0.1);
}
led('green', 0);
