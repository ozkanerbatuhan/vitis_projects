"""Feature preparation for the host streaming tool.

IMPORTANT, KNOWN LIMITATION
---------------------------
The feature layout produced here is NOT the layout the shipped networks were
trained on, and the two must not be mixed.

Training (see the model repository) builds each 40-element vector as:
    [0:20]   20 slots of successive relative price changes, scaled by 1000
             (19 carry data, one is a constant zero)
    [20:30]  10 trade quantities, each divided by the window mean
    [30:40]  10 taker-side indicators, +1 or -1
    every element clipped to [-5, 5]

This script instead flattens raw prices and quantities. Raw BTCUSDT prices are
about three orders of magnitude outside the Q8.8 range, so streaming them
produces meaningless inference results.

The measurements reported in the paper are unaffected: latency and determinism
do not depend on feature values, and the accuracy and bit-exactness figures
were produced with the training-side features. This script is retained for the
latency and throughput runs, for which any well-scaled input will do. Anyone
wanting real predictions should reimplement the training-side layout here.
"""

import pandas as pd
import numpy as np
import argparse
import os

def prepare_klines_features(df):
    """
    Build a 40-dimensional feature vector from Binance klines
    (Open, High, Low, Close, Volume).

    WARNING: this layout does not match the one the shipped networks were
    trained on. See the note at the top of this file and README.md.
    """
    print("Processing klines: last 8 periods x 5 OHLCV columns = 40 features")
    
    # Select the columns we need. Binance klines order is Open_time, Open,
    # High, Low, Close, Volume, ... Assign default names if absent.
    if 'Close' not in df.columns:
        # Standard Binance klines CSV format:
        cols = ['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 'Quote_asset_volume', 
                'Number_of_trades', 'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore']
        df.columns = cols[:len(df.columns)]
    
    # Keep only the numeric OHLCV columns
    numeric_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
    
    features = []
    # An 8-period window means the first 7 rows are skipped
    for i in range(7, len(numeric_df)):
        # Flatten rows i-7..i (8 rows of OHLCV) into a single 40-column row
        window = numeric_df.iloc[i-7:i+1].values.flatten()
        features.append(window)
        
    feature_df = pd.DataFrame(features)
    return feature_df

def prepare_trades_features(df):
    """
    Build a 40-dimensional feature vector from Binance aggTrades or
    historical trades (Price, Qty).

    WARNING: this layout does not match the one the shipped networks were
    trained on. See the note at the top of this file and README.md.
    """
    print("Processing trades: last 20 trades x price/quantity = 40 features")
    
    if 'price' not in df.columns and 'Price' not in df.columns:
        # Standard aggTrades format:
        cols = ['Aggregate_tradeId', 'Price', 'Quantity', 'First_tradeId', 'Last_tradeId', 'Timestamp', 'IsBuyerMaker', 'IsBestMatch']
        df.columns = cols[:len(df.columns)]
        
    # Locate the price and quantity columns
    price_col = 'Price' if 'Price' in df.columns else 'price'
    qty_col = 'Quantity' if 'Quantity' in df.columns else 'qty'
    
    numeric_df = df[[price_col, qty_col]].apply(pd.to_numeric, errors='coerce').dropna()
    
    features = []
    # A 20-trade window means the first 19 rows are skipped
    for i in range(19, len(numeric_df)):
        window = numeric_df.iloc[i-19:i+1].values.flatten()
        features.append(window)
        
    feature_df = pd.DataFrame(features)
    return feature_df

def main():
    parser = argparse.ArgumentParser(description="Convert Binance data into the 40-feature format used by the host engine.")
    parser.add_argument("--input", required=True, help="Ham Binance CSV dosyasinin yolu")
    parser.add_argument("--output", default="stream_data.csv", help="Cikti dosyasinin yolu (Varsayilan: stream_data.csv)")
    parser.add_argument("--type", choices=['klines', 'trades'], required=True, help="Veri tipi: 'klines' (Mumlar) veya 'trades' (Islemler)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}")
        return
        
    print(f"Dosya okunuyor: {args.input}")
    try:
        # Binance exports sometimes lack a header, so row one may be data
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
        print(f"Done. Data written for the host engine: {args.output}")
        print("Arayuzden (hft_frontend.py) bu dosyayi secerek Gercek Veri Akisini baslatabilirsiniz.")
        
    except Exception as e:
        print(f"Hata olustu: {e}")

if __name__ == "__main__":
    main()
