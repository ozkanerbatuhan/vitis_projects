/*
 * platform_config.h -- platform configuration constants
 *
 * Defines the EMAC base address used by the lwIP network adapter.
 */
#ifndef PLATFORM_CONFIG_H
#define PLATFORM_CONFIG_H

#include "xparameters.h"

/* ZedBoard Zynq PS Ethernet MAC (GEM0) base adresi */
#define PLATFORM_EMAC_BASEADDR  XPAR_XEMACPS_0_BASEADDR

#endif /* PLATFORM_CONFIG_H */
