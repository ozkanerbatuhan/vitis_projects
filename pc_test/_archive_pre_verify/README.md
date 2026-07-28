# Arşiv — doğrulama koşumu öncesi loglar

Bu dosyalar **silinmedi, taşındı**. `pc_test/` ve `pc_test/linux/` temizlendi ki yeni doğrulama koşumları eski satırların üstüne eklenmesin (motor log'u `ios::app` ile açıyor — bu, satır hizalamasını bozan ve doğrulamayı anlamsız kılan sessiz bir tuzak).

| Dosya | Ne | Durum |
|---|---|---|
| `2026-07-12_1M-paket_TABLO10-KAYNAGI.csv` | 1,004,229 paketlik koşum, aşama tick'leriyle | **SAKLA — makalenin Tablo 10'unun kaynağı.** Tüm hücreleri bu dosyadan yeniden ürettim, birebir tutuyor. |
| `2026-07-12_1M-paket_TABLO10-KAYNAGI_linuxkopya.csv` | Yukarıdakinin birebir kopyası (md5 aynı) | Yedek |
| `2026-07-12_karisik-model_KULLANMA.csv` | 853,221 satır | **Kullanma.** `yapılacaklar.txt`'ye göre eski + permütasyonlu etiketli satırlar karışık. |
| `2026-05-30_rastgele-model-rastgele-veri.csv` | Rastgele model + rastgele veri testi | Tarihsel |
| `2026-07-12_windows-kosumu.csv` | Windows host koşumu | Bölüm 5.4'teki Linux/Windows karşılaştırmasını destekliyor olabilir — **silmeyin** |
| `2026-07-12_asama-zamanlari_turetilmis.csv` | `parse_stage_timing.py` çıktısı | Türetilmiş, yeniden üretilebilir |

## Önemli

Tablo 10 (aşama bazlı gecikme dökümü) ve Tablo 8 (uçtan uca gecikme) **geçerli sonuçlar** ve bu arşivdeki veriye dayanıyor. Doğruluk/kuantizasyon sonuçlarının aksine bunlarda bir sorun yok — yeniden ölçüm gerektirmiyorlar.

Silinmesi gereken hiçbir şey yok. Yeni koşumlar `HFT_LOG` ortam değişkeniyle ayrı dosyalara yazacağı için karışma riski de kalmadı.
