# Antminer S9 control board: the 4 LEDs driven by the FPGA (PL)
# ACTIVE LOW: the LED lights when the pin is 0 (LED from 3.3 V via 220 ohm to the pin)
set_property PACKAGE_PIN F16 [get_ports {leds[0]}]
set_property PACKAGE_PIN L19 [get_ports {leds[1]}]
set_property PACKAGE_PIN M19 [get_ports {leds[2]}]
set_property PACKAGE_PIN M17 [get_ports {leds[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {leds[*]}]
set_property DRIVE 16 [get_ports {leds[*]}]
set_property SLEW SLOW [get_ports {leds[*]}]
