# Lesson 3: a button on J1 pin 5 (to GND), with the FPGA's pull-up
set_property PACKAGE_PIN T11 [get_ports {button_n}]
set_property IOSTANDARD LVCMOS33 [get_ports {button_n}]
set_property PULLTYPE PULLUP [get_ports {button_n}]
