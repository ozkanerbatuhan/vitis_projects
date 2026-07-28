#!/usr/bin/env python3
"""
FPGA MLP cekirdeginin bit-exact dogrulanmasi.

Ne yapar:
  Dagitilan boru hattinin TAMAMINI yazilimda birebir modeller
    host cast   : hft_engine_linux.cpp  -> float -> int16 Q8.8
    agirlik     : mlp_weight_loader.h   -> float_to_q88 = (int)(w*256)  [trunc]
    PL          : mlp_engine.vhd        -> 40-bit acc, bias<<8, aritmetik >>8,
                                           saturate int16, ReLU (son katman haric)
    karar       : main.c argmax         -> varsayilan 0; 1/2 icin kesin '>'
  ve kaydedilen FPGA logu ile karsilastirir.

Bu bir DOGRULUK (accuracy) olcumu DEGILDIR. Modelin iyi olup olmadigindan
bagimsiz olarak, donanimin altin yazilim modeliyle ayni sonucu urettigini
gosterir. Basari kriteri: %100.

Kullanim:
  python3 verify_bitexact.py --stream verify_stream.csv \
                             --log    verify_log.csv \
                             --model  ../best_model_new.pth
"""
import argparse
import csv
import sys
import zipfile

import numpy as np

# Donanimin sabit yerlesimi (mlp_weight_loader.h / load_default_network)
SHAPES = [(64, 64), (32, 64), (16, 32), (3, 16)]
N_FLOATS = sum(o * i + o for o, i in SHAPES)          # 6819
NAME_TO_ID = {"SELL": 0, "HOLD": 1, "BUY": 2}         # main.c kodlamasi


# ───────────────────────── host cast ─────────────────────────
def host_cast(vals, saturating):
    """
    saturating=False : mevcut kod. static_cast<int16_t>(v*256.0f)
                       x86 cvttss2si -> int32, dusuk 16 bit (SESSIZ SARMALANMA)
    saturating=True  : yamali kod. lrintf + clamp
    """
    v32 = np.asarray(vals, dtype=np.float64).astype(np.float32) * np.float32(256)
    v = v32.astype(np.float64)
    if saturating:
        x = np.rint(v)
        return np.clip(x, -32768, 32767).astype(np.int64)
    ok = np.isfinite(v) & (v < 2147483648.0) & (v >= -2147483648.0)
    i32 = np.where(ok, np.trunc(v), -2147483648.0).astype(np.int64)
    return ((i32 & 0xFFFF) ^ 0x8000) - 0x8000


def parse_stream(path, n_rows, saturating):
    """Host motorunun tokenizer'ini birebir taklit eder (stof, sayisal olmayani atla)."""
    feats = np.zeros((n_rows, 64), dtype=np.int64)
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= n_rows:
                break
            vals = []
            for tok in line.rstrip("\r\n").split(","):
                try:
                    vals.append(float(tok))
                except ValueError:
                    pass          # True/False vb. -> stof firlatir -> atlanir
            if not vals:
                continue
            q = host_cast(vals, saturating)
            feats[i, :min(64, q.size)] = q[:64]
    return feats


# ───────────────────────── agirliklar ─────────────────────────
def _pad(layers):
    """Herhangi bir topolojiyi donanimin sabit 64-genis yerlesimine sifir doldurur."""
    Wq, Bq = [], []
    for (t_out, t_in), (W, b) in zip(SHAPES, layers):
        Wp = np.zeros((t_out, t_in), dtype=np.float32)
        bp = np.zeros(t_out, dtype=np.float32)
        r, c = min(W.shape[0], t_out), min(W.shape[1], t_in)
        Wp[:r, :c] = W[:r, :c]
        bp[:min(b.size, t_out)] = b[:t_out]
        # firmware float_to_q88: trunc (yuvarlama DEGIL)
        Wq.append(np.trunc(Wp * np.float32(256)).astype(np.int64))
        Bq.append(np.trunc(bp * np.float32(256)).astype(np.int64))
    return Wq, Bq


