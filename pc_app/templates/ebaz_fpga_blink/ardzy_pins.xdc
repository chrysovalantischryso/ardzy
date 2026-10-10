# EBAZ4205 pins for your design: remove the # in front of the pins you use and name the port as in
# your top module. All are 3.3 V FPGA pins with no protection. The Ethernet pins and the two LEDs
# are connected by the Ardzy build itself (use the LEDs: name a port and uncomment its line).

# DATA1 header
#set_property -dict {PACKAGE_PIN A20 IOSTANDARD LVCMOS33} [get_ports {data1_5}]
#set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports {data1_6}]
#set_property -dict {PACKAGE_PIN B19 IOSTANDARD LVCMOS33} [get_ports {data1_7}]
#set_property -dict {PACKAGE_PIN B20 IOSTANDARD LVCMOS33} [get_ports {data1_8}]
#set_property -dict {PACKAGE_PIN C20 IOSTANDARD LVCMOS33} [get_ports {data1_9}]
#set_property -dict {PACKAGE_PIN H17 IOSTANDARD LVCMOS33} [get_ports {data1_11}]
#set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {data1_13}]
#set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVCMOS33} [get_ports {data1_14}]
#set_property -dict {PACKAGE_PIN H18 IOSTANDARD LVCMOS33} [get_ports {data1_15}]
#set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports {data1_16}]
#set_property -dict {PACKAGE_PIN F20 IOSTANDARD LVCMOS33} [get_ports {data1_17}]
#set_property -dict {PACKAGE_PIN E19 IOSTANDARD LVCMOS33} [get_ports {data1_18}]
#set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS33} [get_ports {data1_19}]
#set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports {data1_20}]

# DATA2 header
#set_property -dict {PACKAGE_PIN G20 IOSTANDARD LVCMOS33} [get_ports {data2_5}]
#set_property -dict {PACKAGE_PIN J18 IOSTANDARD LVCMOS33} [get_ports {data2_6}]
#set_property -dict {PACKAGE_PIN G19 IOSTANDARD LVCMOS33} [get_ports {data2_7}]
#set_property -dict {PACKAGE_PIN H20 IOSTANDARD LVCMOS33} [get_ports {data2_8}]
#set_property -dict {PACKAGE_PIN J19 IOSTANDARD LVCMOS33} [get_ports {data2_9}]
#set_property -dict {PACKAGE_PIN K18 IOSTANDARD LVCMOS33} [get_ports {data2_11}]
#set_property -dict {PACKAGE_PIN K19 IOSTANDARD LVCMOS33} [get_ports {data2_13}]
#set_property -dict {PACKAGE_PIN J20 IOSTANDARD LVCMOS33} [get_ports {data2_14}]
#set_property -dict {PACKAGE_PIN L16 IOSTANDARD LVCMOS33} [get_ports {data2_15}]
#set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33} [get_ports {data2_16}]
#set_property -dict {PACKAGE_PIN M18 IOSTANDARD LVCMOS33} [get_ports {data2_17}]
#set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33} [get_ports {data2_18}]
#set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports {data2_19}]
#set_property -dict {PACKAGE_PIN L17 IOSTANDARD LVCMOS33} [get_ports {data2_20}]

# DATA3 header
#set_property -dict {PACKAGE_PIN M19 IOSTANDARD LVCMOS33} [get_ports {data3_5}]
#set_property -dict {PACKAGE_PIN N20 IOSTANDARD LVCMOS33} [get_ports {data3_6}]
#set_property -dict {PACKAGE_PIN P18 IOSTANDARD LVCMOS33} [get_ports {data3_7}]
#set_property -dict {PACKAGE_PIN M17 IOSTANDARD LVCMOS33} [get_ports {data3_8}]
#set_property -dict {PACKAGE_PIN N17 IOSTANDARD LVCMOS33} [get_ports {data3_9}]
#set_property -dict {PACKAGE_PIN P20 IOSTANDARD LVCMOS33} [get_ports {data3_11}]
#set_property -dict {PACKAGE_PIN R18 IOSTANDARD LVCMOS33} [get_ports {data3_13}]
#set_property -dict {PACKAGE_PIN R19 IOSTANDARD LVCMOS33} [get_ports {data3_14}]
#set_property -dict {PACKAGE_PIN P19 IOSTANDARD LVCMOS33} [get_ports {data3_15}]
#set_property -dict {PACKAGE_PIN T20 IOSTANDARD LVCMOS33} [get_ports {data3_16}]
#set_property -dict {PACKAGE_PIN U20 IOSTANDARD LVCMOS33} [get_ports {data3_17}]
#set_property -dict {PACKAGE_PIN T19 IOSTANDARD LVCMOS33} [get_ports {data3_18}]
#set_property -dict {PACKAGE_PIN V20 IOSTANDARD LVCMOS33} [get_ports {data3_19}]
#set_property -dict {PACKAGE_PIN U19 IOSTANDARD LVCMOS33} [get_ports {data3_20}]

# on-board LEDs (on when the pin is 0)
#set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {led_red_n}]
#set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {led_green_n}]

# fan headers J3 / J5: PWM out, speed in
#set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33} [get_ports {j3_pwm}]
#set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} [get_ports {j3_tach}]
#set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {j5_pwm}]
#set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33} [get_ports {j5_tach}]

# 50 MHz oscillator X5 (only on boards that have it mounted)
#set_property -dict {PACKAGE_PIN N18 IOSTANDARD LVCMOS33} [get_ports {clk50}]
