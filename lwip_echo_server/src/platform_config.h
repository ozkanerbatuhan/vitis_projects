/*
 * platform_config.h — Platform yapılandırma sabitleri
 *
 * LwIP ağ adaptörünün kullandığı EMAC base adresini tanımlar.
 */
#ifndef PLATFORM_CONFIG_H
#define PLATFORM_CONFIG_H

#include "xparameters.h"

/* ZedBoard Zynq PS Ethernet MAC (GEM0) base adresi */
#define PLATFORM_EMAC_BASEADDR  XPAR_XEMACPS_0_BASEADDR

#endif /* PLATFORM_CONFIG_H */
