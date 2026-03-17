"""
test_mlp.py — HFT-MLP ZedBoard UDP Test İstemcisi

ZedBoard'a 40 adet float (160 byte) gönderir,
MLP inference sonucunu (SELL/HOLD/BUY) alır.

Kullanım:
    python test_mlp.py
"""

import socket
import struct
import random
import time

# ── Ayarlar ──
BOARD_IP   = "192.168.1.10"
BOARD_PORT = 7000
TIMEOUT    = 2.0   # saniye

LABELS = {0: "SELL", 1: "HOLD", 2: "BUY"}


def send_prediction(features: list[float], sock: socket.socket) -> int | None:
    """40 float gönder, 1 byte sonuç al."""
    payload = struct.pack('<40f', *features)
    
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(payload, ("255.255.255.255", BOARD_PORT))
    try:
        data, _ = sock.recvfrom(64)
        return data[0]
    except socket.timeout:
        return None


def main():
    print("=" * 50)
    print("  HFT-MLP ZedBoard Test Istemcisi")
    print(f"  Hedef: {BOARD_IP}:{BOARD_PORT}")
    print("=" * 50)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    
    sock.bind(("192.168.1.100", 0))

    # --- Tek seferlik test ---
    print("\n[1] Tek paket testi:")
    features = [random.uniform(-1.0, 1.0) for _ in range(40)]
    print(f"    Gönderiliyor: {len(features)} feature, 160 byte")

    result = send_prediction(features, sock)
    if result is not None:
        print(f"    Sonuç: {LABELS.get(result, '?')} ({result})")
    else:
        print("    HATA: Zaman aşımı — yanıt gelmedi!")
        print("    Kontrol et:")
        print("      - ZedBoard açık ve programlanmış mı?")
        print("      - Ethernet kablosu bağlı mı?")
        print("      - PC IP adresi 192.168.1.x alt ağında mı?")
        sock.close()
        return

    # --- Çoklu test (gecikme ölçümü) ---
    print(f"\n[2] 1000 paket gecikme testi:")
    latencies = []
    for i in range(1000):
        features = [random.uniform(-1.0, 1.0) for _ in range(40)]
        t0 = time.perf_counter()
        result = send_prediction(features, sock)
        t1 = time.perf_counter()

        if result is not None:
            latency_us = (t1 - t0) * 1_000_000
            latencies.append(latency_us)
           #print(f"    [{i+1:2d}] {LABELS.get(result, '?'):4s}  |  {latency_us:8.1f} µs")
        else:
            #print(f"    [{i+1:2d}] Zaman aşımı!")
            pass

    if latencies:
        avg = sum(latencies) / len(latencies)
        mn  = min(latencies)
        mx  = max(latencies)
        print(f"\n    Ortalama: {avg:.1f} µs")
        print(f"    Min:      {mn:.1f} µs")
        print(f"    Max:      {mx:.1f} µs")

    print("\n" + "=" * 50)
    sock.close()


if __name__ == "__main__":
    main()
