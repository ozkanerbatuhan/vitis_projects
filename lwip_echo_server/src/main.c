#include <stdio.h>
#include <string.h>
#include "mlp_weight_loader.h"
#include "xparameters.h"
#include "netif/xadapter.h"
#include "lwip/init.h"
#include "lwip/udp.h"
#include "lwip/ip4_addr.h"
#include "lwip/err.h"
#include "lwip/netif.h"

#include "platform.h"
#include "platform_config.h"
#include "mlp_driver.h"
/* ── Per-stage latency instrumentation (paper Table 2 / Table 10) ──
 * Set to 0 to compile the original hot path with zero overhead.
 * Timing is embedded in the UDP reply (1 -> 21 bytes:
 *   [0]=decision, then 5x u32 LE Global-Timer ticks: recv,parse,dma,pl,read)
 * so it runs at FULL line rate — no UART in the hot path.
 * Tick rate = COUNTS_PER_SECOND (Zynq-7000: CPU/2), printed once at boot.
 * Parse the engine's extended CSV with pc_test/parse_stage_timing.py          */
#define ENABLE_STAGE_TIMING 1

#if ENABLE_STAGE_TIMING
/* The 2025.2 SDT platform does not export xtime_l.h, so the Zynq-7000
 * Global Timer at PERIPHBASE+0x200 is read directly. 64-bit, CPU_CLK/2. */
#include "xil_io.h"
#define GT_BASE        0xF8F00200U
#define GT_CNT_LO      (GT_BASE + 0x00U)
#define GT_CNT_HI      (GT_BASE + 0x04U)
#define GT_CTRL        (GT_BASE + 0x08U)
#define GT_TICK_HZ     (XPAR_CPU_CORE_CLOCK_FREQ_HZ / 2U)  /* ~333.333 MHz */

typedef u64 XTime;
static inline void XTime_GetTime(XTime *t) {
    u32 hi, lo;
    do {                       /* hi/lo/hi: 32-bit tasma yarisina karsi */
        hi = Xil_In32(GT_CNT_HI);
        lo = Xil_In32(GT_CNT_LO);
    } while (Xil_In32(GT_CNT_HI) != hi);
    *t = (((u64)hi) << 32) | lo;
}
static inline void gt_enable(void) {
    Xil_Out32(GT_CTRL, Xil_In32(GT_CTRL) | 0x1U);  /* bit 0 = timer enable */
}
static XTime g_t_poll;      /* taken in main loop right before xemacif_input */
#endif

/* ── ARM (Cortex-A9) software inference baseline ───────────────────────────
 * Runs the same network on the PS with the same Q8.8 arithmetic. This
 * measures the premise of the design directly: the fabric core takes
 * 768 ns, so how long does the same work take on the processor?
 * Runs on the board with no DMA and no network involvement.
 * Printed once at boot; never called from the hot path.
 * ───────────────────────────────────────────────────────────────────────── */
#define ARM_L1 64
#define ARM_L2 32
#define ARM_L3 16
#define ARM_L4  3

static s16 arm_a0[64], arm_a1[64], arm_a2[64];

static inline s16 arm_sat(s32 v) {
    if (v >  32767) return  32767;
    if (v < -32768) return -32768;
    return (s16)v;
}

/* Q8.8 weight tables, filled in when a model is loaded */
static s16 armW1[ARM_L1*64], armB1[ARM_L1];
static s16 armW2[ARM_L2*64], armB2[ARM_L2];
static s16 armW3[ARM_L3*32], armB3[ARM_L3];
static s16 armW4[ARM_L4*16], armB4[ARM_L4];
static int arm_weights_ready = 0;

/* One layer: n_out neurons, n_in inputs, Q8.8, >>8, saturate, optional ReLU.
 * Follows the same order as the RTL so that both paths produce identical
 * values.
 *
 * Important: Vitis compiles the application at -O0 by default. An
 * unoptimized software baseline would make the comparison unfair, so the
 * attribute below forces -O3 on these two functions regardless of the
 * global flag. The processor therefore does its best and the comparison
 * stays defensible. */
__attribute__((optimize("O3")))
static void arm_layer(const s16 *in, s16 *out, const s16 *W, const s16 *B,
                      int n_out, int n_in, int relu) {
    int j, i;
    for (j = 0; j < n_out; j++) {
        s64 acc = ((s64)B[j]) << 8;
        const s16 *w = W + (u32)j * (u32)n_in;
        for (i = 0; i < n_in; i++)
            acc += (s32)in[i] * (s32)w[i];
        s16 o = arm_sat((s32)(acc >> 8));
        if (relu && o < 0) o = 0;
        out[j] = o;
    }
}

