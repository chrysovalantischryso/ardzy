# The 4 LEDs of the board, driven by the FPGA. ACTIVE LOW: an LED lights when its pin is 0.
set_property PACKAGE_PIN F16 [get_ports {leds[0]}]
set_property PACKAGE_PIN L19 [get_ports {leds[1]}]
set_property PACKAGE_PIN M19 [get_ports {leds[2]}]
set_property PACKAGE_PIN M17 [get_ports {leds[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {leds[*]}]
