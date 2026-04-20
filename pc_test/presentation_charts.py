import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# --- 1. Veriyi Yükle ---
csv_file = "latencies.csv"
if not os.path.exists(csv_file):
    print(f"ERROR: {csv_file} not found!")
    exit()

df = pd.read_csv(csv_file)
latencies = df['Latency_us']

# --- İstatistikleri Hesapla ---
mean_lat = latencies.mean()
median_lat = latencies.median()
p99_lat = latencies.quantile(0.99)
p999_lat = latencies.quantile(0.999)
max_lat = latencies.max()
min_lat = latencies.min()

# --- Grafik Ayarları (Sunum Kalitesi) ---
plt.style.use('default') # Temiz beyaz arka plan
plt.rcParams.update({'font.size': 12, 'font.family': 'sans-serif'})


# ==========================================
# CHART 1: Core Latency Distribution (Histogram)
# Amac: Paketin %99'unun nerede yigildigini gosterir.
# ==========================================
plt.figure(figsize=(10, 6))
# 3.4ms'lik uclari grafikten gizleyip asil kuleye odaklaniyoruz
filtered_latencies = latencies[latencies <= p999_lat]

plt.hist(filtered_latencies, bins=80, color='#2c3e50', edgecolor='white', alpha=0.9)
plt.axvline(mean_lat, color='#e74c3c', linestyle='dashed', linewidth=2, label=f'Mean: {mean_lat:.1f} µs')
plt.axvline(p99_lat, color='#e67e22', linestyle='dotted', linewidth=2, label=f'99th Pct: {p99_lat:.1f} µs')

plt.title('Zynq Real-Time Inference: Latency Distribution', fontsize=16, fontweight='bold', pad=15)
plt.xlabel('Latency (Microseconds)', fontsize=14)
plt.ylabel('Number of Packets', fontsize=14)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.legend(loc='upper right', fontsize=12)

plt.tight_layout()
plt.savefig('slide1_distribution.png', dpi=300)
plt.close()


# ==========================================
# CHART 2: Cumulative Distribution Function (CDF)
# Amac: HFT dunyasinin en onemli grafigi. "Paketlerin %X'i Y suresinin altindadir" der.
# ==========================================
plt.figure(figsize=(10, 6))
sorted_data = np.sort(latencies)
yvals = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

plt.plot(sorted_data, yvals, color='#2980b9', linewidth=2)
plt.axhline(0.99, color='#e67e22', linestyle='--', alpha=0.8)
plt.axvline(p99_lat, color='#e67e22', linestyle='--', alpha=0.8, label=f'99% < {p99_lat:.1f} µs')

# X eksenini anlamsiz uclari gostermemek icin sinirliyoruz
plt.xlim(min_lat - 10, p999_lat + 20) 
plt.ylim(0, 1.05)

plt.title('Cumulative Distribution Function (CDF)', fontsize=16, fontweight='bold', pad=15)
plt.xlabel('Latency (Microseconds)', fontsize=14)
plt.ylabel('Cumulative Probability', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='lower right', fontsize=12)

plt.tight_layout()
plt.savefig('slide2_cdf.png', dpi=300)
plt.close()


# ==========================================
# CHART 3: Percentile Breakdown (Bar Chart)
# Amac: Yoneticilere/Hocalara net rakamlari tek bakista gostermek.
# ==========================================
plt.figure(figsize=(10, 6))
labels = ['Min', 'Median', 'Mean', '99th Pct', '99.9th Pct']
values = [min_lat, median_lat, mean_lat, p99_lat, p999_lat]
colors = ['#27ae60', '#3498db', '#2980b9', '#f39c12', '#d35400']

bars = plt.bar(labels, values, color=colors, edgecolor='black', alpha=0.8)

# Barlarin uzerine degerleri yazdirma
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 1, f'{yval:.1f} µs', 
             ha='center', va='bottom', fontweight='bold', fontsize=11)

plt.title('Key Latency Metrics Overview', fontsize=16, fontweight='bold', pad=15)
plt.ylabel('Latency (Microseconds)', fontsize=14)
plt.grid(axis='y', linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('slide3_percentiles.png', dpi=300)
plt.close()


# ==========================================
# CHART 4: System Stability & Jitter Analysis (Timeline)
# Amac: 1 Milyon paketi noktalara bogmak yerine, her 5000 paketteki (Window) "Ortalama" ve "Maksimum" sicramalari gosterir.
# ==========================================
plt.figure(figsize=(12, 5))

window_size = 5000
df['Window'] = np.arange(len(df)) // window_size
grouped = df.groupby('Window')['Latency_us']

window_means = grouped.mean()
window_maxs = grouped.max()
x_axis = window_means.index * window_size

plt.plot(x_axis, window_means, color='#2980b9', label='Mean Latency (per 5K packets)', linewidth=2)
plt.plot(x_axis, window_maxs, color='#e74c3c', label='Max Latency (Jitter / OS Interrupts)', linewidth=1, alpha=0.6)

plt.title('System Stability over 1 Million Inferences', fontsize=16, fontweight='bold', pad=15)
plt.xlabel('Packet Sequence Number', fontsize=14)
plt.ylabel('Latency (Microseconds)', fontsize=14)
# Y eksenini yine cok uclara kacirmamak icin mantikli bir degere sabitliyoruz (orn: 500us)
plt.ylim(0, 500) 
plt.grid(True, linestyle='--', alpha=0.5)
plt.legend(loc='upper right', fontsize=12)

plt.tight_layout()
plt.savefig('slide4_stability.png', dpi=300)
plt.close()

print("\n[+] Success! 4 high-resolution presentation charts have been generated in the current folder.")
