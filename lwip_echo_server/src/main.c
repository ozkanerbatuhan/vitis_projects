/*
 * main.c — HFT MLP ZedBoard Uygulaması
 *
 * UDP Port 7000'den 40 adet float (Q8.8) alır,
 * MLP'ye gönderir, sonucu LED'de gösterir ve UDP ile geri yollar.
 */
#include <stdio.h>
#include <string.h>

#include "xparameters.h"
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

/* ── Q8.8 dönüşüm ── */
#define FLOAT_TO_Q88(f)  ((s16)((f) * 256.0f))

/* ── Global değişkenler ── */
static unsigned char mac_addr[6] = {BOARD_MAC_0, BOARD_MAC_1, BOARD_MAC_2, BOARD_MAC_3, BOARD_MAC_4, BOARD_MAC_5};
static struct netif server_netif;

/* ── UDP Callback ── */
void udp_recv_callback(void *arg, struct udp_pcb *pcb,
                       struct pbuf *p, const ip_addr_t *addr, u16_t port)
{
    (void)arg;

    if (p == NULL) return;
    if (p->tot_len >= MLP_FEATURE_COUNT * sizeof(float)) {
        float raw[MLP_FEATURE_COUNT];
        /* p->payload is NOT 4-byte aligned (offset by 42 bytes typically), 
         * reading directly from it as float* causes ARM Data Abort exceptions! 
         * Must copy to an aligned local buffer first. */
        memcpy(raw, p->payload, MLP_FEATURE_COUNT * sizeof(float));
        
        s16 inputs[MLP_FEATURE_COUNT];
        int i;

        /* float → Q8.8 dönüşüm */
        for (i = 0; i < MLP_FEATURE_COUNT; i++) {
            inputs[i] = FLOAT_TO_Q88(raw[i]);
        }

        /* MLP inference */
        u32 result = mlp_predict(inputs);

        /* Sonucu geri gönder (1 byte) */
        struct pbuf *reply = pbuf_alloc(PBUF_TRANSPORT, 1, PBUF_RAM);
        if (reply != NULL) {
            ((u8 *)reply->payload)[0] = (u8)result;
            udp_sendto(pcb, reply, addr, port);
            pbuf_free(reply);
        }
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

    /* LwIP init */
    lwip_init();

    /* IP adresleri ayarla (IP4_ADDR ile güvenilir) */
    IP4_ADDR(&ipaddr,  BOARD_IP_0, BOARD_IP_1, BOARD_IP_2, BOARD_IP_3);
    IP4_ADDR(&netmask, BOARD_NM_0, BOARD_NM_1, BOARD_NM_2, BOARD_NM_3);
    IP4_ADDR(&gw,      BOARD_GW_0, BOARD_GW_1, BOARD_GW_2, BOARD_GW_3);

    /* MAC adresini netif'e kopyala */
    server_netif.hwaddr_len = 6;
    memcpy(server_netif.hwaddr, mac_addr, 6);

    /* Ağ arayüzünü ekle */
    netif_ptr = xemac_add(&server_netif, &ipaddr, &netmask, &gw,
                          mac_addr, PLATFORM_EMAC_BASEADDR);
    if (!netif_ptr) {
        return -1;
    }
    netif_set_default(netif_ptr);
    netif_set_up(netif_ptr);

    /* UDP PCB oluştur ve bağla */
    udp_pcb = udp_new();
    if (udp_pcb == NULL) {
        return -1;
    }

    err = udp_bind(udp_pcb, IP_ADDR_ANY, UDP_PORT);
    if (err != ERR_OK) {
        return -1;
    }

    udp_recv(udp_pcb, udp_recv_callback, NULL);

    /* Ana döngü — LwIP paketlerini işle */
    while (1) {
        xemacif_input(netif_ptr);
    }

    /* Buraya gelinmemeli */
    cleanup_platform();
    return 0;
}
