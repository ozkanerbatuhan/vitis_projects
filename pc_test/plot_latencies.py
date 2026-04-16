import csv
import matplotlib.pyplot as plt
import numpy as np
import os

def analyze_and_plot(csv_file):
    if not os.path.exists(csv_file):
        print(f"Hata: {csv_file} bulunamadi.")
        return

    print("Veriler yukleniyor (1 Milyon satir olabilir, biraz bekleyin)...")
    latencies = []
    
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        next(reader) # Baslik atla
        for row in reader:
            if len(row) >= 2:
                latencies.append(float(row[1]))

    if not latencies:
        print("Dosya bos.")
        return

    lats = np.array(latencies)
    
    # -------------------------------------
    # 1. ISTATISTIKSEL ANALIZ VE FILTRELEME
    # -------------------------------------
    total_packets = len(lats)
    p50 = np.percentile(lats, 50)
    p99 = np.percentile(lats, 99)
    p99_9 = np.percentile(lats, 99.9)
    p99_99 = np.percentile(lats, 99.99)
    
    outliers = lats[lats > 1000] # 1 milisaniyeden (1000us) yavas olanlar (Windows Spikeleri)
    
    print("\n--- DETAYLI GECIKME ANALIZI ---")
    print(f"Toplam Paket        : {total_packets:,}")
    print(f"Minimum Gecikme     : {np.min(lats):.1f} us  <-- HFT REKORU!")
    print(f"Medyen (Ortanca)    : {p50:.1f} us")
    print(f"99. Yuzdelik        : {p99:.1f} us (Paketlerin %99'u bundan hizli)")
    print(f"99.9 Yuzdelik       : {p99_9:.1f} us")
    print(f"99.99 Yuzdelik      : {p99_99:.1f} us")
    print(f"1000us Ustu Anomali : {len(outliers)} adet ( %{(len(outliers)/total_packets)*100:.3f} )")
    
    # -------------------------------------
    # 2. GRAFIKLERI CIZ
    # -------------------------------------
    # 1.000.000 noktayi tek ekrana basmak PC'yi kasar ve anlamsizdir.
    # Bu yuzden veriyi 2 farkli formatta sunacagiz.
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # GRAFIK 1: HISTOGRAM (Dagilim)
    # Windows hatalarini gormezden gelmek icin grafikte max 800us'ye kadar olan skalayi cizdiriyoruz
    filtered_lats = lats[lats < 800]
    ax1.hist(filtered_lats, bins=200, color='royalblue', alpha=0.7)
    ax1.axvline(np.mean(filtered_lats), color='red', linestyle='dashed', linewidth=2, label=f'Ortalama: {np.mean(filtered_lats):.1f}us')
    ax1.axvline(np.min(lats), color='green', linestyle='dashed', linewidth=2, label=f'Min: {np.min(lats):.1f}us')
    ax1.set_title("Gecikme Dagilimi (Histogram, 800us alti)")
    ax1.set_xlabel("Gecikme (us)")
    ax1.set_ylabel("Paket Sayisi")
    ax1.legend()
    ax1.grid(alpha=0.3)

    # GRAFIK 2: DOWNSAMPLED (Seyreltilmis) TIME SERIES
    # 1 Milyon veriyi her 1000 pakette 1 tane alinacak sekilde seyreltiyoruz.
    step = max(1, total_packets // 1000)
    downsampled_x = np.arange(0, total_packets, step)
    downsampled_y = lats[::step]
    
    ax2.plot(downsampled_x, downsampled_y, color='coral', alpha=0.8, linewidth=1, marker='.', markersize=2)
    ax2.axhline(p99, color='red', linestyle='--', alpha=0.5, label=f'%99 Siniri: {p99:.1f}us')
    ax2.set_title("Seyreltilmis Zaman Cizelgesi (Her 1000 pakette 1 ornek)")
    ax2.set_xlabel("Paket Numarasi")
    ax2.set_ylabel("Gecikme (us)")
    ax2.set_ylim(0, max(1000, p99_9)) # Y in asirisini kes ki cizgi gorunsun
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.suptitle("Zynq HFT-MLP 1 Milyon Paket Performans Analizi", fontsize=16)
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    analyze_and_plot('latencies.csv')
