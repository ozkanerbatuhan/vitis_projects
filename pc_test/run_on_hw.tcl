# run_on_hw.tcl — mlp_app.elf'i ZedBoard'a yükle ve çalıştır
connect

# FPGA'yi programla (bitstream)
targets -set -filter {name =~ "APU*"}
fpga "D:/vitis_projects/mlp_app/_ide/bitstream/mlp_system_wrapper.bit"

# PS7 init — Zynq donanımını başlat
targets -set -nocase -filter {name =~ "*A9*#0"}
loadhw -hw "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/mlp_system_wrapper.xsa"
source "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/ps7_init.tcl"
ps7_init
ps7_post_config

# ELF yükle ve çalıştır
dow "D:/vitis_projects/mlp_app/build/mlp_app.elf"
con
