# Timing constraints for ibex_top, for floorplan and placement (TP2).
# Same as TP1 (period taken from CLOCK_PERIOD in config.json), plus ideal clocks.
create_clock -name clk -period $::env(CLOCK_PERIOD) [get_ports $::env(CLOCK_PORT)]

# Async reset: unbuffered before PnR (one port drives every flop), and
# OpenSTA ignores set_ideal_network, so exclude it from pre-PnR timing.
set_false_path -from [get_ports rst_ni]

set input_ports [delete_from_list [all_inputs] [get_ports $::env(CLOCK_PORT)]]
set_input_delay  [expr $::env(CLOCK_PERIOD) * 0.2] -clock clk $input_ports
set_output_delay [expr $::env(CLOCK_PERIOD) * 0.2] -clock clk [all_outputs]

# Driving cell and output load come from the selected std cell library.
set driving_cell [split $::env(SYNTH_DRIVING_CELL) "/"]
set_driving_cell -lib_cell [lindex $driving_cell 0] -pin [lindex $driving_cell 1] $input_ports
set_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0] [all_outputs]

# Pre-CTS margins. Hold uses a smaller one: hold is fixed in PnR with
# buffer insertion, so only basic jitter margin is applied here.
set_clock_uncertainty -setup 0.25 [get_clocks clk]
set_clock_uncertainty -hold  0.10 [get_clocks clk]
set_clock_transition 0.15 [get_clocks clk]

# No clock tree before CTS: a single clock gate drives every flop, so a
# propagated clock would show tens of ns of fake latency. Keep it ideal.
unset_propagated_clock [all_clocks]