def load_model(path):
    if path.endswith(".bin"):
        flat = np.fromfile(path, dtype=np.float32)
        if flat.size != N_FLOATS:
            sys.exit(f"[hata] {path}: {flat.size} float, beklenen {N_FLOATS}")
        layers, o = [], 0
        for (n, i) in SHAPES:
            W = flat[o:o + n * i].reshape(n, i); o += n * i
            b = flat[o:o + n];                   o += n
            layers.append((W, b))
        return _pad(layers), "bin (zaten dolgulu)"

    z = zipfile.ZipFile(path)
    items = sorted((i for i in z.infolist() if "/data/" in i.filename),
                   key=lambda i: int(i.filename.split("/")[-1]))
    arrs = [np.frombuffer(z.read(i.filename), dtype="<f4") for i in items]
    layers, topo = [], []
    for k in range(0, 8, 2):
        W, b = arrs[k], arrs[k + 1]
        rows = b.size
        layers.append((W.reshape(rows, W.size // rows), b))
        topo.append(rows)
    return _pad(layers), "pth topoloji 40->" + "->".join(map(str, topo))


# ───────────────────────── PL emulasyonu ─────────────────────────
def forward_q88(x, Wq, Bq):
    """mlp_engine.vhd'nin bit-exact modeli."""
    a = x
    for li, ((n_out, n_in), W, B) in enumerate(zip(SHAPES, Wq, Bq)):
        acc = a[:, :n_in] @ W.T + (B << 8)      # 40-bit akumulator (int64'te rahat sigar)
        s = acc >> 8                            # VHDL shift_right -> aritmetik, floor
        s = np.clip(s, -32768, 32767)           # saturate()
        if li < len(SHAPES) - 1:
            s = np.maximum(s, 0)                # ReLU, son katman haric
        a = s
    return a


def argmax_fw(logits):
    """main.c: varsayilan SELL(0); HOLD/BUY icin kesin buyukluk."""
    o0, o1, o2 = logits[:, 0], logits[:, 1], logits[:, 2]
    d = np.zeros(len(logits), dtype=np.int64)
    d[(o1 > o0) & (o1 > o2)] = 1
    d[(d == 0) & (o2 > o0) & (o2 > o1)] = 2
    return d


# ───────────────────────── log okuma ─────────────────────────
def read_log(path):
    dec, logits, n_to, n_hdr = [], [], 0, 0
    with open(path) as f:
        rd = csv.reader(f)
        header = next(rd)
        has_logits = "out0" in header
        for row in rd:
            if not row:
                continue
            if row[0] == "Timestamp_us":        # dosyaya tekrar header yazilmis
                n_hdr += 1
                continue
            r = row[2] if len(row) > 2 else "TIMEOUT"
            if r not in NAME_TO_ID:
                n_to += 1
                dec.append(-1); logits.append((0, 0, 0))
                continue
            dec.append(NAME_TO_ID[r])
            if has_logits and len(row) >= 11:
                try:
                    logits.append(tuple(int(row[8 + k]) for k in range(3)))
                except ValueError:
                    logits.append((0, 0, 0))
            else:
                logits.append((0, 0, 0))
    return (np.array(dec, dtype=np.int64),
            np.array(logits, dtype=np.int64),
            has_logits, n_to, n_hdr)


# ───────────────────────── ana akis ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--model", required=True, help=".pth veya .bin")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--legacy-cast", action="store_true",
                    help="host cast'e doygunluk yamasi UYGULANMADIYSA kullan")
    args = ap.parse_args()

    fpga, fpga_logits, has_logits, n_to, n_hdr = read_log(args.log)
    n = len(fpga) if not args.max_rows else min(args.max_rows, len(fpga))
    fpga, fpga_logits = fpga[:n], fpga_logits[:n]

    print("─" * 62)
    print(f"log satiri        : {n}")
    print(f"timeout/bilinmeyen: {n_to}")
    if n_hdr:
        print(f"  !! log icinde {n_hdr} ek header satiri -> dosya APPEND edilmis.")
        print("     Kosumdan once eski logu silin, yoksa hizalama bozulur.")
    if n_to:
        print("  !! timeout var; o satirlar karsilastirma disi birakiliyor.")

    (Wq, Bq), desc = load_model(args.model)
    print(f"model             : {args.model}  [{desc}]")
    print(f"host cast         : {'SARMALANAN (yamasiz)' if args.legacy_cast else 'DOYGUN (yamali)'}")

    x = parse_stream(args.stream, n, saturating=not args.legacy_cast)
    print(f"akis              : {args.stream}  oznitelik araligi [{x.min()}, {x.max()}]")

    logits = forward_q88(x, Wq, Bq)
    pred = argmax_fw(logits)

    ok = fpga >= 0
    n_ok = int(ok.sum())
    agree = int((pred[ok] == fpga[ok]).sum())
    rate = 100.0 * agree / n_ok if n_ok else 0.0

    print("─" * 62)
    print(f"KARAR eslesmesi   : {rate:.4f}%   ({agree}/{n_ok})")

    emu_d = [int((pred[ok] == k).sum()) for k in range(3)]
    fpg_d = [int((fpga[ok] == k).sum()) for k in range(3)]
    print(f"  emulator SELL/HOLD/BUY : {emu_d}")
    print(f"  FPGA     SELL/HOLD/BUY : {fpg_d}")

    # Dejenerelik uyarisi: tek sinif baskinsa karar eslesmesi anlamsizdir
    top = max(fpg_d) / max(1, n_ok)
    if top > 0.80:
        print(f"  !! FPGA cikisinin %{100*top:.1f}'i tek sinif. Karar eslesmesi bu")
        print("     durumda zayif kanittir -- logit seviyesinde dogrulama sart.")

    if has_logits:
        m = np.all(fpga_logits[ok] == logits[ok], axis=1)
        lr = 100.0 * m.sum() / n_ok if n_ok else 0.0
        print(f"LOGIT eslesmesi   : {lr:.4f}%   ({int(m.sum())}/{n_ok})   "
              f"[{n_ok*3} adet int16 karsilastirmasi]")
        if lr < 100.0:
            bad = np.where(ok)[0][~m][:5]
            for i in bad:
                print(f"   satir {i}: FPGA {fpga_logits[i].tolist()}  emu {logits[i].tolist()}")
    else:
        print("LOGIT eslesmesi   : yok (firmware yamasi uygulanmamis)")

    print("─" * 62)
    good = rate == 100.0 and (not has_logits or lr == 100.0)
    print("SONUC: BIT-EXACT DOGRULANDI" if good else "SONUC: UYUSMAZLIK VAR")
    if not good:
        mism = np.where(ok & (pred != fpga))[0][:10]
        print(f"ilk uyusmayan satirlar: {mism.tolist()}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
