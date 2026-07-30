/*
 * platform.c -- Zynq platform initialisation
 *
 * Enables the caches and exceptions. GIC setup and interrupt binding are
 * handled automatically by XSetupInterruptSystem in xinterrupt_wrap.c, so
 * the GIC is deliberately not initialised again here: doing so conflicts.
 */
#include "xparameters.h"
#include "xil_cache.h"
#include "platform.h"
#include "platform_config.h"

void init_platform(void)
{
    /* Enable the caches */
    Xil_ICacheEnable();
    Xil_DCacheEnable();

    /*
     * GIC init ve exception setup burada YAPILMIYOR.
     * XSetupInterruptSystem (xinterrupt_wrap.c) kendi
     * creates the static XScuGicInstance and calls Xil_ExceptionInit and
     * Xil_ExceptionEnable. A second GIC init here would conflict.
     */
}

void cleanup_platform(void)
{
    Xil_ICacheDisable();
    Xil_DCacheDisable();
}
