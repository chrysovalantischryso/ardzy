# Lesson 7: the UART on J1: TXD = pin 11, RXD = pin 12 (with a pull-up)
set_property PACKAGE_PIN T12 [get_ports {txd}]
set_property IOSTANDARD LVCMOS33 [get_ports {txd}]
set_property PACKAGE_PIN U12 [get_ports {rxd}]
set_property IOSTANDARD LVCMOS33 [get_ports {rxd}]
set_property PULLTYPE PULLUP [get_ports {rxd}]
