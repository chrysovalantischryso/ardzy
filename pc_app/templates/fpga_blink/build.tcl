# __NAME__ - Vivado 2021.1 batch build:  vivado -mode batch -source build.tcl
# PS7 (only to get the 100 MHz FCLK0) -> blink counter -> 4 LEDs
set part xc7z010clg400-1
set here [file normalize [file dirname [info script]]]
set out  [file normalize "$here/../_build/__NAME__"]
file delete -force $out
create_project __NAME__ $out -part $part -force

add_files "$here/blink.v"
add_files -fileset constrs_1 "$here/leds.xdc"
update_compile_order -fileset sources_1

create_bd_design sys
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} \
  [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {0} CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] [get_bd_cells ps7]
create_bd_cell -type module -reference blink blink0
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins blink0/clk]
create_bd_port -dir O -from 3 -to 0 leds
connect_bd_net [get_bd_pins blink0/leds] [get_bd_ports leds]
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
