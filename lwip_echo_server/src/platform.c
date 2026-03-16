/*
 * platform.c — Zynq platform başlatma
 *
 * Cache'leri açar ve exception'ları aktifleştirir.
 * GIC başlatma ve interrupt bağlama işlemi XSetupInterruptSystem
 * (xinterrupt_wrap.c) tarafından otomatik yapılır.
 * Burada ayrıca GIC init yapmıyoruz çünkü çakışma yaratır.
 */
#include "xparameters.h"
#include "xil_cache.h"
#include "platform.h"
#include "platform_config.h"

void init_platform(void)
{
    /* Önbellekleri aç */
    Xil_ICacheEnable();
    Xil_DCacheEnable();

    /*
     * GIC init ve exception setup burada YAPILMIYOR.
     * XSetupInterruptSystem (xinterrupt_wrap.c) kendi
     * static XScuGicInstance'ını oluşturuyor ve
     * Xil_ExceptionInit + Xil_ExceptionEnable çağrıyor.
     * Burada ikinci bir GIC init yapmak çakışma yaratır.
     */
}

void cleanup_platform(void)
{
    Xil_ICacheDisable();
    Xil_DCacheDisable();
}
