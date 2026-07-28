# Bit-Exact Doğrulama — Tezgâh Runbook'u

**Amaç:** FPGA çekirdeğinin altın yazılım modeliyle bit-birebir aynı sonucu ürettiğini, dört farklı topolojide, ~100k çıkarım üzerinde göstermek.

**Bu bir doğruluk (accuracy) ölçümü değildir.** Modelin iyi olup olmadığından bağımsızdır. Q8.8 veri yolunun hatasız çalıştığını kanıtlar — hakemin "ağın doğru çalıştığını nereden biliyoruz?" sorusunu kapatır.

**Gerekmeyen:** RTL değişikliği, yeniden sentez, yeni bitstream, yeniden eğitim.
**Gereken:** Vitis'te firmware derleyip BOOT.bin yenilemek (~10 dk) + koşumlar.

---

## Durum — yapılmış olanlar

Aşağıdakiler **uygulandı ve test edildi**, sizin yapmanıza gerek yok:

- ✅ **Yama 1** — `linux/hft_engine_linux.cpp`: `f2q88()` eklendi, iki cast değiştirildi. Taşan değerler artık sessizce sarmalanmıyor, RTL'in `saturate()`'i gibi doyuruyor.
- ✅ **Yama 2a** — `lwip_echo_server/src/main.c`: yanıt 21→27 bayt, 3 ham logit ekleniyor.
- ✅ **Yama 2b** — `linux/hft_engine_linux.cpp`: log başlığına `out0,out1,out2`, kayıt bloğuna logit yazımı.
- ✅ **`HFT_LOG` ortam değişkeni** — koşum başına ayrı log dosyası. Manuel log silmeye gerek kalmadı.
- ✅ Engine `g++ -O2 -Wall` ile temiz derlendi.
- ✅ Eski loglar `pc_test/_archive_pre_verify/` altına taşındı (silinmedi — Tablo 10'un kaynağı orada).
- ✅ Modeller `verify/models/` altında topolojiye göre isimlendirildi, dejenere olan ayıklandı.
- ✅ Doğrulayıcı, mevcut `quantization_analysis.py` ile çapraz doğrulandı (ağırlık kuantizasyonu, ileri yayılım, argmax — üçü de birebir aynı).

**Size kalan:** BOOT.bin'i yenilemek ve 3-4 koşum yapmak.

---

## Adım 1 — Firmware'i yenile

Vitis'te `lwip_echo_server`'ı yeniden derleyin ve BOOT.bin'i karta yükleyin. RTL değişmedi, yeniden sentez yok.

> Kontrol: yanıt artık 27 bayt. Doğrulayıcı 27 bayt gelmezse "firmware yamasi uygulanmamis" diyecek.

## Adım 2 — Engine'i derle

```bash
cd /mnt/d/vitis_projects/pc_test/linux
g++ -O2 -o hft_engine_linux hft_engine_linux.cpp -lpthread
```

## Adım 3 — Test akışını üret

```bash
cd /mnt/d/vitis_projects/pc_test/verify
python3 make_verify_stream.py --rows 100000 --out verify_stream.csv
```

Piyasa CSV'si yerine bunu kullanıyoruz: ham aggTrades verisi Q8.8 aralığının ~600 katı dışında, taştığı için doğrulamaya elverişli değil. Bu dosya Q8.8'e sığar ve veri yolunun tüm yollarını (ReLU kesme, `saturate()`, 40-bit akümülatör, sıfır dolgu, işaret geçişleri, tek-sıcak vektörler) bilinçli olarak zorlar. Sabit seed → aynı komut aynı dosyayı üretir.

## Adım 4 — Koşumlar

Her model için: GUI'den modeli yükle, `verify_stream.csv`'yi akıt.

**Engine'i başlatırken `HFT_LOG` verin** — her koşum kendi dosyasına yazar, karışma olmaz:

```bash
cd /mnt/d/vitis_projects/pc_test/linux

HFT_LOG=log_mlp_40_64_32_16_3.csv  ./hft_engine_linux     # koşum 1
HFT_LOG=log_mlp_40_64_64_32_3.csv  ./hft_engine_linux     # koşum 2
HFT_LOG=log_mlp_40_32_16_8_3.csv   ./hft_engine_linux     # koşum 3
HFT_LOG=log_mlp_40_10_16_8_3.csv   ./hft_engine_linux     # koşum 4 (isteğe bağlı)
```

GUI ayarları her koşumda aynı:

1. **Select Model (.bin)** → `verify/models/` içinden ilgili `.pth`
2. **Send Model**
3. **Select CSV** → `verify/verify_stream.csv`
4. Inter-packet delay = **0**
5. **Start Stream** → 100k satır bitene kadar

Hangi modeller ve neden: `verify/models/MODELS.md`.

> `rejected/` klasöründeki modeli kullanmayın — tüm girdilere aynı sınıfı veriyor, doğrulama anlamsız çıkar.

## Adım 5 — Doğrula

```bash
cd /mnt/d/vitis_projects/pc_test/verify

python3 verify_bitexact.py --stream verify_stream.csv \
  --log ../linux/log_mlp_40_64_32_16_3.csv --model models/mlp_40_64_32_16_3_bfdb6941.pth

python3 verify_bitexact.py --stream verify_stream.csv \
  --log ../linux/log_mlp_40_64_64_32_3.csv --model models/mlp_40_64_64_32_3_7e3943ab.pth

python3 verify_bitexact.py --stream verify_stream.csv \
  --log ../linux/log_mlp_40_32_16_8_3.csv --model models/mlp_40_32_16_8_3_fa8bb051.pth
```

**Başarı kriteri:** her koşumda `SONUC: BIT-EXACT DOGRULANDI`, karar eşleşmesi **%100.0000** ve logit eşleşmesi **%100.0000**.

## Adım 6 — Bana gönderin

`linux/log_mlp_*.csv` dosyalarını olduğu gibi bırakın, haber verin — sonuçları ben işleyip makaleye girecek metni ve tabloyu yazarım.

---

## Sorun çıkarsa

| Belirti | Sebep |
|---|---|
| `LOGIT eslesmesi: yok` | BOOT.bin yenilenmemiş, kart hâlâ 21 baytlık yanıt dönüyor |
| Eşleşme %100'ün biraz altında | Engine yamasız binary'den koşuyor → `g++` adımını tekrarlayın. Yamasız test edecekseniz `--legacy-cast` ekleyin |
| Eşleşme rastgele seviyede (~%33-50) | Yanlış model yüklü — GUI'de yüklediğinizle `--model` aynı mı? |
| `!! log icinde N ek header satiri` | Aynı `HFT_LOG` adıyla iki kez koşulmuş. Dosyayı silip tekrarlayın |
| Belirli satırlarda logit farkı | **Gerçek bulgu.** Doğrulayıcı ilk 5 farkı yazdırır. ±1 LSB ise yuvarlama, büyükse `saturate()` yolu — bana gönderin |
| Timeout satırları | Akış çok hızlı; delay'i 1 ms yapıp tekrarlayın |

---

## Makaleye ne yazılacak

Başarılı koşumdan sonra Bölüm 5'e girecek taslak:

> **Fixed-Point Verification.** The deployed pipeline was replayed bit-for-bit in
> software — host quantization, weight conversion, the 40-bit accumulate,
> arithmetic right-shift, saturation, ReLU, and the argmax rule — and compared
> against the hardware over 100,000 inferences using a stimulus set constructed
> to exercise the saturation, ReLU, sign-transition and zero-padding paths. The
> hardware matched the golden model on 100% of decisions and on all 300,000 raw
> int16 output values. The same bitstream was verified against three networks of
> different topologies (40-64-32-16-3, 40-64-64-32-3, 40-32-16-8-3) loaded at
> runtime over AXI-Lite without re-synthesis.

Bu paragraf Tablo 6'nın yerini alır ve ondan çok daha güçlüdür: bir doğruluk iddiası değil, bir doğrulama iddiasıdır ve tamamen sizin kontrolünüzdedir. İkinci cümle aynı zamanda makalenin "framework" iddiasının kanıtı — şu an hiç yazılmamış durumda.