__attribute__((optimize("O3")))
static u32 arm_infer_once(const s16 *x) {
    s16 o0, o1, o2;
    arm_layer(x,      arm_a0, armW1, armB1, ARM_L1, 64, 1);
    arm_layer(arm_a0, arm_a1, armW2, armB2, ARM_L2, 64, 1);
    arm_layer(arm_a1, arm_a2, armW3, armB3, ARM_L3, 32, 1);
    arm_layer(arm_a2, arm_a0, armW4, armB4, ARM_L4, 16, 0);
    o0 = arm_a0[0]; o1 = arm_a0[1]; o2 = arm_a0[2];
    if (o1 > o0 && o1 > o2) return 1;
    if (o2 > o0 && o2 > o1) return 2;
    return 0;
}

#define ARM_DIST_MAX 1000
static u32 arm_dist[ARM_DIST_MAX];

/* Insertion sort: n <= 1000, called once at boot, speed is irrelevant. */
static void arm_sort_u32(u32 *a, int n) {
    int i, j;
    for (i = 1; i < n; i++) {
        u32 v = a[i];
        for (j = i - 1; j >= 0 && a[j] > v; j--) a[j + 1] = a[j];
        a[j + 1] = v;
    }
}

/* Runs n_iter inferences and prints the mean ns per inference to the UART.
 * synth: 1 for synthetic weights (boot), 0 for real model weights.
 * %s is avoided for the label: xil_printf is a lightweight printf whose
 * format support varies between releases, so two literal formats are safer. */
static void arm_baseline_report(int n_iter, int synth) {
#if ENABLE_STAGE_TIMING
    static s16 x[64];
    XTime t0, t1;
    u64 ticks;
    u32 ns_per, sink = 0;
    int k;

    if (!arm_weights_ready) {
        xil_printf("ARM baseline: weights not loaded yet\r\n");
        return;
    }
    for (k = 0; k < 64; k++) x[k] = (s16)((k * 137) % 511 - 255);

    xil_printf("ARM baseline: starting measurement (%d iterations)\r\n", n_iter);
    arm_infer_once(x);                       /* warm the cache */
    XTime_GetTime(&t0);
    for (k = 0; k < n_iter; k++) sink += arm_infer_once(x);
    XTime_GetTime(&t1);

    ticks  = (u64)(t1 - t0);
    ns_per = (u32)((ticks * 1000000000ULL) / ((u64)GT_TICK_HZ * (u64)n_iter));

    /* Second pass: time each inference individually to obtain the distribution.
     * The hardware cycle counter shows a single-valued distribution, so
     * reporting min/p50/p99/max alongside the mean keeps the software side
     * on the same footing. The instrumentation overhead is two timer reads
     * per inference, on the order of one percent of the measured interval. */
    if (n_iter > ARM_DIST_MAX) n_iter = ARM_DIST_MAX;
    for (k = 0; k < n_iter; k++) {
        XTime a, b;
        XTime_GetTime(&a);
        sink += arm_infer_once(x);
        XTime_GetTime(&b);
        arm_dist[k] = (u32)(((u64)(b - a) * 1000000000ULL) / (u64)GT_TICK_HZ);
    }
    arm_sort_u32(arm_dist, n_iter);
    xil_printf("ARM baseline dist: min=%u p50=%u p99=%u max=%u ns (n=%d)\r\n",
               (unsigned)arm_dist[0],
               (unsigned)arm_dist[n_iter / 2],
               (unsigned)arm_dist[(n_iter * 99) / 100],
               (unsigned)arm_dist[n_iter - 1], n_iter);
    if (synth)
        xil_printf("ARM baseline [synthetic]: %d inferences, %u ns each (sink=%u)\r\n",
                   n_iter, (unsigned)ns_per, (unsigned)sink);
    else
        xil_printf("ARM baseline [model]: %d inferences, %u ns each (sink=%u)\r\n",
                   n_iter, (unsigned)ns_per, (unsigned)sink);
#else
    (void)n_iter; (void)synth;
#endif
}

/* Boot-time variant that runs without a model being loaded.
 *
 * Latency does not depend on the weight VALUES: every inference performs
 * the same number of multiply-accumulate operations. The baseline can
 * therefore be measured with synthetic weights at boot, needing neither a
 * model upload nor the host tooling. The result appears on the UART as
 * soon as the board comes up. */
