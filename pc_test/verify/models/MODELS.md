# Doğrulama modelleri

Dosya adı topolojiyi kodluyor: `mlp_<giriş>_<h1>_<h2>_<h3>_<çıkış>_<md5>.pth`

Hash, aynı topolojiye sahip farklı dosyaları ayırt etmek için — daha önce iki ayrı `best_model_new.pth` vardı ve hangisinin koşulduğu belirsizdi. Bu, Tablo 6'nın yeniden üretilememesinin muhtemel sebeplerinden biri.

## Koşulacak modeller

| Dosya | Topoloji | Doğrulama akışındaki çıkış dağılımı | Kaynak |
|---|---|---|---|
| `mlp_40_64_32_16_3_bfdb6941.pth` | 40→64→32→16→3 | `[10019, 3273, 6708]` | `best_model_new.pth` |
| `mlp_40_64_64_32_3_7e3943ab.pth` | 40→64→64→32→3 | `[2702, 8952, 8346]` | `best_model_64_64_32_t00005.pth` |
| `mlp_40_32_16_8_3_fa8bb051.pth` | 40→32→16→8→3 | `[3509, 8102, 8389]` | `best_model_32_16_8_t00005.pth` |
| `mlp_40_10_16_8_3_1421e245.pth` | 40→10→16→8→3 | `[7011, 6246, 6743]` | `best_model_10_16_8_t00005.pth` |

Dağılımlar 20,000 satırlık doğrulama akışında emülatörle hesaplandı. Dördü de üç sınıfa dengeli yayılıyor (en baskın sınıf ≤%50) — yani karar eşleşmesi anlamlı bir test olacak.

**İlk üçü yeterli.** Dördüncüsü isterseniz.

Bu dördü **makalenin asıl sonucunu** da veriyor: aynı bitstream, dört farklı topoloji, yeniden sentez yok. Birinci hidden layer 10 ile 64 arasında, katman genişlikleri tamamen farklı.

## Reddedilen

`rejected/mlp_40_64_32_16_3_22039252.pth` — `linux/best_model_new.pth`'den geliyor. **Dejenere**: 20,000 girdinin tamamına aynı sınıfı veriyor (`[20000, 0, 0]`).

Doğrulama için kullanmayın. Böyle bir modelde karar eşleşmesi hiçbir şey kanıtlamaz — donanım tamamen bozuk olsa bile eşleşme yüksek çıkar. (Eski FPGA logunun %91.4'ünün tek sınıf olması ve makaledeki "%96.85 match" değerinin buradan gelmiş olması kuvvetle muhtemel.)
