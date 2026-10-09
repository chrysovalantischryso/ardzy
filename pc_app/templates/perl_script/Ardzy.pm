# Ardzy.pm: the Ardzy board from Perl.   Use it with:  use Ardzy;
#
#   led('green', 1);                 # status LED: green, red or ps; 1 = on, 0 = off
#   beep(0.1);                       # buzzer, seconds
#   if (button('ip')) { ... }        # true while pressed: ip (S2) or reset (S1)
#   my $v = peek(0x41200000);        # 32-bit FPGA register at an address (Vivado's Address Editor)
#   poke(0x41200000, 5);
#   my $w = reg(1, 3); reg_write(1, 3, 42);   # word 3 of slot 1 of an Ardzy FPGA project
#   watch(speed => 12.5);            # a live value for the app's Watch tab and Plotter
#
# Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
# behind it can hang the board until it is reset.
package Ardzy;
use strict;
use warnings;
use Exporter 'import';
use IPC::Open2;
use Time::HiRes ();

our @EXPORT = qw(led beep button peek poke reg reg_write watch);
our $BUS_BASE = 0x43C00000;
my %LED = (green => [38, 1], red => [37, 1], ps => [15, 0]);    # GPIO number, on when high
my %BUTTON = (ip => 51, reset => 47);

$| = 1;     # print each line at once (the Monitor shows it immediately)

sub _gpio_set {
    my ($n, $v) = @_;
    open(my $f, '>', "/sys/class/gpio/gpio$n/value") or die "cannot open gpio$n: $!";
    print $f ($v ? '1' : '0');
    close($f);
}

sub _gpio_get {
    my ($n) = @_;
    open(my $f, '<', "/sys/class/gpio/gpio$n/value") or die "cannot open gpio$n: $!";
    my $v = <$f>;
    close($f);
    return $v =~ /^1/;
}

sub led {
    my ($name, $on) = @_;
    $on = 1 unless defined $on;
    my $l = $LED{$name} or die "led: green, red or ps\n";
    _gpio_set($l->[0], ($on ? 1 : 0) == $l->[1]);
}

sub beep {
    my ($s) = @_;
    _gpio_set(39, 1);
    Time::HiRes::sleep($s // 0.1);
    _gpio_set(39, 0);
}

sub button {
    my $n = $BUTTON{$_[0] // 'ip'} // die "button: ip or reset\n";
    return !_gpio_get($n);
}

# FPGA registers: through the board's register helper (Perl cannot map memory by itself)
my ($rd, $wr);
sub _regd {
    my ($cmd) = @_;
    unless ($wr) {
        my $h = $ENV{ARDZY_REGD} or die "the register helper is missing (start the program with Upload)\n";
        open2($rd, $wr, $h) or die "cannot start $h\n";
    }
    print $wr "$cmd\n";
    $wr->flush();
    my $ans = <$rd>;
    die "register helper stopped\n" unless defined $ans;
    chomp $ans;
    die "$ans\n" if $ans =~ /^error/;
    return $ans;
}

sub peek { return 0 + _regd(sprintf('r 0x%x', $_[0])); }
sub poke { _regd(sprintf('w 0x%x %u', $_[0], $_[1] & 0xFFFFFFFF)); }
sub reg { return peek($BUS_BASE + $_[0] * 0x1000 + 4 * $_[1]); }
sub reg_write { poke($BUS_BASE + $_[0] * 0x1000 + 4 * $_[1], $_[2]); }

sub watch {
    my @parts;
    while (my ($k, $v) = splice(@_, 0, 2)) {
        push @parts, ($v =~ /^-?\d+(\.\d+)?$/) ? "$k:$v" : "$k=\"$v\"";
    }
    print join(' ', @parts), "\n";
}

1;