static void arm_baseline_boot(void) {
    int i;
    for (i = 0; i < ARM_L1*64; i++) armW1[i] = (s16)((i * 37) % 511 - 255);
    for (i = 0; i < ARM_L1;    i++) armB1[i] = (s16)(i % 13);
    for (i = 0; i < ARM_L2*64; i++) armW2[i] = (s16)((i * 29) % 511 - 255);
    for (i = 0; i < ARM_L2;    i++) armB2[i] = (s16)(i % 7);
    for (i = 0; i < ARM_L3*32; i++) armW3[i] = (s16)((i * 17) % 511 - 255);
    for (i = 0; i < ARM_L3;    i++) armB3[i] = (s16)(i % 5);
    for (i = 0; i < ARM_L4*16; i++) armW4[i] = (s16)((i * 11) % 511 - 255);
    for (i = 0; i < ARM_L4;    i++) armB4[i] = (s16)(i % 3);

    arm_weights_ready = 1;
    arm_baseline_report(1000, 1);
    arm_weights_ready = 0;   /* set back to 1 when a real model is loaded */
}

/* ── Network settings ── */
#define BOARD_IP_0      192
#define BOARD_IP_1      168
#define BOARD_IP_2      1
#define BOARD_IP_3      10

#define BOARD_GW_0      192
#define BOARD_GW_1      168
#define BOARD_GW_2      1
#define BOARD_GW_3      1

#define BOARD_NM_0      255
#define BOARD_NM_1      255
#define BOARD_NM_2      255
#define BOARD_NM_3      0

#define BOARD_MAC_0     0x00
#define BOARD_MAC_1     0x0a
#define BOARD_MAC_2     0x35
#define BOARD_MAC_3     0x00
#define BOARD_MAC_4     0x01
#define BOARD_MAC_5     0x02

#define UDP_PORT        7000

/* Q8.8 conversion is now performed on the host */

/* ── Globals ── */
#include "xaxidma.h"

XAxiDma AxiDma;
int DmaInitSuccess = 0;
static unsigned char mac_addr[6] = {BOARD_MAC_0, BOARD_MAC_1, BOARD_MAC_2, BOARD_MAC_3, BOARD_MAC_4, BOARD_MAC_5};
static struct netif server_netif;

/* ── UDP Callback ── */
void udp_recv_callback(void *arg, struct udp_pcb *pcb,
                       struct pbuf *p, const ip_addr_t *addr, u16_t port)
{
    (void)arg;

    if (p == NULL) return;

    u8 *payload = (u8 *)p->payload;
    
    // The first byte is the command type (header)
    u8 cmd = payload[0];

