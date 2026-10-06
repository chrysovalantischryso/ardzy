# __NAME__ - Vivado 2021.1 batch build:  vivado -mode batch -source build.tcl
# PS7 --(AXI GP0)--> AXI GPIO @ 0x41200000 -> 4 LEDs.  Python on the ARM writes the LEDs.
set part xc7z010clg400-1
set here [file normalize [file dirname [info script]]]
set out  [file normalize "$here/../_build/__NAME__"]
file delete -force $out
create_project __NAME__ $out -part $part -force
add_files -fileset constrs_1 "$here/leds.xdc"

create_bd_design sys
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} \
  [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] [get_bd_cells ps7]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 gpio_leds
set_property -dict [list CONFIG.C_GPIO_WIDTH {4} CONFIG.C_ALL_OUTPUTS {1}] [get_bd_cells gpio_leds]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
  -config {Clk_master {/ps7/FCLK_CLK0} Clk_slave {Auto} Clk_xbar {Auto} Master {/ps7/M_AXI_GP0} Slave {/gpio_leds/S_AXI} intc_ip {New AXI Interconnect} master_apm {0}} \
  [get_bd_intf_pins gpio_leds/S_AXI]
create_bd_port -dir O -from 3 -to 0 leds
connect_bd_net [get_bd_pins gpio_leds/gpio_io_o] [get_bd_ports leds]
set_property offset 0x41200000 [get_bd_addr_segs {ps7/Data/SEG_gpio_leds_Reg}]
set_property range 64K [get_bd_addr_segs {ps7/Data/SEG_gpio_leds_Reg}]
validate_bd_design
save_bd_design

make_wrapper -files [get_files sys.bd] -top
add_files -norecurse [glob "$out/__NAME__.gen/sources_1/bd/sys/hdl/sys_wrapper.v"]
set_property top sys_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs 8
wait_on_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1

set bit "$out/__NAME__.runs/impl_1/sys_wrapper.bit"
if {[file exists $bit]} {
  file copy -force $bit "$here/__NAME__.bit"
  puts "BUILD_OK: $here/__NAME__.bit"
} else { puts "BUILD_FAIL" }
