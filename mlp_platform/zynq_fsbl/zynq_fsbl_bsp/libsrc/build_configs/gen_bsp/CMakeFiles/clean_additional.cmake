# Additional clean files
cmake_minimum_required(VERSION 3.16)

if("${CONFIG}" STREQUAL "" OR "${CONFIG}" STREQUAL "")
  file(REMOVE_RECURSE
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\diskio.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\ff.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\ffconf.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\lwipopts.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\sleep.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xemac_ieee_reg.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xemacpsif_hw.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xilffs.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xilffs_config.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xilrsa.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xiltimer.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xlwipconfig.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\include\\xtimer_config.h"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\lib\\liblwip220.a"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\lib\\libxilffs.a"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\lib\\libxilrsa.a"
  "D:\\vitis_projects\\mlp_platform\\zynq_fsbl\\zynq_fsbl_bsp\\lib\\libxiltimer.a"
  )
endif()
