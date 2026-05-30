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

/* ── Ağ Ayarları ── */
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

/* Q8.8 donusumu artik PC tarafinda yapiliyor */

/* ── Global değişkenler ── */
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
    
    // Ilk Byte komut tipini belirliyor (Header)
    u8 cmd = payload[0];

    // Trafik Polisi (Header Switch-Case)
    switch (cmd) {
        case 0x01:
        case 'M': {
            /* DURUM 1: MODEL GÜNCELLEME KOMUTU */
            
            // GUVENLIK KONTROLU: Model 6819 adet float bekliyor (27.2 KB). 
            // Eksik paket gelirse isleme alma.
            if (p->tot_len < 4 + (6819 * sizeof(float))) {
                break; // Paketi cope at
            }

            // LwIP pbuf ZINCIRLEME (Chained) calisir!
            // Buyuk paketler (27KB) birden fazla pbuf'a bolunur.
            // Dogrudan (payload + 4) adresinden sirayla 27KB okumak Data Abort (CPU cokmesi) yaratir.
            // Bu yuzden LwIP fonksiyonu ile veriyi duz bir DDR dizisine kopyaliyoruz:
            static float model_buffer[6819];
            pbuf_copy_partial(p, model_buffer, 6819 * sizeof(float), 4);

            // Artik guvenle tek parca halindeki DDR belleiginden okuyabiliriz:
            float *W1 = model_buffer;
            float *B1 = W1 + (64 * 64);
            
            float *W2 = B1 + 64;
            float *B2 = W2 + (32 * 64);
            
            float *W3 = B2 + 32;
            float *B3 = W3 + (16 * 32);
            
            float *W4 = B3 + 16;
            float *B4 = W4 + (3 * 16);

            // mlp_weight_loader.h icerisindeki donanim guncelleme fonksiyonunu cagir
            load_default_network(W1, B1, W2, B2, W3, B3, W4, B4);

            // Frontend'e islemin basarili olduguna dair ACK gonder
            struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
            if (reply != NULL) {
                ((u8 *)reply->payload)[0] = 0xFF; // ACK (Tamamlandi)
                udp_sendto(pcb, reply, addr, port);
                pbuf_free(reply);
            }
            break;
        }

        case 0x02:
        case 'D': {
            /* DURUM 2: CANLI HFT VERİSİ */
            if (p->tot_len >= 4 + (64 * sizeof(s16))) {
                static s16 inputs[64] __attribute__((aligned(32)));
                memcpy(inputs, payload + 4, 64 * sizeof(s16));

                if (DmaInitSuccess) {
                    // 1. Cache'i RAM'e bosalt ve DMA transferini baslat
                    Xil_DCacheFlushRange((UINTPTR)inputs, 64 * sizeof(s16));
                    int status = XAxiDma_SimpleTransfer(&AxiDma, (UINTPTR)inputs, 64 * sizeof(s16), XAXIDMA_DMA_TO_DEVICE);

                    if (status == XST_SUCCESS) {
                        // 2. DONE BEKLEME: Donanimin bitirme hizina yarasir sekilde basit bekleme
                        while ((mlp_read_reg(0x04) & 0x01) == 0) {
                            // Sadece bekle, donanim kesme yapana kadar (veya done sinyali gelene kadar)
                        }
                    }

                    // 3. ARGMAX HESABI: Sonuclari (SELL, HOLD, BUY skorlarini) ayri ayri oku
                    s16 out0 = (s16)mlp_read_reg(0x100); // SELL skoru
                    s16 out1 = (s16)mlp_read_reg(0x104); // HOLD skoru
                    s16 out2 = (s16)mlp_read_reg(0x108); // BUY skoru

                    u8 final_decision = 0; // Varsayilan: SELL
                    if (out1 > out0 && out1 > out2) {
                        final_decision = 1; // HOLD
                    } else if (out2 > out0 && out2 > out1) {
                        final_decision = 2; // BUY
                    }

                    // 4. Ag uzerinden Python Arayuzune nihai karari (0, 1, 2) don
                    struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
                    if (reply != NULL) {
                        ((u8 *)reply->payload)[0] = final_decision;
                        udp_sendto(pcb, reply, addr, port);
                        pbuf_free(reply);
                    }
                }
            }
            break;
        }

        default:
            // Tanimlanmayan bir komut geldiyse (Bozuk paket veya broadcast)
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

    while (1) {
        xemacif_input(netif_ptr);
    }
    cleanup_platform();
    return 0;
}
