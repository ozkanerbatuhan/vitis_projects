# Firmware, Host Tooling and Verification (Zynq HFT-MLP)

Software side of *An Ethernet-Enabled Customizable Neural Inference Framework on
Low-Cost FPGA SoC for High-Frequency Trading*.

This repository holds the bare-metal firmware that runs on the Zynq PS, the host
engine and GUI that drive the board over Ethernet, and the scripts that produce
the verification and measurement results reported in the paper. The RTL is in a
separate repository (see [Companion repository](#companion-repository)).

## How it fits together

```
host (Linux or Windows)                 ZedBoard
┌──────────────────────┐  UDP 7000  ┌──────────────────────────────────┐
│ hft_frontend.py  GUI │◄──────────►│ PS: bare-metal lwIP, Cortex-A9   │
│ hft_engine_linux.cpp │            │   parse -> AXI-DMA -> AXI-Stream │
│   float -> Q8.8      │            │              ▼                   │
│   CSV streaming      │            │ PL: MLP core, Q8.8, 768 ns       │
│   logging            │            │              ▼                   │
└──────────────────────┘            │   AXI-Lite readout -> reply      │
                                    └──────────────────────────────────┘
```

A request is a UDP round trip. The reply is 29 bytes: the decision, five 32-bit
Global Timer stamps for the per-stage latency breakdown, the three raw 16-bit
logits, and the PL cycle count for that inference. The logits are what make
bit-exact verification possible; the cycle count is what makes the determinism
claim measurable.

Model upload is a separate command on the same socket, so a different network is
deployed at run time with no synthesis step.

## Layout

```
lwip_echo_server/src/
    main.c                  UDP server, DMA hand-off, per-stage timestamps,
                            ARM software baseline
    mlp_driver.h            AXI-Lite register map and DMA helper
    mlp_weight_loader.h     float to Q8.8 conversion and weight upload
    platform*.c/h           Zynq platform bring-up
pc_test/
    hft_frontend.py         GUI: model upload, streaming, live status
    linux/hft_engine_linux.cpp   host engine (Linux)
    win/                    host engine (Windows)
    data_prep_binance.py    feature preparation (see the warning below)
    quantization_analysis.py     float against Q8.8 comparison
    parse_stage_timing.py   per-stage latency breakdown from a log
    analyze_linux_log.py    end-to-end latency statistics
    verify/                 bit-exact verification and determinism analysis
    _archive_pre_verify/    the measurement logs behind the paper's tables
mlp_system_wrapper.xsa      hardware handoff from the RTL repository
PAPER_MEASUREMENTS.md       which run produced which table
verify_boot.bif             bootgen description
```

Generated content is excluded from version control. In particular
`mlp_platform/` is the board-support package Vitis generates from the `.xsa`,
roughly 5,700 files of lwIP and Xilinx driver source that belong to the tool.
See `.gitignore`.

## Building

Vitis 2025.2.

1. **Platform.** Create a platform component from `mlp_system_wrapper.xsa`
   (Vitis, Create Platform Component). If the `.xsa` has been regenerated,
   use Update Hardware Specification instead and rebuild.
2. **Application.** Clean-build `lwip_echo_server`.
3. **Boot image.** `bootgen -image verify_boot.bif -arch zynq -o BOOT.bin -w on`

   Check that the resulting `BOOT.bin` is newer than the `.elf`. A stale boot
   image is the most common reason a rebuilt change appears not to take effect.
   For UART-only measurements, Run As -> Launch Hardware downloads the fresh
   `.elf` over JTAG and skips `bootgen` entirely.

4. **Host engine.**

   ```
   cd pc_test/linux
   g++ -O2 -o hft_engine_linux hft_engine_linux.cpp -lpthread
   ```

## Verification

`pc_test/verify/` reproduces the verification result in the paper. Full
instructions are in `verify/RUNBOOK.md`; the determinism and baseline runs are in
`verify/RUNBOOK_2.md`.

```
# generate the stimulus (deterministic, fixed seed)
python3 verify/make_verify_stream.py --rows 100000 --out verify/verify_stream.csv

# stream it from the GUI, then compare against the golden model
python3 verify/verify_bitexact.py --stream verify/verify_stream.csv \
    --log ../linux/log_run.csv \
    --model verify/models/mlp_40_64_32_16_3_bfdb6941.pth
```

`verify_bitexact.py` reimplements the whole deployed pipeline independently: the
host cast, the truncating weight conversion, the 40-bit accumulate, the
arithmetic right shift, saturation, ReLU and the argmax rule. It is not an
accuracy measurement. Across four topologies the hardware matched it on 400,000
inferences and all 1,200,000 raw output values.

The stimulus is synthetic on purpose. Trained features are clipped to a narrow
band, so replaying market data never drives the accumulator towards saturation
and cannot distinguish a correct datapath from one whose clamping logic is
broken.

**Determinism.** `verify/analyze_jitter.py` reports the distribution of the
`cycles` column. Over 100,000 inferences it is single-valued with zero standard
deviation.

**Software baseline.** The firmware prints an ARM Cortex-A9 baseline to the UART
at boot, with no model upload or host tooling required:

```
ARM baseline: starting measurement (1000 iterations)
ARM baseline dist: min=... p50=... p99=... max=... ns (n=1000)
ARM baseline [synthetic]: 1000 inferences, ... ns each
```

The same network, the same Q8.8 arithmetic, bare-metal, single core, warm
caches. The two functions carry an `optimize("O3")` attribute because Vitis
compiles the application at `-O0` by default and an unoptimized baseline would
make the comparison unfair.

## Known limitation: feature layout mismatch

`data_prep_binance.py` flattens raw prices and quantities. That is **not** the
layout the shipped networks were trained on. Training builds each 40-element
vector as 20 slots of relative price changes scaled by 1000, 10 quantities
divided by the window mean, and 10 taker-side indicators, everything clipped to
`[-5, 5]`.

Raw BTCUSDT prices are about three orders of magnitude outside the Q8.8 range,
so streaming them produces meaningless predictions.

No measurement in the paper is affected. Latency and determinism do not depend
on feature values, and the accuracy and bit-exactness figures were produced with
the training-side features. The script is kept for latency and throughput runs,
for which any well-scaled input will do. Anyone wanting real predictions should
reimplement the training-side layout there; the file carries the same warning at
the top.

## Register map

| Offset | Access | Meaning |
|---|---|---|
| `0x00` | W | bit 0 = start |
| `0x04` | R | bit 0 = done, bit 1 = busy |
| `0x0C` | R | decision, bits [1:0] |
| `0x10` | R | cycle count of the last inference |
| `0x20000 +` | W | weights and biases, see `mlp_weight_loader.h` |

Weight address: `0x20000 + bram_idx * 512 + word_addr * 4`, with
`bram_idx = neuron_slot * 64 + input_index` and biases at `bram_idx` 192 to 194.

## Measurement logs

`pc_test/_archive_pre_verify/` holds the raw logs behind the latency tables, gzip
compressed. `PAPER_MEASUREMENTS.md` says which run produced which table. Logs
that are exact duplicates, that `parse_stage_timing.py` reproduces, or that came
from the superseded bitstream are not tracked.

## Companion repository

RTL, block design, testbench and implementation reports:
<https://github.com/ozkanerbatuhan/hft>

## Citing

Citation details will be added once the paper is published. Until then, please
reference this repository directly.
