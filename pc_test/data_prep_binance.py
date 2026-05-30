import pandas as pd
import numpy as np
import argparse
import os

def prepare_klines_features(df):
    """
    Binance Klines verisinden (Open, High, Low, Close, Volume) 
    40 boyutlu bir feature vektörü çıkarır.
    Mantık: Son 8 periyodun OHLCV değerlerini yan yana dizmek (8 * 5 = 40 feature).
    """
    print("Klines verisi işleniyor (Son 8 periyot x 5 OHLCV sütunu = 40 Feature)...")
    
    # Gerekli sütunları alalım (Binance Klines formatı: Open_time, Open, High, Low, Close, Volume, ...)
    # Sütun isimleri yoksa veya farklıysa diye varsayılan isimleri verelim
    if 'Close' not in df.columns:
        # Standart Binance Klines CSV formatı:
        cols = ['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 'Quote_asset_volume', 
                'Number_of_trades', 'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore']
        df.columns = cols[:len(df.columns)]
    
    # Sadece sayısal OHLCV verisini al
    numeric_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
    
    features = []
    # 8 periyot geriye bakacağımız için ilk 7 satırı atlıyoruz
    for i in range(7, len(numeric_df)):
        # i-7'den i'ye kadar olan (8 satır) OHLCV değerlerini tek bir satır (40 sütun) yap
        window = numeric_df.iloc[i-7:i+1].values.flatten()
        features.append(window)
        
    feature_df = pd.DataFrame(features)
    return feature_df

def prepare_trades_features(df):
    """
    Binance AggTrades veya Historical Trades verisinden (Price, Qty)
    40 boyutlu bir feature vektörü çıkarır.
    Mantık: Son 20 işlemin Price ve Qty değerlerini yan yana dizmek (20 * 2 = 40 feature).
    """
    print("Trades verisi işleniyor (Son 20 işlem x Price/Qty = 40 Feature)...")
    
    if 'price' not in df.columns and 'Price' not in df.columns:
        # Standart AggTrades formatı:
        cols = ['Aggregate_tradeId', 'Price', 'Quantity', 'First_tradeId', 'Last_tradeId', 'Timestamp', 'IsBuyerMaker', 'IsBestMatch']
        df.columns = cols[:len(df.columns)]
        
    # Price ve Quantity sütunlarını bul
    price_col = 'Price' if 'Price' in df.columns else 'price'
    qty_col = 'Quantity' if 'Quantity' in df.columns else 'qty'
    
    numeric_df = df[[price_col, qty_col]].apply(pd.to_numeric, errors='coerce').dropna()
    
    features = []
    # 20 periyot geriye bakacağımız için ilk 19 satırı atlıyoruz
    for i in range(19, len(numeric_df)):
        window = numeric_df.iloc[i-19:i+1].values.flatten()
        features.append(window)
        
    feature_df = pd.DataFrame(features)
    return feature_df

def main():
    parser = argparse.ArgumentParser(description="Binance verilerini HFT FPGA motoru icin 40 feature formatina donusturur.")
    parser.add_argument("--input", required=True, help="Ham Binance CSV dosyasinin yolu")
    parser.add_argument("--output", default="stream_data.csv", help="Cikti dosyasinin yolu (Varsayilan: stream_data.csv)")
    parser.add_argument("--type", choices=['klines', 'trades'], required=True, help="Veri tipi: 'klines' (Mumlar) veya 'trades' (Islemler)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Hata: Girdi dosyasi bulunamadi: {args.input}")
        return
        
    print(f"Dosya okunuyor: {args.input}")
    try:
        # Binance verilerinde bazen header olmayabilir, ilk satir veri olabilir
        df = pd.read_csv(args.input, header=0)
        
        if args.type == 'klines':
            feature_df = prepare_klines_features(df)
        else:
            feature_df = prepare_trades_features(df)
            
        # Normalizasyon veya Scaling gerekliyse buraya eklenebilir.
        # Orn: feature_df = (feature_df - feature_df.mean()) / feature_df.std()
            
        print(f"Olusturulan Feature Matrisi Boyutu: {feature_df.shape} (Satir, Sutun)")
        
        if feature_df.shape[1] != 40:
            print(f"DIKKAT: Feature sayisi 40 olmali ama {feature_df.shape[1]} cikti!")
            
        feature_df.to_csv(args.output, index=False, header=False)
        print(f"Basarili! FPGA motoruna hazir veri kaydedildi: {args.output}")
        print("Arayuzden (hft_frontend.py) bu dosyayi secerek Gercek Veri Akisini baslatabilirsiniz.")
        
    except Exception as e:
        print(f"Hata olustu: {e}")

if __name__ == "__main__":
    main()
