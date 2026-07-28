#!/usr/bin/env python3
"""
Bit-exact dogrulama icin test akis dosyasi ureticisi.

Neden ayri bir dosya:
  Piyasa CSV'si (temp_stream_converted.csv) Q8.8 araligi disinda kaliyor ve
  host tarafinda sarmalaniyor -> dogrulama icin elverissiz. Bu script,
  Q8.8'e sigan, datapath'in TUM yollarini (pozitif/negatif, ReLU kesme,
  40-bit akumulator, saturate(), sifir dolgu) zorlayan deterministik bir
  vektor kumesi uretir.

Cikti formati:
  40 sutunlu, header'siz CSV. Host motoru her satiri tokenize edip
  int16 Q8.8'e cevirir ve 64'e sifir doldurur -- yani gercek akisla
  ayni yolu izler.

Kullanim:
  python3 make_verify_stream.py --rows 100000 --out verify_stream.csv
"""
import argparse
import numpy as np

N_FEAT = 40
SEED = 20260728          # sabit -> tekrar uretilebilir


def build(n_rows: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    rows = []

    # --- 1) Kenar durumlari: elle secilmis, datapath'i zorlayan satirlar ---
    edge = [
        np.zeros(N_FEAT),                                    # tum sifir
        np.full(N_FEAT,  127.99609375),                      # Q8.8 pozitif tavan
        np.full(N_FEAT, -128.0),                             # Q8.8 negatif taban
        np.full(N_FEAT,  1.0 / 256),                         # en kucuk pozitif LSB
        np.full(N_FEAT, -1.0 / 256),                         # en kucuk negatif LSB
        np.tile([127.99609375, -128.0], N_FEAT // 2),        # maks salinim
        np.tile([-128.0, 127.99609375], N_FEAT // 2),
        np.linspace(-128.0, 127.99609375, N_FEAT),           # rampa
        np.linspace(127.99609375, -128.0, N_FEAT),           # ters rampa
    ]
    # tek-sicak: her oznitelik sirayla tavana, kalani sifir
    for i in range(N_FEAT):
        v = np.zeros(N_FEAT); v[i] = 127.99609375; edge.append(v)
        v = np.zeros(N_FEAT); v[i] = -128.0;       edge.append(v)
    rows.extend(edge)

    # --- 2) Rastgele blok: dagilimi karisik tut ---
    remaining = max(0, n_rows - len(rows))
    if remaining:
        # %40 dar aralik (ReLU/isaret gecislerini yogun ornekler)
        # %40 orta aralik
        # %20 genis aralik (akumulator + saturate yollarini zorlar)
        n_a = int(remaining * 0.4)
        n_b = int(remaining * 0.4)
        n_c = remaining - n_a - n_b
        blocks = [
            rng.uniform(-2.0,   2.0,   size=(n_a, N_FEAT)),
            rng.uniform(-16.0,  16.0,  size=(n_b, N_FEAT)),
            rng.uniform(-128.0, 127.99, size=(n_c, N_FEAT)),
        ]
        rand = np.vstack(blocks)
        rng.shuffle(rand, axis=0)
        rows.extend(rand)

    a = np.asarray(rows[:n_rows], dtype=np.float64)

    # Q8.8 izgarasina otur: host cast'i trunc yapiyor; tam izgara degerleri
    # kullanirsak CSV metin -> float -> int16 yolunda belirsizlik kalmaz.
    q = np.trunc(a * 256.0)
    q = np.clip(q, -32768, 32767)
    return q / 256.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100000)
    ap.add_argument("--out", default="verify_stream.csv")
    args = ap.parse_args()

    a = build(args.rows)
    # %.6f yeterli: tum degerler 1/256'nin tam katlari (~0.0039), kayip yok
    np.savetxt(args.out, a, delimiter=",", fmt="%.6f")

    print(f"[ok] {a.shape[0]} satir x {a.shape[1]} oznitelik -> {args.out}")
    print(f"     deger araligi [{a.min():.4f}, {a.max():.4f}]  (Q8.8 siniri -128 .. +127.996)")
    print(f"     seed={SEED} -> ayni komut ayni dosyayi uretir")
    print()
    print("     Not: host motoru her satiri 64'e sifir doldurur; oznitelik 40-63 = 0.")


if __name__ == "__main__":
    main()
