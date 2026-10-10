# the two LEDs and header DATA1 pin 5
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {led_green_n}]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {led_red_n}]
set_property -dict {PACKAGE_PIN A20 IOSTANDARD LVCMOS33} [get_ports {data1_5}]
