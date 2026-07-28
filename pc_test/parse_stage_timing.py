#!/usr/bin/env python3
"""
Per-stage latency statistics for paper Table 2 / Table 10.

Input: the engine's execution log CSV produced with the ENABLE_STAGE_TIMING
firmware (21-byte UDP reply). Columns:
  Timestamp_us,Latency_us,Result,recv_ticks,parse_ticks,dma_ticks,pl_ticks,read_ticks

Ticks are Zynq-7000 Global Timer ticks (CPU_FREQ/2; Zedboard 667 MHz -> 333.33 MHz).
Override with --freq if your PS clock differs (see xparameters.h COUNTS_PER_SECOND,
printed once at boot as "TIMFREQ,<Hz>" on UART).

Usage:  python3 parse_stage_timing.py execution_log_linux.csv [--freq 333333333]
"""
import argparse, csv
import numpy as np

STAGES = [
    ("Ethernet packet reception (EMAC+lwIP)", "recv"),
    ("Packet parsing / feature prep",         "parse"),
    ("AXI-DMA transfer to PL (MM2S)",         "dma"),
    ("PL: AXI-Stream receive + MLP compute",  "pl"),
    ("Result readout (AXI-Lite, 3 regs)",     "read"),
    ("Sum of PS+PL stages",                   "sum"),
    ("Host end-to-end (Latency_us column)",   "e2e"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="extended execution log CSV")
    ap.add_argument("--freq", type=float, default=333333333.0,
                    help="Global Timer tick rate in Hz (default Zedboard 333.33 MHz)")
    args = ap.parse_args()

    ticks, e2e = [], []
    with open(args.log) as f:
        rd = csv.reader(f)
        header = next(rd)
        if len(header) < 8:
            raise SystemExit("log has no stage tick columns — was the firmware "
                             "built with ENABLE_STAGE_TIMING and the engine rebuilt?")
        for row in rd:
            if len(row) < 8 or row[3] == "" or row[1] == "TIMEOUT":
                continue
            try:
                ticks.append([int(x) for x in row[3:8]])
                e2e.append(float(row[1]))
            except ValueError:
                continue
    if not ticks:
        raise SystemExit("no rows with stage ticks found")

    t = np.array(ticks, dtype=np.float64) / args.freq * 1e6   # -> microseconds
    e2e = np.array(e2e)
    cols = [t[:, 0], t[:, 1], t[:, 2], t[:, 3], t[:, 4], t.sum(axis=1), e2e]

    print(f"packets: {len(t)}   tick rate: {args.freq/1e6:.3f} MHz\n")
    hdr = f"{'stage':42s} {'mean':>9s} {'p50':>9s} {'p99':>9s} {'min':>9s} {'max':>9s}"
    print(hdr); print("-" * len(hdr))
    for (name, _), c in zip(STAGES, cols):
        print(f"{name:42s} {c.mean():9.3f} {np.percentile(c,50):9.3f} "
              f"{np.percentile(c,99):9.3f} {c.min():9.3f} {c.max():9.3f}")

    print("\nAll values in microseconds.")
    print("Table 2:  #1=recv  #2=parse  #3=dma  #4=host end-to-end")
    print("Table 10: #9=recv  #10=parse  #11=dma  #12=pl  #13=read  #14=host end-to-end")
    print("Note: (e2e - sum) = wire/NIC/OS time on the PC side + UDP reply path.")

    out = np.column_stack(cols)
    np.savetxt("stage_timing_us.csv", out, delimiter=",", fmt="%.4f",
               header="recv_us,parse_us,dma_us,pl_us,read_us,sum_us,e2e_us", comments="")
    print("raw per-packet data written to stage_timing_us.csv")


if __name__ == "__main__":
    main()
