# ardzy_io - the "pin control" design used by the Ardzy app's I/O and Tools views (version 2).
#   AXI GPIO   @ 0x4120_0000: ch1 = j1..j8 (32 pins), ch2 = j9, LEDs, TP1, board ID, I2C (17 pins)
#                             every pin tri-state (input by default)
#   ardzy_ctl  @ 0x43C0_0000 (64 KB): sits between the GPIO and the 49 pins (IOBUFs inside) and adds
#              8 PWM, 4 measuring channels, a UART, a 4096-sample logic analyzer, Device DNA,
#              the fan controller and the FCLK0 counter (ardzy_ctl.v). Simulation: sim/run_sim.bat
# Vivado 2021.1 batch:  vivado -mode batch -source build.tcl
set part xc7z010clg400-1
set here [file normalize [file dirname [info script]]]
set out  [file normalize "$here/../_build/ardzy_io"]
file delete -force $out
create_project ardzy_io $out -part $part -force
add_files "$here/ardzy_ctl.v"
add_files -fileset constrs_1 "$here/ardzy_io.xdc"
update_compile_order -fileset sources_1

create_bd_design sys
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} \
  [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] [get_bd_cells ps7]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 gpio
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {17} \
  CONFIG.C_ALL_INPUTS {0} CONFIG.C_ALL_INPUTS_2 {0} CONFIG.C_TRI_DEFAULT {0xFFFFFFFF} \
  CONFIG.C_TRI_DEFAULT_2 {0xFFFFFFFF}] [get_bd_cells gpio]
create_bd_cell -type module -reference ardzy_ctl ctl

apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
  -config {Clk_master {/ps7/FCLK_CLK0} Clk_slave {Auto} Clk_xbar {Auto} Master {/ps7/M_AXI_GP0} Slave {/gpio/S_AXI} intc_ip {New AXI Interconnect} master_apm {0}} \
  [get_bd_intf_pins gpio/S_AXI]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
  -config {Clk_master {/ps7/FCLK_CLK0} Clk_slave {Auto} Clk_xbar {Auto} Master {/ps7/M_AXI_GP0} Slave {/ctl/s_axi} intc_ip {Auto} master_apm {0}} \
  [get_bd_intf_pins ctl/s_axi]

# the GPIO goes through ardzy_ctl (pin function switch), which owns the pin buffers
connect_bd_net [get_bd_pins gpio/gpio_io_o]  [get_bd_pins ctl/gpio1_o]
connect_bd_net [get_bd_pins gpio/gpio_io_t]  [get_bd_pins ctl/gpio1_t]
connect_bd_net [get_bd_pins ctl/gpio1_i]     [get_bd_pins gpio/gpio_io_i]
connect_bd_net [get_bd_pins gpio/gpio2_io_o] [get_bd_pins ctl/gpio2_o]
connect_bd_net [get_bd_pins gpio/gpio2_io_t] [get_bd_pins ctl/gpio2_t]
connect_bd_net [get_bd_pins ctl/gpio2_i]     [get_bd_pins gpio/gpio2_io_i]
create_bd_port -dir IO -from 48 -to 0 pins
connect_bd_net [get_bd_pins ctl/pins] [get_bd_ports pins]
create_bd_port -dir O fan_pwm
create_bd_port -dir I -from 5 -to 0 fan_tach
connect_bd_net [get_bd_pins ctl/fan_pwm] [get_bd_ports fan_pwm]
connect_bd_net [get_bd_pins ctl/fan_tach] [get_bd_ports fan_tach]

set_property offset 0x41200000 [get_bd_addr_segs {ps7/Data/SEG_gpio_Reg}]
set_property range 64K [get_bd_addr_segs {ps7/Data/SEG_gpio_Reg}]
set fseg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *ctl*}]
set_property offset 0x43C00000 $fseg
set_property range 64K $fseg
validate_bd_design
save_bd_design
puts "ADDRESS MAP:"
foreach s [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data]] {
  puts "  [get_property NAME $s]  [get_property OFFSET $s]  [get_property RANGE $s]"
}

set_property synth_checkpoint_mode None [get_files sys.bd]
make_wrapper -files [get_files sys.bd] -top
add_files -norecurse [glob "$out/ardzy_io.gen/sources_1/bd/sys/hdl/sys_wrapper.v"]
set_property top sys_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs 8
wait_on_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
open_run impl_1
report_timing_summary -max_paths 2 -file "$out/timing.txt"
puts "WNS: [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]"

set bit "$out/ardzy_io.runs/impl_1/sys_wrapper.bit"
if {[file exists $bit]} {
  file copy -force $bit "$here/ardzy_io.bit"
  puts "BUILD_OK: $here/ardzy_io.bit"
} else { puts "BUILD_FAIL" }
