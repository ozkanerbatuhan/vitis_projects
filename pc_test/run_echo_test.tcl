# run_echo_test.tcl — lwip_echo_server ELF'i ZedBoard'a yükle ve çalıştır
connect

# FPGA'yi programla (bitstream)
targets -set -filter {name =~ "APU*"}
fpga "D:/vitis_projects/lwip_echo_server/_ide/bitstream/mlp_system_wrapper.bit"

# PS7 init — Zynq donanımını başlat
targets -set -nocase -filter {name =~ "*A9*#0"}
loadhw -hw "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/mlp_system_wrapper.xsa"
source "D:/vitis_projects/mlp_platform/export/mlp_platform/hw/ps7_init.tcl"
ps7_init
ps7_post_config

# ELF yükle ve çalıştır
dow "D:/vitis_projects/lwip_echo_server/build/lwip_echo_server.elf"
con
