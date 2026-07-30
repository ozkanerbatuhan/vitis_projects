# run_on_hw.tcl -- download and run mlp_app.elf on the ZedBoard
connect

# FPGA'yi programla (bitstream)
targets -set -filter {name =~ "APU*"}
fpga "D:/vitis_projects/mlp_app/_ide/bitstream/mlp_system_wrapper.bit"

# PS7 init: bring up the Zynq hardware
targets -set -nocase -filter {name =~ "*A9*#0"}
loadhw -hw "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/mlp_system_wrapper.xsa"
source "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/ps7_init.tcl"
ps7_init
ps7_post_config

# Download and run the ELF
dow "D:/vitis_projects/mlp_app/build/mlp_app.elf"
con
