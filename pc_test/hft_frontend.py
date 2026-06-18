import os
import threading
import socket
import time
import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox
import struct

# Drag and Drop Support
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
    class TkinterDnDApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
except ImportError:
    HAS_DND = False
    class TkinterDnDApp(ctk.CTk):
        pass

# Set theme and appearance
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# FPGA fixed architecture (must match the Vitis firmware EXACTLY).
# Firmware pointer layout:
#   W1=64x64, B1=64 | W2=32x64, B2=32 | W3=16x32, B3=16 | W4=3x16, B4=3
# Total = 6819 float32 values, no header. Input is padded to 64.
FPGA_LAYER_SHAPES = [(64, 64), (32, 64), (16, 32), (3, 16)]  # (out, in) per layer
FPGA_BIAS_SIZES = [64, 32, 16, 3]
FPGA_NUM_LAYERS = len(FPGA_LAYER_SHAPES)
FPGA_MODEL_FLOATS = sum(o * i for (o, i) in FPGA_LAYER_SHAPES) + sum(FPGA_BIAS_SIZES)  # 6819

class HFTFrontendApp(TkinterDnDApp):
    def __init__(self):
        super().__init__()

        self.title("FPGA HFT Accelerator - Advanced Control Panel")
        self.geometry("1100x650")
        self.minsize(900, 600)

        # Variables
        self.model_filepath = None
        self.csv_filepath = None
        self.is_connected = False
        self.is_streaming = False
        self.sock = None

        self.packet_count = 0
        self.last_ui_update = time.time()

        self.build_ui()
        self.log_message("SYSTEM", "Interface started. Connecting to C++ engine...")
        self.connect_to_engine()

    def build_ui(self):
        # Grid Configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # LEFT PANEL (Controls)
        # ==========================================
        self.frame_left = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.frame_left.grid(row=0, column=0, sticky="nsew")
        self.frame_left.grid_rowconfigure(6, weight=1)

        lbl_title = ctk.CTkLabel(self.frame_left, text="HFT CONTROL", font=ctk.CTkFont(size=24, weight="bold"))
        lbl_title.grid(row=0, column=0, padx=20, pady=(20, 30))

        # --- Connection Status ---
        self.frame_conn = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        self.frame_conn.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.lbl_conn_indicator = ctk.CTkLabel(self.frame_conn, text="●", text_color="red", font=ctk.CTkFont(size=20))
        self.lbl_conn_indicator.pack(side="left")
        self.lbl_conn_text = ctk.CTkLabel(self.frame_conn, text="Waiting for connection", font=ctk.CTkFont(size=14))
        self.lbl_conn_text.pack(side="left", padx=10)

        self.btn_reconnect = ctk.CTkButton(self.frame_left, text="Reconnect", command=self.connect_to_engine, fg_color="gray", hover_color="darkgray")
        self.btn_reconnect.grid(row=2, column=0, padx=20, pady=10)

        # --- Model Setup ---
        lbl_model = ctk.CTkLabel(self.frame_left, text="Model Loading", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_model.grid(row=3, column=0, padx=20, pady=(30, 5), sticky="w")

        self.btn_select_model = ctk.CTkButton(self.frame_left, text="Select Model (.bin)", command=self.select_model_file)
        self.btn_select_model.grid(row=4, column=0, padx=20, pady=5)

        self.btn_send_model = ctk.CTkButton(self.frame_left, text="Send Model", state="disabled", fg_color="#b8860b", hover_color="#8b6508", command=self.send_model)
        self.btn_send_model.grid(row=5, column=0, padx=20, pady=5)

        # --- Spacer ---

        # --- Stream Setup ---
        lbl_stream = ctk.CTkLabel(self.frame_left, text="Data Streaming", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_stream.grid(row=7, column=0, padx=20, pady=(20, 5), sticky="w")

        self.btn_select_csv = ctk.CTkButton(self.frame_left, text="Select Data File (.csv)", command=self.select_csv_file)
        self.btn_select_csv.grid(row=8, column=0, padx=20, pady=5)

        # Delay Slider
        self.lbl_delay_val = ctk.CTkLabel(self.frame_left, text="Packet Delay: 100 ms")
        self.lbl_delay_val.grid(row=9, column=0, padx=20, pady=(10, 0), sticky="w")
        self.slider_delay = ctk.CTkSlider(self.frame_left, from_=0, to=1000, number_of_steps=100, command=self.update_delay_lbl)
        self.slider_delay.set(100)
        self.slider_delay.grid(row=10, column=0, padx=20, pady=5)

        self.btn_stream = ctk.CTkButton(self.frame_left, text="Start Live Data Stream", fg_color="green", hover_color="darkgreen", command=self.toggle_stream)
        self.btn_stream.grid(row=11, column=0, padx=20, pady=10)

        self.btn_test_stream = ctk.CTkButton(self.frame_left, text="Test Stream (Random)", fg_color="#1f538d", hover_color="#14375e", command=self.toggle_test_stream)
        self.btn_test_stream.grid(row=12, column=0, padx=20, pady=20)

        # ==========================================
        # RIGHT PANEL (Dashboard & Logs)
        # ==========================================
        self.frame_right = ctk.CTkFrame(self)
        self.frame_right.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.frame_right.grid_columnconfigure(0, weight=1)
        self.frame_right.grid_rowconfigure(1, weight=1)

        # --- Top Dashboard ---
        self.frame_dash = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        self.frame_dash.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.frame_dash.grid_columnconfigure((0, 1, 2), weight=1)

        # Dash Card: Status
        self.card_status = ctk.CTkFrame(self.frame_dash, corner_radius=10)
        self.card_status.grid(row=0, column=0, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_status, text="Last Prediction", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_status = ctk.CTkLabel(self.card_status, text="-", font=ctk.CTkFont(size=40, weight="bold"))
        self.lbl_dash_status.pack(pady=10)

        # Dash Card: Latency
        self.card_lat = ctk.CTkFrame(self.frame_dash, corner_radius=10)
        self.card_lat.grid(row=0, column=1, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_lat, text="Last Latency (us)", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_lat = ctk.CTkLabel(self.card_lat, text="0.00", font=ctk.CTkFont(size=40, weight="bold"), text_color="#2980b9")
        self.lbl_dash_lat.pack(pady=10)

        # Dash Card: Counter
        self.card_cnt = ctk.CTkFrame(self.frame_dash, corner_radius=10)
        self.card_cnt.grid(row=0, column=2, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_cnt, text="Processed Packets", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_cnt = ctk.CTkLabel(self.card_cnt, text="0", font=ctk.CTkFont(size=40, weight="bold"), text_color="#d4ac0d")
        self.lbl_dash_cnt.pack(pady=10)

        # --- Log Console ---
        self.frame_log = ctk.CTkFrame(self.frame_right)
        self.frame_log.grid(row=1, column=0, sticky="nsew")
        self.frame_log.grid_columnconfigure(0, weight=1)
        self.frame_log.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.frame_log, text="System Logs", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=10)

        self.log_textbox = ctk.CTkTextbox(self.frame_log, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.handle_drop)
            self.log_message("SYSTEM", "Drag-and-drop enabled.")
        else:
            self.log_message("SYSTEM", "For drag-and-drop, run 'pip install tkinterdnd2' in the terminal.")

    # ===============================
    # LOGIC & NETWORK
    # ===============================
    def log_message(self, tag, message, color=None):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] [{tag}] {message}\n"

        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", log_entry)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
        print(log_entry, end="")

    def connect_to_engine(self):
        try:
            if self.sock:
                self.sock.close()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(("127.0.0.1", 5005))
            self.is_connected = True
            self.lbl_conn_indicator.configure(text_color="green")
            self.lbl_conn_text.configure(text="Connected to engine (Port 5005)")
            self.btn_reconnect.configure(state="disabled")
            self.log_message("NET", "Successfully connected to the C++ HFT engine.")
            threading.Thread(target=self.tcp_listener, daemon=True).start()
        except Exception as e:
            self.is_connected = False
            self.lbl_conn_indicator.configure(text_color="red")
            self.lbl_conn_text.configure(text="Connection lost")
            self.btn_reconnect.configure(state="normal")
            self.log_message("ERROR", f"Could not connect to engine. Please start the C++ application from the terminal. Error: {str(e)}")

    def tcp_listener(self):
        buffer = ""
        while self.is_connected:
            try:
                data = self.sock.recv(1024).decode('utf-8')
                if not data:
                    break
                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self.handle_engine_message(line)
            except:
                break

        self.is_connected = False
        self.is_streaming = False
        self.after(0, self.handle_disconnect)

    def handle_disconnect(self):
        self.lbl_conn_indicator.configure(text_color="red")
        self.lbl_conn_text.configure(text="Connection lost")
        self.btn_reconnect.configure(state="normal")
        self.btn_stream.configure(state="normal", text="Start Live Data Stream", fg_color="green", hover_color="darkgreen")
        self.btn_test_stream.configure(state="normal", text="Test Stream (Random)", fg_color="#1f538d", hover_color="#14375e")
        self.log_message("NET", "Connection to the C++ engine was lost or timed out.")

    def handle_engine_message(self, msg):
        if msg == "STATUS:MODEL_OK":
            self.log_message("FPGA", "Model weights loaded and verified on the FPGA.")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg.startswith("STATUS:ERROR") or msg == "STATUS:TIMEOUT":
            self.log_message("WARNING", f"Error or timeout: {msg}")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg == "STATUS:STREAM_FINISHED" or msg == "STATUS:STOPPED":
            self.is_streaming = False
            self.log_message("INFO", "Data stream finished or stopped.")
            self.after(0, lambda: self.btn_stream.configure(state="normal", text="Start Live Data Stream", fg_color="green", hover_color="darkgreen"))
            self.after(0, lambda: self.btn_test_stream.configure(state="normal", text="Test Stream (Random)", fg_color="#1f538d", hover_color="#14375e"))
        elif msg.startswith("STATUS:"):
            # Format: STATUS:BUY|LATENCY:12.34
            parts = msg.split('|')
            status = parts[0].split(':')[1]
            latency = 0.0
            if len(parts) > 1 and "LATENCY:" in parts[1]:
                try: latency = float(parts[1].split(':')[1])
                except: pass

            self.packet_count += 1

            # Debounce UI updates to prevent freezing when 1000s of packets arrive
            now = time.time()
            if now - self.last_ui_update > 0.05:
                self.last_ui_update = now
                self.update_dashboard(status, latency, self.packet_count)

    def send_command(self, cmd_str):
        if not self.is_connected:
            self.log_message("ERROR", "Could not send command. Not connected to the C++ engine.")
            self.connect_to_engine()
        if self.is_connected:
            try:
                self.sock.sendall((cmd_str + "\n").encode('utf-8'))
            except Exception as e:
                self.is_connected = False
                self.log_message("ERROR", f"Send error: {str(e)}")

    # ===============================
    # UI EVENT HANDLERS
    # ===============================
    def handle_drop(self, event):
        filepath = event.data
        if filepath.startswith('{') and filepath.endswith('}'):
            filepath = filepath[1:-1]

        if filepath.lower().endswith(('.pth', '.bin', '.txt')):
            self.model_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_model.configure(text=f"Selected: {filename}")
            self.btn_send_model.configure(state="normal")
            self.log_message("SETUP", f"Model dropped: {filename}")
        elif filepath.lower().endswith(('.csv', '.parquet')):
            self.csv_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_csv.configure(text=f"Selected: {filename}")
            self.log_message("SETUP", f"Data dropped: {filename}")
        else:
            self.log_message("WARNING", "Dropped file is not supported (must be .pth, .csv, .parquet, etc.).")

    def update_delay_lbl(self, val):
        self.lbl_delay_val.configure(text=f"Packet Delay: {int(val)} ms")

    def select_model_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Model Files", "*.pth *.bin *.txt"), ("All Files", "*.*")])
        if filepath:
            self.model_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_model.configure(text=f"Selected: {filename}")
            self.btn_send_model.configure(state="normal")
            self.log_message("SETUP", f"Model file selected: {filepath}")

    def process_pth_model(self, pth_file):
        """
        Convert a PyTorch MLP checkpoint into the fixed FPGA weight layout.

        The Vitis firmware expects a fixed 64->32->16->3 network (6819 floats),
        with per-layer weight shapes:
          W1 64x64, W2 32x64, W3 16x32, W4 3x16  (+ matching biases).
        Each trained layer is copied into the top-left of its target block and
        zero-padded; the input dimension (40) is padded to 64 in W1's columns.
        Output is a raw float32 stream, no header.
        """
        try:
            import torch
            import numpy as np
        except ImportError:
            self.log_message("ERROR", "PyTorch is not installed! Run 'pip install torch' to load '.pth' files.")
            messagebox.showerror("Error", "PyTorch is not installed. In the terminal run:\npip install torch")
            return None

        try:
            self.log_message("SETUP", f"Processing PyTorch model: {pth_file}")
            state_dict = torch.load(pth_file, map_location='cpu', weights_only=True)

            # Collect (weight, bias) pairs in file order.
            pending_w = {}
            pending_b = {}
            order = []
            for key, tensor in state_dict.items():
                arr = tensor.detach().cpu().numpy().astype(np.float32)
                if key.endswith(".weight"):
                    prefix = key[:-len(".weight")]
                    pending_w[prefix] = arr
                    if prefix not in order:
                        order.append(prefix)
                elif key.endswith(".bias"):
                    prefix = key[:-len(".bias")]
                    pending_b[prefix] = arr
                    if prefix not in order:
                        order.append(prefix)
                else:
                    self.log_message("WARNING", f"Skipped unexpected parameter: {key}")

            layers = []
            for prefix in order:
                if prefix in pending_w and prefix in pending_b:
                    layers.append((pending_w[prefix], pending_b[prefix]))
                else:
                    self.log_message("WARNING", f"Missing weight/bias for '{prefix}', skipping.")

            if not layers:
                self.log_message("ERROR", "No Linear layers found in the model.")
                return None

            # Architecture summary for the log
            dims = [layers[0][0].shape[1]] + [w.shape[0] for (w, b) in layers]
            arch_str = "->".join(str(d) for d in dims)
            self.log_message("SETUP", f"Detected architecture: {arch_str} ({len(layers)} layers)")

            if len(layers) != FPGA_NUM_LAYERS:
                self.log_message("WARNING",
                                 f"Model has {len(layers)} layers but FPGA expects "
                                 f"{FPGA_NUM_LAYERS}. Mismatched layers will be zero-padded/truncated.")

            # Build the fixed firmware template, per-layer zero-padded.
            out_blocks = []
            for i in range(FPGA_NUM_LAYERS):
                t_out, t_in = FPGA_LAYER_SHAPES[i]
                t_bias = FPGA_BIAS_SIZES[i]
                w = np.zeros((t_out, t_in), dtype=np.float32)
                b = np.zeros((t_bias,), dtype=np.float32)
                if i < len(layers):
                    ow, ob = layers[i]
                    if ow.shape[0] > t_out or ow.shape[1] > t_in:
                        self.log_message("WARNING",
                                         f"Layer {i+1} {ow.shape} exceeds target {(t_out, t_in)} and will be truncated.")
                    r = min(ow.shape[0], t_out)
                    c = min(ow.shape[1], t_in)
                    w[:r, :c] = ow[:r, :c]
                    nb = min(ob.shape[0], t_bias)
                    b[:nb] = ob[:nb]
                out_blocks.append(w.flatten())   # row-major (C-order)
                out_blocks.append(b)

            flat = np.concatenate(out_blocks).astype('<f4')

            if flat.size != FPGA_MODEL_FLOATS:
                self.log_message("ERROR",
                                 f"Internal error: produced {flat.size} floats, expected {FPGA_MODEL_FLOATS}.")
                return None

            temp_bin = "temp_weights.bin"
            with open(temp_bin, "wb") as f:
                f.write(flat.tobytes())

            self.log_message("SETUP",
                             f"PyTorch model converted to the fixed FPGA '.bin' format "
                             f"({FPGA_MODEL_FLOATS} floats, 64->32->16->3 layout).")
            return os.path.abspath(temp_bin)

        except Exception as e:
            self.log_message("ERROR", f"PyTorch processing error: {e}")
            return None

    def send_model(self):
        self.btn_send_model.configure(state="disabled")

        target_file = self.model_filepath
        if target_file.endswith(".pth"):
            processed_file = self.process_pth_model(target_file)
            if not processed_file:
                self.btn_send_model.configure(state="normal")
                return
            target_file = processed_file

        self.log_message("SETUP", "Sending model to the FPGA, please wait...")
        self.send_command(f"MODEL:{target_file}")

    def select_csv_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Data Files", "*.csv *.parquet"), ("All Files", "*.*")])
        if filepath:
            self.csv_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_csv.configure(text=f"Selected: {filename}")
            self.log_message("SETUP", f"Data file selected: {filepath}")

    def reset_ui_on_error(self):
        self.is_streaming = False
        self.btn_stream.configure(text="Start Live Data Stream", fg_color="green", hover_color="darkgreen")
        self.btn_test_stream.configure(state="normal")

    def toggle_stream(self):
        if not self.csv_filepath:
            self.log_message("ERROR", "You must select a data (CSV/Parquet) file before starting a live stream!")
            messagebox.showwarning("Warning", "Please select a data (CSV/Parquet) file first!")
            return

        if self.is_streaming:
            self.is_streaming = False
            self.btn_stream.configure(text="Start Live Data Stream", fg_color="green", hover_color="darkgreen")
            self.btn_test_stream.configure(state="normal")
            self.send_command("STOP")
            self.log_message("STREAM", "Stop request sent.")
        else:
            self.is_streaming = True
            self.packet_count = 0
            self.btn_stream.configure(text="Stop Stream", fg_color="#c0392b", hover_color="#922b21")
            self.btn_test_stream.configure(state="disabled")

            stream_target = self.csv_filepath
            if stream_target.endswith(".parquet"):
                base_name = os.path.basename(stream_target)
                # Create a unique temp file name for this parquet file to reuse it later
                temp_csv = f"{base_name}_converted.csv"

                if os.path.exists(temp_csv):
                    self.log_message("STREAM", "Converted CSV for this Parquet found. (Using cache)")
                    stream_target = os.path.abspath(temp_csv)
                    delay_ms = str(int(self.slider_delay.get()))
                    self.send_command(f"STREAM:{stream_target}:{delay_ms}")
                    self.log_message("STREAM", f"Live data stream started. Delay: {delay_ms}ms")
                    return

                self.log_message("STREAM", "Parquet file detected. Converting to CSV in the background, please wait...")

                def convert_and_start():
                    try:
                        import pandas as pd
                        pd.read_parquet(stream_target).to_csv(temp_csv, index=False, header=False)
                        target = os.path.abspath(temp_csv)
                        self.log_message("STREAM", "Parquet conversion successful. File cached.")
                        delay_ms = str(int(self.slider_delay.get()))
                        self.send_command(f"STREAM:{target}:{delay_ms}")
                        self.log_message("STREAM", f"Live data stream started. Delay: {delay_ms}ms")
                    except ImportError:
                        self.log_message("ERROR", "Pandas or PyArrow library missing! (Run 'pip install pandas pyarrow' in the terminal)")
                        self.after(0, self.reset_ui_on_error)
                    except Exception as e:
                        self.log_message("ERROR", f"Parquet conversion error: {e}")
                        self.after(0, self.reset_ui_on_error)

                threading.Thread(target=convert_and_start, daemon=True).start()
                return  # Thread will handle sending the stream command

            delay_ms = str(int(self.slider_delay.get()))
            self.send_command(f"STREAM:{stream_target}:{delay_ms}")
            self.log_message("STREAM", f"Live data stream started. Delay: {delay_ms}ms")

    def toggle_test_stream(self):
        if self.is_streaming:
            self.is_streaming = False
            self.btn_test_stream.configure(text="Test Stream (Random)", fg_color="#1f538d", hover_color="#14375e")
            self.btn_stream.configure(state="normal")
            self.send_command("STOP")
            self.log_message("STREAM", "Test stream stop request sent.")
        else:
            self.is_streaming = True
            self.packet_count = 0
            self.btn_test_stream.configure(text="Stop Test Stream", fg_color="#c0392b", hover_color="#922b21")
            self.btn_stream.configure(state="disabled")
            delay_ms = str(int(self.slider_delay.get()))
            self.send_command(f"TEST_STREAM:{delay_ms}")
            self.log_message("STREAM", f"Test stream started with random data. Delay: {delay_ms}ms")

    def update_dashboard(self, status, latency, count):
        def update():
            # Update Counters
            self.lbl_dash_cnt.configure(text=f"{count}")
            self.lbl_dash_lat.configure(text=f"{latency:.2f}")

            # Update Status text and color
            if status == "SELL":
                self.lbl_dash_status.configure(text="SELL", text_color="#c0392b")  # Darker Red
            elif status == "HOLD":
                self.lbl_dash_status.configure(text="HOLD", text_color="#7f8c8d")  # Darker Gray
            elif status == "BUY":
                self.lbl_dash_status.configure(text="BUY", text_color="#27ae60")   # Darker Green
            else:
                self.lbl_dash_status.configure(text=status, text_color="#d35400")  # Darker Orange

        self.after(0, update)

if __name__ == "__main__":
    app = HFTFrontendApp()
    app.mainloop()
