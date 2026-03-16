# Additional clean files
cmake_minimum_required(VERSION 3.16)

if("${CONFIG}" STREQUAL "" OR "${CONFIG}" STREQUAL "")
  file(REMOVE_RECURSE
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\lwipopts.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\sleep.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\xemac_ieee_reg.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\xemacpsif_hw.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\xiltimer.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\xlwipconfig.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\include\\xtimer_config.h"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\lib\\liblwip220.a"
  "D:\\vitis_projects\\mlp_platform\\ps7_cortexa9_0\\standalone_ps7_cortexa9_0\\bsp\\lib\\libxiltimer.a"
  )
endif()
