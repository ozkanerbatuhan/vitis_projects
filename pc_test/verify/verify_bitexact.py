#!/usr/bin/env python3
"""
Bit-exact verification of the FPGA MLP core.

What it does:
  Reproduces the whole deployed pipeline in software
    host cast : hft_engine_linux.cpp  -> float to int16 Q8.8
    weights   : mlp_weight_loader.h   -> float_to_q88 = (int)(w*256), truncating
    PL        : mlp_engine.vhd        -> 40-bit accumulate, bias<<8, arithmetic
                                         >>8, saturate to int16, ReLU on all
                                         but the last layer
    decision  : main.c argmax         -> class 0 by default, strict '>' for 1/2
  and compares it against the recorded FPGA log.

This is NOT an accuracy measurement. Independently of whether the network is
any good, it shows that the hardware produces the same numbers as the golden
software model. The pass criterion is 100 percent.

Usage:
  python3 verify_bitexact.py --stream verify_stream.csv \
                             --log    verify_log.csv \
                             --model  ../best_model_new.pth
"""
import argparse
import csv
import sys
import zipfile

import numpy as np

# The hardware's fixed layout (mlp_weight_loader.h / load_default_network)
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
    """Reproduce the host engine's tokenizer exactly (stof, skip non-numeric)."""
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


# ───────────────────────── weights ─────────────────────────
def _pad(layers):
    """Zero-pad any topology into the hardware's fixed 64-wide layout."""
    Wq, Bq = [], []
    for (t_out, t_in), (W, b) in zip(SHAPES, layers):
        Wp = np.zeros((t_out, t_in), dtype=np.float32)
        bp = np.zeros(t_out, dtype=np.float32)
        r, c = min(W.shape[0], t_out), min(W.shape[1], t_in)
        Wp[:r, :c] = W[:r, :c]
        bp[:min(b.size, t_out)] = b[:t_out]
        # firmware float_to_q88 truncates; it does NOT round
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
    """Bit-exact model of mlp_engine.vhd."""
    a = x
    for li, ((n_out, n_in), W, B) in enumerate(zip(SHAPES, Wq, Bq)):
        acc = a[:, :n_in] @ W.T + (B << 8)      # 40-bit akumulator (int64'te rahat sigar)
        s = acc >> 8                            # VHDL shift_right -> aritmetik, floor
        s = np.clip(s, -32768, 32767)           # saturate()
        if li < len(SHAPES) - 1:
            s = np.maximum(s, 0)                # ReLU on all but the last layer
        a = s
    return a


def argmax_fw(logits):
    """Mirrors main.c: class 0 by default, strict comparison for the others."""
    o0, o1, o2 = logits[:, 0], logits[:, 1], logits[:, 2]
    d = np.zeros(len(logits), dtype=np.int64)
    d[(o1 > o0) & (o1 > o2)] = 1
    d[(d == 0) & (o2 > o0) & (o2 > o1)] = 2
    return d


# ───────────────────────── log parsing ─────────────────────────
def read_log(path):
    dec, logits, n_to, n_hdr = [], [], 0, 0
    with open(path) as f:
        rd = csv.reader(f)
        header = next(rd)
        # Detect the presence of logits from the DATA ROW width, not from the
        # header: the firmware writes logits, but a log whose header was
        # produced by an older engine build may be missing the column names.
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
            if len(row) >= 11:
                has_logits = True          # veri satirindan tespit
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


# ───────────────────────── main ─────────────────────────
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
    print(f"log rows          : {n}")
    print(f"timeout / unknown : {n_to}")
    if n_hdr:
        print(f"  !! {n_hdr} extra header rows in the log: the file was APPENDED to.")
        print("     Delete the old log before a run, otherwise alignment breaks.")
    if n_to:
        print("  !! timeouts present; those rows are excluded from the comparison.")

    (Wq, Bq), desc = load_model(args.model)
    print(f"model             : {args.model}  [{desc}]")
    print(f"host cast         : {'WRAPPING (legacy)' if args.legacy_cast else 'SATURATING'}")

    x = parse_stream(args.stream, n, saturating=not args.legacy_cast)
    print(f"stream            : {args.stream}  feature range [{x.min()}, {x.max()}]")

    logits = forward_q88(x, Wq, Bq)
    pred = argmax_fw(logits)

    ok = fpga >= 0
    n_ok = int(ok.sum())
    agree = int((pred[ok] == fpga[ok]).sum())
    rate = 100.0 * agree / n_ok if n_ok else 0.0

    print("─" * 62)
    print(f"DECISION match    : {rate:.4f}%   ({agree}/{n_ok})")

    emu_d = [int((pred[ok] == k).sum()) for k in range(3)]
    fpg_d = [int((fpga[ok] == k).sum()) for k in range(3)]
    print(f"  emulator per class : {emu_d}")
    print(f"  FPGA     per class : {fpg_d}")

    # Degeneracy warning: if one class dominates, decision agreement is weak
    top = max(fpg_d) / max(1, n_ok)
    if top > 0.80:
        print(f"  !! {100*top:.1f}% of FPGA outputs are one class. Decision agreement is")
        print("     weak evidence here; logit-level verification is required.")

    if has_logits:
        m = np.all(fpga_logits[ok] == logits[ok], axis=1)
        lr = 100.0 * m.sum() / n_ok if n_ok else 0.0
        print(f"LOGIT match       : {lr:.4f}%   ({int(m.sum())}/{n_ok})   "
              f"[{n_ok*3} adet int16 karsilastirmasi]")
        if lr < 100.0:
            bad = np.where(ok)[0][~m][:5]
            for i in bad:
                print(f"   row {i}: FPGA {fpga_logits[i].tolist()}  emu {logits[i].tolist()}")
    else:
        print("LOGIT match       : unavailable (firmware does not return logits)")

    print("─" * 62)
    good = rate == 100.0 and (not has_logits or lr == 100.0)
    print("RESULT: BIT-EXACT VERIFIED" if good else "RESULT: MISMATCH")
    if not good:
        mism = np.where(ok & (pred != fpga))[0][:10]
        print(f"first mismatching rows: {mism.tolist()}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
