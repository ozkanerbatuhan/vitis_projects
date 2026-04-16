#ifndef MLP_DRIVER_H
#define MLP_DRIVER_H

#include "xil_io.h"
#include "xparameters.h"
#include "xaxidma.h"
#include "xil_cache.h"

extern XAxiDma AxiDma;
extern int DmaInitSuccess;

#ifndef MLP_FEATURE_COUNT
#define MLP_FEATURE_COUNT 40
#endif

#ifndef MLP_BASE_ADDR
#define MLP_BASE_ADDR  XPAR_MLP_AXI_WRAPPER_0_BASEADDR
#endif

/* Register offsets */
#define MLP_REG_CTRL    0x00   /* W:  bit0 = start                           */
#define MLP_REG_STATUS  0x04   /* R:  bit0 = done, bit1 = busy               */
#define MLP_REG_INPUT   0x08   /* W:  [15:0]=data, [21:16]=addr              */
#define MLP_REG_RESULT  0x0C   /* R:  [1:0] = class (0=SELL,1=HOLD,2=BUY)    */

static inline void mlp_write_reg(u32 offset, u32 value) {
    Xil_Out32(MLP_BASE_ADDR + offset, value);
}

static inline u32 mlp_read_reg(u32 offset) {
    return Xil_In32(MLP_BASE_ADDR + offset);
}

/* AXI-Lite INPUT ve START kaldirildi - DMA + AXI-Stream tarafindan yapiliyor */

static inline int mlp_is_done(void) {
    return (mlp_read_reg(MLP_REG_STATUS) & 0x1);
}

static inline int mlp_is_busy(void) {
    return (mlp_read_reg(MLP_REG_STATUS) >> 1) & 0x1;
}

static inline u32 mlp_get_result(void) {
    return mlp_read_reg(MLP_REG_RESULT) & 0x3;
}

static inline u32 mlp_predict(s16 *inputs) {
    int timeout = 0;

    if (!DmaInitSuccess) {
        return 0; // DMA calismiyorsa Data Abort almamak icin bekleme/yazma yapma
    }

    /* Islemcinin L1/L2 onbellegini DDR'a yaz (DMA RAM'den okuyacak) */
    Xil_DCacheFlushRange((UINTPTR)inputs, MLP_FEATURE_COUNT * sizeof(s16));

    /* DMA ile RAM'den AXI-Stream uzerinden PL'e yolla (Tek Komut) */
    XAxiDma_SimpleTransfer(&AxiDma, (UINTPTR)inputs, 
                           MLP_FEATURE_COUNT * sizeof(s16), 
                           XAXIDMA_DMA_TO_DEVICE);

    /* VHDL tarafi AXI-Stream TLAST alinca hesabi otomatik baslatacak */

    while (!mlp_is_done()) {
        timeout++;
        if (timeout > 10000000) {
            return 0; // Fallback
        }
    }
    return mlp_get_result();
}

#endif /* MLP_DRIVER_H */