    // Dispatch on the header
    switch (cmd) {
        case 0x01:
        case 'M': {
            /* Case 1: model update command */
            
            // Sanity check: a model is 6819 floats (27.2 KB).
            // Ignore the packet if it is short.
            if (p->tot_len < 4 + (6819 * sizeof(float))) {
                break; // discard the packet
            }

            // lwIP pbufs are chained: a 27 KB packet is split across several of
            // them, so reading 27 KB straight from (payload + 4) causes a data
            // abort. Copy into a flat DDR array with the lwIP helper instead.
            static float model_buffer[6819];
            pbuf_copy_partial(p, model_buffer, 6819 * sizeof(float), 4);

            // Now it is safe to read from contiguous DDR
            float *W1 = model_buffer;
            float *B1 = W1 + (64 * 64);
            
            float *W2 = B1 + 64;
            float *B2 = W2 + (32 * 64);
            
            float *W3 = B2 + 32;
            float *B3 = W3 + (16 * 32);
            
            float *W4 = B3 + 16;
            float *B4 = W4 + (3 * 16);

            // Call the hardware update function from mlp_weight_loader.h
            load_default_network(W1, B1, W2, B2, W3, B3, W4, B4);

            /* Keep the same weights in Q8.8 for the ARM baseline. The conversion
             * is float_to_q88, identical to the hardware path, so both compute
             * the same numbers and the comparison is fair. */
            {
                int i;
                for (i = 0; i < ARM_L1*64; i++) armW1[i] = (s16)float_to_q88(W1[i]);
                for (i = 0; i < ARM_L1;    i++) armB1[i] = (s16)float_to_q88(B1[i]);
                for (i = 0; i < ARM_L2*64; i++) armW2[i] = (s16)float_to_q88(W2[i]);
                for (i = 0; i < ARM_L2;    i++) armB2[i] = (s16)float_to_q88(B2[i]);
                for (i = 0; i < ARM_L3*32; i++) armW3[i] = (s16)float_to_q88(W3[i]);
                for (i = 0; i < ARM_L3;    i++) armB3[i] = (s16)float_to_q88(B3[i]);
                for (i = 0; i < ARM_L4*16; i++) armW4[i] = (s16)float_to_q88(W4[i]);
                for (i = 0; i < ARM_L4;    i++) armB4[i] = (s16)float_to_q88(B4[i]);
                arm_weights_ready = 1;
            }
            arm_baseline_report(1000, 0);  /* prints ns per inference to the UART */

            // Acknowledge the upload to the host
            struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
            if (reply != NULL) {
                ((u8 *)reply->payload)[0] = 0xFF; // ACK
                udp_sendto(pcb, reply, addr, port);
                pbuf_free(reply);
            }
            break;
        }

        case 0x02:
        case 'D': {
            /* Case 2: live feature vector */
            if (p->tot_len >= 4 + (64 * sizeof(s16))) {
#if ENABLE_STAGE_TIMING
                XTime t_cb, t_parse, t_dma, t_pl, t_read;
                XTime_GetTime(&t_cb);   /* packet is ready in the lwIP buffer */
#endif
                static s16 inputs[64] __attribute__((aligned(32)));
                memcpy(inputs, payload + 4, 64 * sizeof(s16));
#if ENABLE_STAGE_TIMING
                XTime_GetTime(&t_parse); /* parse and feature hand-off complete */
#endif

                if (DmaInitSuccess) {
                    // 1. Flush the cache to RAM and start the DMA transfer
                    Xil_DCacheFlushRange((UINTPTR)inputs, 64 * sizeof(s16));
                    int status = XAxiDma_SimpleTransfer(&AxiDma, (UINTPTR)inputs, 64 * sizeof(s16), XAXIDMA_DMA_TO_DEVICE);

#if ENABLE_STAGE_TIMING
                    /* until the MM2S channel drains: PS to PL DMA time */
                    while (XAxiDma_Busy(&AxiDma, XAXIDMA_DMA_TO_DEVICE)) { }
                    XTime_GetTime(&t_dma);
#endif
                    if (status == XST_SUCCESS) {
                        // 2. Wait for done. A tight spin is appropriate at this latency.
                        while ((mlp_read_reg(0x04) & 0x01) == 0) {
                            // spin until the hardware asserts done
                        }
                    }
#if ENABLE_STAGE_TIMING
                    XTime_GetTime(&t_pl);   /* AXI-Stream receive and MLP compute complete */
#endif

                    /* cycle count of this inference, from the RTL counter */
                    u16 cyc = (u16)(mlp_read_reg(0x10) & 0xFFFF);

                    // 3. Argmax: read the three class scores individually
                    s16 out0 = (s16)mlp_read_reg(0x100); // SELL skoru
                    s16 out1 = (s16)mlp_read_reg(0x104); // HOLD skoru
                    s16 out2 = (s16)mlp_read_reg(0x108); // BUY skoru
#if ENABLE_STAGE_TIMING
                    XTime_GetTime(&t_read); /* AXI-Lite result readout complete */
#endif

                    u8 final_decision = 0; // default class
                    if (out1 > out0 && out1 > out2) {
                        final_decision = 1; // HOLD
                    } else if (out2 > out0 && out2 > out1) {
                        final_decision = 2; // BUY
                    }

                    // 4. Return the decision (0, 1, 2) to the host over the network.
                    //    With ENABLE_STAGE_TIMING the reply is the decision plus
                    //    five u32 ticks. The minimum Ethernet frame is 60 bytes
                    //    anyway, so the wire cost is nil, and no UART is used in
                    //    the hot path, so the measurement runs at full rate.
#if ENABLE_STAGE_TIMING
                    /* 29 bytes: [decision][5x u32 ticks][3x s16 raw logits][u16 cycles]
                     * The logits are what makes bit-exact verification possible
                     * and the cycle count is what makes the determinism claim
                     * measurable. The minimum Ethernet frame is 60 bytes, so
                     * growing the reply costs nothing on the wire. */
                    struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 29, PBUF_RAM);
                    if (reply != NULL) {
                        u8 *rp = (u8 *)reply->payload;
                        rp[0] = final_decision;
                        u32 stg[5];
                        stg[0] = (u32)(t_cb    - g_t_poll);  /* recv: EMAC+lwIP  */
                        stg[1] = (u32)(t_parse - t_cb);      /* parse/memcpy     */
                        stg[2] = (u32)(t_dma   - t_parse);   /* AXI-DMA MM2S     */
                        stg[3] = (u32)(t_pl    - t_dma);     /* stream RX + MLP  */
                        stg[4] = (u32)(t_read  - t_pl);      /* AXI-Lite readout */
                        memcpy(rp + 1, stg, sizeof(stg));    /* little-endian    */
                        /* Ham cikis logitleri (SELL, HOLD, BUY) */
                        s16 outs[3] = { out0, out1, out2 };
                        memcpy(rp + 21, outs, sizeof(outs));
                        memcpy(rp + 27, &cyc, sizeof(cyc));   /* cevrim sayisi */
                        udp_sendto(pcb, reply, addr, port);
                        pbuf_free(reply);
                    }
#else
                    struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
                    if (reply != NULL) {
                        ((u8 *)reply->payload)[0] = final_decision;
                        udp_sendto(pcb, reply, addr, port);
                        pbuf_free(reply);
                    }
#endif
                }
            }
            break;
        }

