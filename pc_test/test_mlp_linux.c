#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <time.h>

/* ── Ayarlar ── */
#define BOARD_IP        "192.168.1.10"
#define BOARD_PORT      7000
#define LOCAL_IP        "0.0.0.0"
#define FEATURE_COUNT   40
#define TIMEOUT_MS      2000
#define BENCH_ROUNDS    1000000
#define WARMUP_ROUNDS   5000

/* ── Etiketler ── */
static const char *LABELS[] = {"SELL", "HOLD", "BUY"};

/* ── Global Arrayler ── */
static double latencies[BENCH_ROUNDS];
static int results_arr[BENCH_ROUNDS];

/* ── Q8.8 donusum ── */
static inline int16_t float_to_q88(float f) {
    return (int16_t)(f * 256.0f);
}

/* ── Rastgele float [-1.0, 1.0] ── */
static float rand_float(void) {
    return ((float)rand() / (float)RAND_MAX) * 2.0f - 1.0f;
}

static int send_prediction(float *features, int sock, struct sockaddr_in *dest) {
    int16_t payload[FEATURE_COUNT];
    int i;
    for (i = 0; i < FEATURE_COUNT; i++) {
        payload[i] = float_to_q88(features[i]);
    }

    sendto(sock, (const char *)payload, sizeof(payload), 0, (struct sockaddr *)dest, sizeof(*dest));

    char buf[64];
    struct sockaddr_in from;
    socklen_t fromlen = sizeof(from);

    int n = recvfrom(sock, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fromlen);
    if (n > 0) {
        return (unsigned char)buf[0];
    }
    return -1;
}

int main(void) {
    int sock;
    struct sockaddr_in local_addr, board_addr;
    struct timespec t0, t1;
    int lat_count = 0;
    int i;

    /* UDP soket olustur */
    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        perror("HATA: socket olusturulamadi");
        return 1;
    }

    /* Timeout ayarla */
    struct timeval tv;
    tv.tv_sec = TIMEOUT_MS / 1000;
    tv.tv_usec = (TIMEOUT_MS % 1000) * 1000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    /* Yerel adrese bagla */
    memset(&local_addr, 0, sizeof(local_addr));
    local_addr.sin_family = AF_INET;
    local_addr.sin_addr.s_addr = inet_addr(LOCAL_IP);
    local_addr.sin_port = htons(0);

    if (bind(sock, (struct sockaddr *)&local_addr, sizeof(local_addr)) < 0) {
        perror("HATA: bind basarisiz");
        close(sock);
        return 1;
    }

    /* Hedef adres */
    memset(&board_addr, 0, sizeof(board_addr));
    board_addr.sin_family = AF_INET;
    board_addr.sin_addr.s_addr = inet_addr(BOARD_IP);
    board_addr.sin_port = htons(BOARD_PORT);

    srand((unsigned int)time(NULL));

    printf("==================================================\n");
    printf("  HFT-MLP ZedBoard LINUX Test Istemcisi (C/POSIX)\n");
    printf("  Hedef : %s:%d\n", BOARD_IP, BOARD_PORT);
    printf("  Payload: %d feature x 2 byte = %d byte (Q8.8)\n", FEATURE_COUNT, FEATURE_COUNT * 2);
    printf("==================================================\n");

    /* --- [1] Tek paket testi --- */
    printf("\n[1] Tek paket testi:\n");
    float features[FEATURE_COUNT];
    for (i = 0; i < FEATURE_COUNT; i++) {
        features[i] = rand_float();
    }

    int result = send_prediction(features, sock, &board_addr);
    if (result >= 0 && result <= 2) {
        printf("    Sonuc: %s (%d)\n", LABELS[result], result);
    } else {
        printf("    HATA: Zaman asimi - yanit gelmedi!\n");
        close(sock);
        return 1;
    }

    /* --- [2] Warmup --- */
    printf("\n[2] WARMUP: %d paket gonderiliyor (KASE/ARP isinmasi)...\n", WARMUP_ROUNDS);
    for (i = 0; i < WARMUP_ROUNDS; i++) {
        int j;
        for (j = 0; j < FEATURE_COUNT; j++) {
            features[j] = rand_float();
        }
        send_prediction(features, sock, &board_addr);
    }
    printf("    Isinma tamamlandi!\n");

    /* --- [3] Benchmark --- */
    printf("\n[3] %d paket gercek gecikme testi basliyor...\n", BENCH_ROUNDS);
    for (i = 0; i < BENCH_ROUNDS; i++) {
        int j;
        for (j = 0; j < FEATURE_COUNT; j++) {
            features[j] = rand_float();
        }

        // Linux nanosaniye bazli yuksek hassasiyetli kronometre
        clock_gettime(CLOCK_MONOTONIC, &t0);
        result = send_prediction(features, sock, &board_addr);
        clock_gettime(CLOCK_MONOTONIC, &t1);

        if (result >= 0) {
            double us = (double)(t1.tv_sec - t0.tv_sec) * 1000000.0 +
                        (double)(t1.tv_nsec - t0.tv_nsec) / 1000.0;
            results_arr[lat_count] = result;
            latencies[lat_count++] = us;
        }
    }

    /* Istatistikler */
    if (lat_count > 0) {
        double sum = 0, mn = latencies[0], mx = latencies[0];
        for (i = 0; i < lat_count; i++) {
            sum += latencies[i];
            if (latencies[i] < mn) mn = latencies[i];
            if (latencies[i] > mx) mx = latencies[i];
        }
        printf("\n    Basarili: %d / %d\n", lat_count, BENCH_ROUNDS);
        printf("    Ortalama: %.1f us\n", sum / lat_count);
        printf("    Min:      %.1f us\n", mn);
        printf("    Max:      %.1f us\n", mx);

        /* CSV'ye kaydet */
        FILE *f = fopen("latencies.csv", "w");
        if (f) {
            fprintf(f, "Packet,Latency_us,Result\n");
            for (i = 0; i < lat_count; i++) {
                fprintf(f, "%d,%.1f,%d\n", i + 1, latencies[i], results_arr[i]);
            }
            fclose(f);
            printf("\n    > Graph verisi 'latencies.csv' dosyasina kaydedildi.\n");
        }
    } else {
        printf("\n    HATA: Hicbir paket yanit almadi!\n");
    }

    printf("\n==================================================\n");
    close(sock);
    return 0;
}
