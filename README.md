# Zynq HFT-MLP Inference Ethernet Server

This project implements a High-Frequency Trading (HFT) Multi-Layer Perceptron (MLP) inference server running on a Xilinx Zynq SoC (specifically targeted for the ZedBoard). The project focuses on achieving ultra-low, sub-microsecond inference latencies by coupling the ARM Processing System (PS) with a custom neural network accelerator running in the Programmable Logic (PL) via AXI-DMA.

The SoC receives financial feature data over Ethernet using the `lwIP` networking stack, performs the classification (SELL, HOLD, or BUY) on the FPGA PL, and sends the verdict back to the PC via UDP.

## Hardware & Architecture

- **Processing System (PS):** Runs a bare-metal `lwIP` UDP server written in C. It continuously listens for incoming UDP packets on port `7000`.
- **Programmable Logic (PL):** Implements a low-latency MLP (Multi-Layer Perceptron).
- **Communication:** The PC sends UDP packets to the PS. The PS pushes the incoming feature array over an AXI-Stream interface to the hardware accelerator via **AXI-DMA**. Upon completion, the PS retrieves the class mapping via an AXI-Lite register read or directly and transmits the resulting 1-byte class back to the PC.

## Protocol and Payload

1. **Request:** The PC sends a single UDP packet containing exactly 80 bytes. This represents 40 input features, where each feature is a 16-bit (`int16_t`) fixed-point Q8.8 value.
2. **Response:** The board responds with a single UDP packet containing 1 byte, representing the classification result.
   - `0`: SELL
   - `1`: HOLD
   - `2`: BUY

## Project Structure

- **`mlp_platform/`**: The Vitis platform project containing the hardware definition (`.xsa`), board support packages, and system wrappers from the Vivado block design.
- **`lwip_echo_server/`**: The Vitis C application that runs on the ARM Cortex-A9 cores. This handles the Ethernet communication via lwIP and manages the DMA transfers to the MLP hardware using drivers (`mlp_driver.h`).
- **`pc_test/`**: Contains PC-side testing and benchmarking tools to measure the roundtrip latencies over Ethernet.

## PC Tools & Benchmarking (`pc_test`)

The `pc_test/` directory contains tools to measure network and inference latencies.

### 1. High-Performance C Benchmark (`test_mlp.c`)
A fast C client built with `Winsock2` that pushes data to the ZedBoard and receives responses. It can run a million packets sequentially to accurately map network jitter and benchmark end-to-end latency.
It produces a CSV file (`latencies.csv`) with the latency (in microseconds) of every single packet.
**To compile:** `gcc test_mlp.c -o test_mlp.exe -lws2_32`

### 2. Python Client (`test_mlp.py`)
A simpler, Python-based test tool used to quickly test single queries or run smaller-scale benchmarks (e.g., 1000 packets) without needing GCC.

### 3. Latency Visualizer (`plot_latencies.py`)
A Matplotlib-based script tailored to process the 1-million-row `latencies.csv` file produced by the C client.
It calculates statistical percentiles (Med, 99th, 99.9th, 99.99th), filters out OS-level network spikes/jitter, and produces two graphs:
- A histogram showing the distribution of typical fast responses.
- A downsampled time-series chart showing latency variation over the course of the benchmark.

## Setup Instructions
1. Upload the bitstream and the `lwip_echo_server` ELF to the ZedBoard via Xilinx Vitis (or utilize `run_on_hw.tcl` / `run_echo_test.tcl`).
2. Make sure your PC is connected to the ZedBoard Ethernet port and has an IP assigned in the `192.168.1.x` subnet.
3. Run `test_mlp.exe` or `python test_mlp.py` on your PC to benchmark latency boundaries.