        default:
            // Unrecognised command: a malformed packet or a broadcast
            break;
    }

    pbuf_free(p);
}

int main(void)
{
    ip_addr_t ipaddr, netmask, gw;
    struct udp_pcb *udp_pcb;
    err_t err;
    struct netif *netif_ptr;

    /* Platform init */
    init_platform();

    /* AXI DMA Init */
    XAxiDma_Config *CfgPtr = XAxiDma_LookupConfig(XPAR_XAXIDMA_0_BASEADDR);
    
    if (CfgPtr) {
        if (XAxiDma_CfgInitialize(&AxiDma, CfgPtr) == XST_SUCCESS) {
            XAxiDma_IntrDisable(&AxiDma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
            DmaInitSuccess = 1;

            // Donanimi (MLP IP) acilista yalnizca BIR KERE resetle
            // VHDL Gelistiricisi: Sadece sistemi ilk actiginda 1 yazip hemen ardindan 0 yazmalisin.
            mlp_write_reg(0x00, 1);
            for(volatile int i=0; i<1000; i++); // Kisa bir gecikme
            mlp_write_reg(0x00, 0);
        }
    }

    /* LwIP init */
    lwip_init();

    IP4_ADDR(&ipaddr,  BOARD_IP_0, BOARD_IP_1, BOARD_IP_2, BOARD_IP_3);
    IP4_ADDR(&netmask, BOARD_NM_0, BOARD_NM_1, BOARD_NM_2, BOARD_NM_3);
    IP4_ADDR(&gw,      BOARD_GW_0, BOARD_GW_1, BOARD_GW_2, BOARD_GW_3);

    server_netif.hwaddr_len = 6;
    memcpy(server_netif.hwaddr, mac_addr, 6);

    netif_ptr = xemac_add(&server_netif, &ipaddr, &netmask, &gw,
                          mac_addr, PLATFORM_EMAC_BASEADDR);
    if (!netif_ptr) {
        return -1;
    }
    netif_set_default(netif_ptr);
    netif_set_up(netif_ptr);

    udp_pcb = udp_new();
    if (udp_pcb == NULL) {
        return -1;
    }

    err = udp_bind(udp_pcb, IP_ADDR_ANY, UDP_PORT);
    if (err != ERR_OK) {
        return -1;
    }

    udp_recv(udp_pcb, udp_recv_callback, NULL);

#if ENABLE_STAGE_TIMING
    gt_enable();  /* Start the Global Timer; the xiltimer BSP may leave it disabled */
    /* Announce the tick rate once for the host parser (CPU_FREQ/2) */
    xil_printf("TIMFREQ,%u\r\n", (u32)GT_TICK_HZ);
    arm_baseline_boot();   /* print the ARM baseline; needs no model or host */
#endif

    while (1) {
#if ENABLE_STAGE_TIMING
        /* Timestamp taken immediately before pulling the frame from the EMAC,
         * so the recv column is EMAC DMA plus lwIP stack processing time,
         * that is NIC to UDP buffer. */
        XTime_GetTime(&g_t_poll);
#endif
        xemacif_input(netif_ptr);
    }
    cleanup_platform();
    return 0;
}
