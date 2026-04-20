import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# 1. Veriyi Yükle (Pandas ile 1 milyon satır anında yüklenir)
csv_file = "latencies.csv"
if not os.path.exists(csv_file):
    print(f"HATA: {csv_file} bulunamadı!")
    exit()

df = pd.read_csv(csv_file)

# 2. İstatistikleri Hesapla
total_packets = len(df)
mean_lat = df['Latency_us'].mean()
p99_lat = df['Latency_us'].quantile(0.99)
max_lat = df['Latency_us'].max()
min_lat = df['Latency_us'].min()

# 3. Grafik Teması (Karanlık HFT Teması)
plt.style.use('dark_background')
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle('Zynq FPGA - MLP Gerçek Zamanlı Çıkarım Analizi', fontsize=18, fontweight='bold', color='cyan')

# --- SOL GRAFİK: Zaman Çizelgesi ve Jitter Analizi ---
# 1 milyon noktayı üst üste çizip bilgisayarı dondurmamak için s=1 (nokta boyutu) ve alpha=0.3 (şeffaflık) kullanıyoruz
ax1.scatter(df['Packet'], df['Latency_us'], color='lime', alpha=0.3, s=1)
ax1.axhline(mean_lat, color='white', linestyle='-', linewidth=1.5, label=f'Ortalama: {mean_lat:.1f} µs')
ax1.axhline(p99_lat, color='red', linestyle='--', linewidth=2, label=f'%99 Sınırı: {p99_lat:.1f} µs')

ax1.set_title('Paket Bazlı Gecikme (Jitter Dağılımı)', color='lightgray', fontsize=14)
ax1.set_xlabel('Paket Numarası (Zaman)', fontsize=12)
ax1.set_ylabel('Gecikme (µs)', fontsize=12)
ax1.legend(loc='upper right', facecolor='black', edgecolor='white')
ax1.grid(True, color='#333333', linestyle=':')

# --- SAĞ GRAFİK: Gecikme Histogramı ---
# O devasa 3.4 ms'lik tek tük sıçramalar, asıl 111 us'lik kuleyi ezmesin diye 
# X eksenini üst %0.1'lik kısmı kırparak gösteriyoruz.
p999_lat = df['Latency_us'].quantile(0.999)
filtered_df = df[df['Latency_us'] <= p999_lat]

ax2.hist(filtered_df['Latency_us'], bins=100, color='dodgerblue', edgecolor='black', alpha=0.8)
ax2.axvline(mean_lat, color='white', linestyle='-', linewidth=2, label=f'Ortalama: {mean_lat:.1f} µs')

ax2.set_title('Gecikme Dağılımı (Uç %0.1 Değerler Gizlenmiş)', color='lightgray', fontsize=14)
ax2.set_xlabel('Gecikme (µs)', fontsize=12)
ax2.set_ylabel('Frekans (Paket Sayısı)', fontsize=12)
ax2.legend(loc='upper right', facecolor='black', edgecolor='white')
ax2.grid(True, color='#333333', linestyle=':')

# --- BİLGİ KUTUCUĞU ---
stats_text = (
    f"--- TEST ÖZETİ ---\n"
    f"Toplam Paket: {total_packets:,}\n"
    f"Min Gecikme: {min_lat:.1f} µs\n"
    f"Max Gecikme: {max_lat:.1f} µs\n"
    f"Ortalama: {mean_lat:.1f} µs\n"
    f"%99 Sınırı: {p99_lat:.1f} µs"
)
props = dict(boxstyle='round', facecolor='#111111', alpha=0.9, edgecolor='cyan')
ax2.text(0.95, 0.5, stats_text, transform=ax2.transAxes, fontsize=12,
         verticalalignment='center', horizontalalignment='right', bbox=props, color='white', fontfamily='monospace')

# 4. Kaydet ve Göster
plt.tight_layout()
file_name = "hft_latency_pro_analysis.png"
plt.savefig(file_name, dpi=300, bbox_inches='tight')
print(f"\n[+] Grafik başarıyla çizildi ve '{file_name}' olarak kaydedildi!")
plt.show()
