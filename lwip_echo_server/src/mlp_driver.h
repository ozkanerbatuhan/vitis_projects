/*
 * mlp_driver.h — MLP AXI Register Driver
 *
 * ZedBoard PL tarafındaki MLP sinir ağı çekirdeğine
 * AXI üzerinden erişim sağlar.
 */
#ifndef MLP_DRIVER_H
#define MLP_DRIVER_H

#include "xil_io.h"
#include "xparameters.h"

/*
 * Base address — xparameters.h'den gelir.
 * XPAR_MLP_AXI_WRAPPER_0_BASEADDR = 0x40000000
 */
#ifndef MLP_BASE_ADDR
#define MLP_BASE_ADDR  XPAR_MLP_AXI_WRAPPER_0_BASEADDR
#endif

/* Register offsets */
#define MLP_REG_CTRL    0x00   /* W:  bit0 = start                           */
#define MLP_REG_STATUS  0x04   /* R:  bit0 = done, bit1 = busy               */
#define MLP_REG_INPUT   0x08   /* W:  [15:0]=data, [21:16]=addr              */
#define MLP_REG_RESULT  0x0C   /* R:  [1:0] = class (0=SELL,1=HOLD,2=BUY)    */

/* ── Düşük seviye register erişimi ── */
static inline void mlp_write_reg(u32 offset, u32 value) {
    Xil_Out32(MLP_BASE_ADDR + offset, value);
}

static inline u32 mlp_read_reg(u32 offset) {
    return Xil_In32(MLP_BASE_ADDR + offset);
}

/* ── Üst seviye fonksiyonlar ── */

/* Tek bir Q8.8 giriş değerini yaz (addr: 0..39) */
static inline void mlp_write_input(u8 addr, s16 data) {
    u32 val = ((u32)(addr & 0x3F) << 16) | ((u32)data & 0xFFFF);
    mlp_write_reg(MLP_REG_INPUT, val);
}

/* MLP çalıştırmayı başlat (tek darbe) */
static inline void mlp_start(void) {
    mlp_write_reg(MLP_REG_CTRL, 0x1);
    mlp_write_reg(MLP_REG_CTRL, 0x0);  /* pulse bitir */
}

/* done flag kontrol (1 = bitti) */
static inline int mlp_is_done(void) {
    return (mlp_read_reg(MLP_REG_STATUS) & 0x1);
}

/* busy flag kontrol (1 = çalışıyor) */
static inline int mlp_is_busy(void) {
    return (mlp_read_reg(MLP_REG_STATUS) >> 1) & 0x1;
}

/* Sonucu oku: 0=SELL, 1=HOLD, 2=BUY */
static inline u32 mlp_get_result(void) {
    return mlp_read_reg(MLP_REG_RESULT) & 0x3;
}

/* ── Tam inference akışı ── */
/*
 * inputs: 40 eleman Q8.8 formatında (s16 dizisi)
 * return: 0=SELL, 1=HOLD, 2=BUY
 */
static inline u32 mlp_predict(s16 *inputs) {
    int i;
    int timeout = 0;

    xil_printf("  -> mlp_predict: 1) Loading inputs...\r\n");
    /* 1) 40 girişi yükle */
    for (i = 0; i < 40; i++) {
        mlp_write_input((u8)i, inputs[i]);
    }

    xil_printf("  -> mlp_predict: 2) Starting MLP...\r\n");
    /* 2) Başlat */
    mlp_start();

    xil_printf("  -> mlp_predict: 3) Waiting for finish...\r\n");
    /* 3) Bitene kadar bekle */
    while (!mlp_is_done()) {
        timeout++;
        if (timeout > 10000000) {
            xil_printf("  -> mlp_predict: FATAL ERROR - MLP Hardware TIMEOUT! (No clock?)\r\n");
            return 0; // Fallback
        }
    }

    xil_printf("  -> mlp_predict: 4) Done! Reading result...\r\n");
    /* 4) Sonuç */
    return mlp_get_result();
}

#endif /* MLP_DRIVER_H */
