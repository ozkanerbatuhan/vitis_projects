#!/usr/bin/env python3
"""
Table 4 (Quantization evaluation) — offline, bit-exact analysis.

Reproduces the ENTIRE deployed pipeline in software, bit-for-bit:
  * PC side   : hft_engine_linux.cpp  ->  static_cast<int16_t>(stof(tok) * 256.0f)
                (x86 cvttss2si semantics: out-of-int32-range -> INT32_MIN, then low 16 bits)
  * FW side   : mlp_weight_loader.h   ->  float_to_q88 = (int)(w * 256.0f)  (trunc toward 0)
  * PL side   : mlp_engine.vhd        ->  40-bit accumulate, bias<<8, arithmetic >>8,
                saturate to int16, ReLU except last layer
  * Decision  : main.c argmax rule    ->  default SELL(0); HOLD/BUY need strict '>'

Outputs (fills Table 4 TBD cells):
  1. Output match rate  : Python Q8.8 emulator argmax  vs  FPGA argmax (execution log replay)
  2. Max absolute error : |float32 logits - Q8.8 logits/256| on the output layer
  3. Class change ratio : float32 argmax != Q8.8 argmax
  4. Q8.8 vs float agreement / per-class F1 (float model as reference)

Usage:  python3 quantization_analysis.py [--stream temp_stream_converted.csv]
                                         [--log linux/execution_log_linux.csv]
                                         [--weights temp_weights.bin]
                                         [--max-rows 0]        # 0 = as many as log rows
"""
import argparse, csv, sys
import numpy as np

# FPGA fixed architecture (matches Vitis firmware / VHDL)
SHAPES = [(64, 64), (32, 64), (16, 32), (3, 16)]
RESULT_NAMES = {0: "SELL", 1: "HOLD", 2: "BUY"}   # firmware class IDs (main.c)
# NOTE: engines built BEFORE 2026-07-12 decoded the reply as 0->HOLD, 1->BUY,
# 2->SELL (mismatch with firmware). Old logs (incl. execution_log_linux.csv) are
# therefore permuted -> use the inverted mapping below (default). For logs
# produced with the FIXED engine, pass --fixed-log.
NAME_TO_ID = {"HOLD": 0, "BUY": 1, "SELL": 2}          # legacy (buggy) logs
NAME_TO_ID_FIXED = {"SELL": 0, "HOLD": 1, "BUY": 2}    # logs after engine fix


def load_weights(path):
    flat = np.fromfile(path, dtype=np.float32)
    assert flat.size == 6819, f"expected 6819 floats, got {flat.size}"
    Wf, Bf, o = [], [], 0
    for (n_out, n_in) in SHAPES:
        Wf.append(flat[o:o + n_out * n_in].reshape(n_out, n_in)); o += n_out * n_in
        Bf.append(flat[o:o + n_out]); o += n_out
    # firmware float_to_q88: (int)(w*256.0f) — truncation toward zero
    Wq = [np.trunc(w.astype(np.float32) * np.float32(256)).astype(np.int64) for w in Wf]
    Bq = [np.trunc(b.astype(np.float32) * np.float32(256)).astype(np.int64) for b in Bf]
    return Wf, Bf, Wq, Bq


def cpp_float_to_int16(vals_f64):
    """Emulate x86 static_cast<int16_t>(float32 v): cvttss2si -> int32, keep low 16 bits."""
    v = vals_f64.astype(np.float32) * np.float32(256)
    v64 = v.astype(np.float64)
    in_range = np.isfinite(v64) & (v64 < 2147483648.0) & (v64 >= -2147483648.0)
    i32 = np.where(in_range, np.trunc(v64), -2147483648.0).astype(np.int64)
    return ((i32 & 0xFFFF) ^ 0x8000) - 0x8000  # low 16 bits, signed


def parse_stream_rows(path, n_rows):
    """Replicate the C++ tokenizer: stof each comma token, skip non-numeric (True/False)."""
    feats = np.zeros((n_rows, 64), dtype=np.int64)
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= n_rows:
                break
            vals = []
            for tok in line.rstrip("\r\n").split(","):
                try:
                    vals.append(float(tok))  # stof; True/False -> throws -> skipped
                except ValueError:
                    pass
            q = cpp_float_to_int16(np.array(vals, dtype=np.float64))
            feats[i, :min(64, q.size)] = q[:64]
    return feats


def forward_q88(x_i16, Wq, Bq):
    """Bit-exact PL emulation. x: (N,64) int64. Returns final int16 logits (N,3)."""
    a = x_i16
    for li, ((n_out, n_in), W, B) in enumerate(zip(SHAPES, Wq, Bq)):
        acc = a[:, :n_in] @ W.T + (B << 8)          # 40-bit acc fits easily in int64
        s = acc >> 8                                # VHDL shift_right (arithmetic, floor)
        s = np.clip(s, -32768, 32767)               # saturate()
        if li < len(SHAPES) - 1:
            s = np.maximum(s, 0)                    # ReLU (except last layer)
        a = s
    return a


