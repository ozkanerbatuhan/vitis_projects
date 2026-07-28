# Makale TBD ölçümleri — durum ve talimatlar (2026-07-12)

## ✅ Şimdi dolu: Table 4 (Quantization evaluation)

`pc_test/quantization_analysis.py` ile, mevcut `execution_log_linux.csv` (164.628 paket),
`temp_stream_converted.csv` ve `temp_weights.bin` üzerinden — **board'a dokunmadan** — alındı.
Emülatör bit-exact: C++ int16 dönüşümü (cvttss2si semantiği), firmware `float_to_q88`
(truncation), VHDL 40-bit accumulator + `>>8` + saturate + ReLU, main.c argmax kuralı.

| Metrik | Değer |
|---|---|
| Output match rate (Python Q8.8 vs FPGA argmax) | **96.85 %** (159 447 / 164 627) |
| Max absolute error (float vs Q8.8, çıkış katmanı) | **1.374** (mean 0.335) |
| Class change ratio (float vs Q8.8 argmax) | **0.074 %** |
| Q8.8 ↔ float agreement | **99.93 %** |
| Per-class F1 (float referans, SELL/HOLD/BUY) | 0.971 / 1.000 / 1.000 (macro **0.990**) |

Notlar:
1. **"Python Q8.8 accuracy" hücresi**: repoda etiketli test seti yok; accuracy ancak
   float model referans alınarak (agreement/F1, yukarıda) raporlanabilir. Ground-truth
   accuracy istenirse eğitimdeki etiketli test setiyle aynı script tekrar koşulur.
2. **Bulgu — etiket eşlemesi hatası (DÜZELTİLDİ)**: firmware 0=SELL, 1=HOLD, 2=BUY
   gönderiyordu; engine 0→HOLD, 1→BUY, 2→SELL diye logluyordu. `linux/hft_engine_linux.cpp`
   ve `win/hft_engine.cpp` düzeltildi (yeniden derlenmeli: `g++ -O2 -o hft_engine_linux
   hft_engine_linux.cpp -lpthread`). ESKİ loglar (execution_log_linux.csv dahil) hâlâ
   permütasyonlu — analiz scripti varsayılan olarak geri çevirir; düzeltilmiş engine ile
   alınan YENİ loglar için `--fixed-log` bayrağını kullanın.
3. Kalan %3.15 uyumsuzluk bitişik bloklar halinde → UDP reply kaybı/gecikmesi kaynaklı
   satır kayması (reply'da sequence no yok). Makalede "≥96.9 % (UDP, sequence-untagged)"
   diye raporlanabilir.
4. Stream dosyası ham aggTrades kolonları içeriyor (feature pipeline değil); Q8.8 girişleri
   int16'ya sarılıyor/satüre oluyor. Ölçüm deployed sistemin birebir kopyası, ancak
   normalize feature'larla tekrar koşu makale için daha temiz olur (`data_prep_binance.py`
   çıktısı + normalizasyon → board replay).

## ⚙ Board koşusu gerektiren: Table 2 + Table 10 (Measured sütunu)

Firmware patch'i uygulandı: `lwip_echo_server/src/main.c`, `ENABLE_STAGE_TIMING 1`
(0 yapınca orijinal hot path, sıfır overhead). Ölçüm noktaları:

