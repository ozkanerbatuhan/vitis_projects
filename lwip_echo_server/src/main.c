/*
 * main.c — HFT MLP ZedBoard Uygulaması
 *
 * UDP Port 7000'den 40 adet float (Q8.8) alır,
 * MLP'ye gönderir, sonucu LED'de gösterir ve UDP ile geri yollar.
 */
#include <stdio.h>
#include <string.h>

#include "xparameters.h"
#include "xil_printf.h"
#include "netif/xadapter.h"
#include "lwip/init.h"
#include "lwip/udp.h"
#include "lwip/ip4_addr.h"
#include "lwip/err.h"
#include "lwip/netif.h"
#include "lwip/timeouts.h"

#include "platform.h"
#include "platform_config.h"
#include "mlp_driver.h"

/* ── Ağ Ayarları ── */
#define UDP_PORT        7000

/* ── Q8.8 dönüşüm ── */
#define FLOAT_TO_Q88(f)  ((s16)((f) * 256.0f))

/* ── MAC adresi (Xilinx OUI: 00:0a:35) ── */
static unsigned char mac_addr[6] = {0x00, 0x0a, 0x35, 0x00, 0x01, 0x02};

/* ── Global değişkenler ── */
static struct netif server_netif;
static const char *result_names[] = {"SELL", "HOLD", "BUY"};

/* ── UDP Callback ── */
void udp_recv_callback(void *arg, struct udp_pcb *pcb,
                       struct pbuf *p, const ip_addr_t *addr, u16_t port)
{
    (void)arg;

    if (p == NULL) return;
    
    xil_printf("!!! udp_recv TRG: %d byte geldi. !!!\r\n", p->tot_len);

    /*
     * Beklenen payload: 40 x float (160 byte)
     * Her float PC tarafından little-endian gönderilir,
     * ARM Cortex-A9 da little-endian olduğu için doğrudan okunur.
     */
    if (p->tot_len >= 40 * sizeof(float)) {
        float raw[40];
        /* p->payload is NOT 4-byte aligned (offset by 42 bytes typically), 
         * reading directly from it as float* causes ARM Data Abort exceptions! 
         * Must copy to an aligned local buffer first. */
        memcpy(raw, p->payload, 40 * sizeof(float));
        
        s16 inputs[40];
        int i;

        /* float → Q8.8 dönüşüm */
        for (i = 0; i < 40; i++) {
            inputs[i] = FLOAT_TO_Q88(raw[i]);
        }

        /* MLP inference */
        u32 result = mlp_predict(inputs);
        xil_printf("Prediction: %s (%d)\r\n", result_names[result], result);

        /* Sonucu geri gönder (1 byte) */
        struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
        if (reply != NULL) {
            ((u8 *)reply->payload)[0] = (u8)result;
            udp_sendto(pcb, reply, addr, port);
            pbuf_free(reply);
        }
    } else {
        xil_printf("WARN: Beklenen 160 byte, gelen %d byte\r\n", p->tot_len);
    }

    pbuf_free(p);
}

/* ── Ana Program ── */
int main(void)
{
    ip_addr_t ipaddr, netmask, gw;
    struct udp_pcb *udp_pcb;
    err_t err;
    struct netif *netif_ptr;

    /* Platform init */
    init_platform();

    xil_printf("\r\n");
    xil_printf("========================================\r\n");
    xil_printf("  HFT-MLP ZedBoard - Baslatiliyor...\r\n");
    xil_printf("========================================\r\n");

    /* LwIP init */
    lwip_init();

    /* IP adresleri ayarla (IP4_ADDR ile güvenilir) */
    IP4_ADDR(&ipaddr,  192, 168, 1, 10);
    IP4_ADDR(&netmask, 255, 255, 255, 0);
    IP4_ADDR(&gw,      192, 168, 1, 1);

    /* MAC adresini netif'e kopyala */
    server_netif.hwaddr_len = 6;
    memcpy(server_netif.hwaddr, mac_addr, 6);

    xil_printf("MAC: %02x:%02x:%02x:%02x:%02x:%02x\r\n",
               mac_addr[0], mac_addr[1], mac_addr[2],
               mac_addr[3], mac_addr[4], mac_addr[5]);

    /* Ağ arayüzünü ekle */
    netif_ptr = xemac_add(&server_netif, &ipaddr, &netmask, &gw,
                          mac_addr, PLATFORM_EMAC_BASEADDR);
    if (!netif_ptr) {
        xil_printf("HATA: xemac_add basarisiz!\r\n");
        return -1;
    }
    netif_set_default(netif_ptr);
    netif_set_up(netif_ptr);

    xil_printf("IP : 192.168.1.10\r\n");
    xil_printf("Port: %d (UDP)\r\n", UDP_PORT);

    /* UDP PCB oluştur ve bağla */
    udp_pcb = udp_new();
    if (udp_pcb == NULL) {
        xil_printf("HATA: udp_new basarisiz!\r\n");
        return -1;
    }

    err = udp_bind(udp_pcb, IP_ADDR_ANY, UDP_PORT);
    if (err != ERR_OK) {
        xil_printf("HATA: udp_bind basarisiz (%d)\r\n", err);
        return -1;
    }

    udp_recv(udp_pcb, udp_recv_callback, NULL);

    xil_printf("UDP dinlemede... Veri bekleniyor.\r\n");
    xil_printf("========================================\r\n");

    /* Ana döngü — LwIP paketlerini işle */
    while (1) {
        xemacif_input(netif_ptr);
    }

    /* Buraya gelinmemeli */
    cleanup_platform();
    return 0;
}
