#!/usr/bin/env python3
"""
Distribution of the PL cycle counter: the evidence behind the determinism
claim.

After every inference the firmware reads the cycle counter from AXI-Lite
offset 0x10 and appends it to the reply; the host writes it into the
'cycles' column of the log. This script reports that column's distribution.

A single-valued distribution (min = max, std = 0) over 10^5 inferences is
what turns the claim from an illustration into a measurement.

Usage:  python3 analyze_jitter.py ../linux/log_jitter.csv
"""
import csv
import sys
from collections import Counter


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: analyze_jitter.py <log.csv>")
    path = sys.argv[1]

    vals, n_rows, n_missing = [], 0, 0
    with open(path) as f:
        rd = csv.reader(f)
        header = next(rd)
        try:
            col = header.index("cycles")
        except ValueError:
            sys.exit("ERROR: the log has no 'cycles' column.\n"
                     "  The firmware may not be returning the 29-byte reply; "
                     "is BOOT.bin current?")
        for row in rd:
            if not row or row[0] == "Timestamp_us":
                continue
            n_rows += 1
            if len(row) <= col or row[col].strip() == "":
                n_missing += 1
                continue
            try:
                vals.append(int(row[col]))
            except ValueError:
                n_missing += 1

    if not vals:
        sys.exit("ERROR: no cycle values could be read.")

    c = Counter(vals)
    lo, hi = min(vals), max(vals)
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)

    print("─" * 58)
    print("log rows          : %d" % n_rows)
    print("cycle values      : %d" % len(vals))
    if n_missing:
        print("  !! %d rows have no value (no 29-byte reply)" % n_missing)
    print("─" * 58)
    print("min / max         : %d / %d" % (lo, hi))
    print("mean              : %.6f" % mean)
    print("standard deviation: %.6f" % (var ** 0.5))
    print("distinct values   : %d" % len(c))
    print()
    for v, k in sorted(c.items()):
        print("  %5d cycles : %8d  (%6.3f%%)  = %.1f ns at 125 MHz"
              % (v, k, 100.0 * k / len(vals), v * 8.0))
    print("─" * 58)

    if lo == hi:
        print("RESULT: NO JITTER. The core takes exactly %d cycles every time." % lo)
        print("       %.0f ns at 125 MHz. Analytic model: 96 cycles / 768 ns." % (lo * 8.0))
        if lo != 96:
            print("       Note: the analytic model predicts 96; the counter excludes the\n       cycle in which start is sampled, so %d + 1 = 96." % lo)
    else:
        print("RESULT: JITTER PRESENT (%d to %d cycles)." % (lo, hi))
        print("       This is unexpected: the core should be deterministic.")
        print("       Check the AXI-Lite read timing first: the counter is")
        print("       latched at done, so the read must happen after done.")


if __name__ == "__main__":
    main()