- `recv`  = EMAC poll → UDP callback (NIC→buffer, Table 2 #1 / Table 10 #9)
- `parse` = header + memcpy (Table 2 #2 / Table 10 #10)
- `dma`   = MM2S transfer, `XAxiDma_Busy` bitene kadar (Table 2 #3 / Table 10 #11)
- `pl`    = DMA sonu → done biti (AXI-Stream alım + MLP hesabı, Table 10 #12)
- `read`  = 3× AXI-Lite register okuma (Table 10 #13)
- `total` = callback → reply gönderildi

**Raporlama UART'sız — UDP reply'a gömülü** (UART hot path'i bloklayıp throughput'u
~285 pkt/s'e düşürürdü; 66.3 µs koşusu ~9.5k pkt/s idi). Reply 1 → 21 bayt:
`[karar][5× u32 LE tick: recv,parse,dma,pl,read]`. Min Ethernet frame zaten 60 B
olduğundan tel maliyeti ~0; ölçüm TAM hızda alınır. Engine bu tick'leri
`execution_log_linux.csv`'ye ek kolon olarak yazar (eski firmware ile boş kalır).
Boot'ta UART'a bir kez `TIMFREQ,<Hz>` basılır (sadece bilgi).

> **Not (Vitis 2025.2 SDT):** platform `xtime_l.h` export etmediği için patch Global
> Timer'ı (0xF8F00200) doğrudan okur — ek BSP ayarı gerekmez. Tick frekansı
> `XPAR_CPU_CORE_CLOCK_FREQ_HZ/2` = **333 333 343 Hz** (parser'a `--freq 333333343`).

### SD karttan otomatik boot (BOOT.bin yenileme)
Rebuild sonrası SD'deki BOOT.bin ESKİ elf'i içerir — yeniden paketlemek şart:
1. Vitis Unified IDE'de sağ tık lwip_echo_server → *Create Boot Image* (mevcut
   `BIF_HFT.bif` kullanılabilir), **veya** XSCT/komut satırından:
   `bootgen -arch zynq -image D:\vitis_projects\BIF_HFT.bif -w -o D:\vitis_projects\BOOT.bin`
   (BIF zaten doğru sırayla: fsbl.elf → mlp_system_wrapper.bit → build\lwip_echo_server.elf)
2. Yeni `BOOT.bin`'i SD'nin FAT32 birinci bölümüne kopyala (eskisinin üstüne).
3. Zedboard boot jumper'ları SD konumunda kalıyor (değişiklik yok); kartı tak, aç.
4. Ölçüm bitince `ENABLE_STAGE_TIMING 0` ile rebuild + adım 1-2'yi tekrarla.

### Koşu adımları
1. Vitis'te `lwip_echo_server`'ı rebuild et (`ENABLE_STAGE_TIMING 1`), board'u aç.
2. Engine'i yeniden derle: `g++ -O2 -o hft_engine_linux hft_engine_linux.cpp -lpthread`.
3. Eski `execution_log_linux.csv`'yi yedekle/taşı (yeni başlık yazılsın diye).
4. Normal akışı başlat (model + stream) — hız sınırlaması YOK, birkaç bin paket yeter.
5. `python3 pc_test/parse_stage_timing.py execution_log_linux.csv`
   → aşama başına mean/p50/p99/min/max + ham `stage_timing_us.csv`.
   PS clock 667 MHz değilse `--freq <COUNTS_PER_SECOND>` verin (boot'taki TIMFREQ).

Not: `pl` sütunu AXI-Stream alımı + MLP hesabını birlikte ölçer; Table 10 #12'yi ayrı
ayrıştırmak isterseniz RTL sim cycle sayımı (mlp_tb) Expected sütununa yazılabilir.
Not: (Latency_us − aşamalar toplamı) = PC tarafı NIC/OS + tel + reply yolu.
Not: Makale koşusu bittikten sonra `ENABLE_STAGE_TIMING 0` yapıp rebuild ederek
orijinal 1 baytlık reply'a dönebilirsiniz; engine iki formatı da destekler.

## ✓ Elde olan 2 hücre
Table 2 #4 ve Table 10 #14 (packet-to-decision total) = **66.3 µs** (Table 9, Linux end-to-end).

## Dosyalar
- `lwip_echo_server/src/main.c` — timing patch (ENABLE_STAGE_TIMING ile kapatılabilir)
- `pc_test/quantization_analysis.py` — Table 4 (tekrar üretilebilir)
- `pc_test/parse_stage_timing.py` — Table 2/10 istatistikleri
