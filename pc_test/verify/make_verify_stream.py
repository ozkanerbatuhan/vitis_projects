#!/usr/bin/env python3
"""
Generate the stimulus stream used for bit-exact verification.

Why a separate file:
  Recorded market data is unsuitable as a verification stimulus. Trained
  features are clipped to a narrow band, so replaying them never drives the
  accumulator towards saturation and never exercises the clamping logic: it
  cannot distinguish a correct datapath from one whose saturation path is
  broken. This script instead produces a deterministic vector set that fits
  in Q8.8 while deliberately exercising every path in the datapath, including
  positive and negative operands, ReLU clamping, the 40-bit accumulator,
  saturate() and zero padding.

Output format:
  40-column CSV with no header. The host engine tokenizes each row, converts
  to int16 Q8.8 and zero-pads to 64, i.e. exactly the path a live stream
  follows.

Usage:
  python3 make_verify_stream.py --rows 100000 --out verify_stream.csv
"""
import argparse
import numpy as np

N_FEAT = 40
SEED = 20260728          # sabit -> tekrar uretilebilir


def build(n_rows: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    rows = []

    # --- 1) Corner cases: hand-picked rows that stress the datapath ---
    edge = [
        np.zeros(N_FEAT),                                    # all zero
        np.full(N_FEAT,  127.99609375),                      # Q8.8 pozitif tavan
        np.full(N_FEAT, -128.0),                             # Q8.8 negatif taban
        np.full(N_FEAT,  1.0 / 256),                         # en kucuk pozitif LSB
        np.full(N_FEAT, -1.0 / 256),                         # en kucuk negatif LSB
        np.tile([127.99609375, -128.0], N_FEAT // 2),        # maximum swing
        np.tile([-128.0, 127.99609375], N_FEAT // 2),
        np.linspace(-128.0, 127.99609375, N_FEAT),           # rampa
        np.linspace(127.99609375, -128.0, N_FEAT),           # ters rampa
    ]
    # one-hot: each feature in turn at the ceiling, the rest zero
    for i in range(N_FEAT):
        v = np.zeros(N_FEAT); v[i] = 127.99609375; edge.append(v)
        v = np.zeros(N_FEAT); v[i] = -128.0;       edge.append(v)
    rows.extend(edge)

    # --- 2) Random block, deliberately mixed in scale ---
    remaining = max(0, n_rows - len(rows))
    if remaining:
        # 40% narrow range: samples ReLU and sign transitions densely
        # 40% mid range
        # 20% wide range: drives the accumulator and saturation paths
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

    # Snap to the Q8.8 grid. The host cast truncates, so using exact grid
    # values removes any ambiguity along CSV text -> float -> int16.
    q = np.trunc(a * 256.0)
    q = np.clip(q, -32768, 32767)
    return q / 256.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100000)
    ap.add_argument("--out", default="verify_stream.csv")
    args = ap.parse_args()

    a = build(args.rows)
    # %.6f suffices: every value is an exact multiple of 1/256, so nothing is lost
    np.savetxt(args.out, a, delimiter=",", fmt="%.6f")

    print(f"[ok] {a.shape[0]} satir x {a.shape[1]} oznitelik -> {args.out}")
    print(f"     deger araligi [{a.min():.4f}, {a.max():.4f}]  (Q8.8 siniri -128 .. +127.996)")
    print(f"     seed={SEED} -> ayni komut ayni dosyayi uretir")
    print()
    print("     Note: the host engine zero-pads every row to 64, so features 40-63 = 0.")


if __name__ == "__main__":
    main()