def forward_float(x_f, Wf, Bf):
    a = x_f
    for li, ((n_out, n_in), W, B) in enumerate(zip(SHAPES, Wf, Bf)):
        z = a[:, :n_in] @ W.T.astype(np.float64) + B.astype(np.float64)
        a = np.maximum(z, 0) if li < len(SHAPES) - 1 else z
    return a


def fw_argmax(logits):
    """main.c rule: default 0; 1 if out1 strictly greatest; else 2 if out2 strictly greatest."""
    o0, o1, o2 = logits[:, 0], logits[:, 1], logits[:, 2]
    d = np.zeros(len(logits), dtype=np.int64)
    d[(o1 > o0) & (o1 > o2)] = 1
    d[(d == 0) & (o2 > o0) & (o2 > o1)] = 2
    return d


def f1_per_class(y_ref, y_hat, k):
    tp = np.sum((y_hat == k) & (y_ref == k))
    fp = np.sum((y_hat == k) & (y_ref != k))
    fn = np.sum((y_hat != k) & (y_ref == k))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", default="temp_stream_converted.csv")
    ap.add_argument("--log", default="linux/execution_log_linux.csv")
    ap.add_argument("--weights", default="temp_weights.bin")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--fixed-log", action="store_true",
                    help="log was produced by the FIXED engine (correct 0=SELL,1=HOLD,2=BUY names)")
    args = ap.parse_args()
    name_map = NAME_TO_ID_FIXED if args.fixed_log else NAME_TO_ID

    # FPGA results from the execution log (in stream order)
    fpga = []
    with open(args.log) as f:
        rd = csv.reader(f); next(rd)
        for row in rd:
            fpga.append(name_map.get(row[2], -1))  # TIMEOUT/UNKNOWN -> -1
    fpga = np.array(fpga, dtype=np.int64)
    n = len(fpga) if not args.max_rows else min(args.max_rows, len(fpga))
    fpga = fpga[:n]
    print(f"[i] log rows: {n}  (timeouts/unknown: {(fpga < 0).sum()})")

    Wf, Bf, Wq, Bq = load_weights(args.weights)
    x_q = parse_stream_rows(args.stream, n)
    print(f"[i] stream rows parsed: {x_q.shape[0]}, int16 feature range "
          f"[{x_q.min()}, {x_q.max()}]")

    logits_q = forward_q88(x_q, Wq, Bq)
    pred_q = fw_argmax(logits_q)

    # Float reference: dequantized inputs (what the PL actually received), float weights
    logits_f = forward_float(x_q.astype(np.float64) / 256.0, Wf, Bf)
    pred_f = fw_argmax(logits_f)

    ok = fpga >= 0
    match = np.mean(pred_q[ok] == fpga[ok])
    max_abs_err = np.max(np.abs(logits_f - logits_q / 256.0))
    mean_abs_err = np.mean(np.abs(logits_f - logits_q / 256.0))
    class_change = np.mean(pred_f != pred_q)
    agree = 1.0 - class_change
    f1s = [f1_per_class(pred_f, pred_q, k) for k in (0, 1, 2)]

    print("\n──────── Table 4 results ────────")
    print(f"Output match rate  (Python Q8.8 vs FPGA argmax) : {match*100:.4f}%  "
          f"({int((pred_q[ok]==fpga[ok]).sum())}/{int(ok.sum())})")
    print(f"Max absolute error (float vs Q8.8, output layer): {max_abs_err:.6f}  "
          f"(mean {mean_abs_err:.6f})")
    print(f"Class change ratio (float argmax vs Q8.8 argmax): {class_change*100:.4f}%")
    print(f"Q8.8 agreement with float reference             : {agree*100:.4f}%")
    print(f"Per-class F1 (float ref)  SELL/HOLD/BUY         : "
          f"{f1s[0]:.4f} / {f1s[1]:.4f} / {f1s[2]:.4f}")
    print(f"Macro F1                                        : {np.mean(f1s):.4f}")

    dist_q = [int((pred_q == k).sum()) for k in range(3)]
    dist_g = [int((fpga == k).sum()) for k in range(3)]
    print(f"\nClass distribution  emulator SELL/HOLD/BUY : {dist_q}")
    print(f"Class distribution  FPGA log SELL/HOLD/BUY : {dist_g}")
    if match < 0.999:
        mism = np.where((fpga >= 0) & (pred_q != fpga))[0][:10]
        print(f"first mismatched rows: {mism.tolist()}")


if __name__ == "__main__":
    main()
