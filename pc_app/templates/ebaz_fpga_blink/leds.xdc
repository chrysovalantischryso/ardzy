# the two LEDs (on when the pin is 0)
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {led_green_n}]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {led_red_n}]
