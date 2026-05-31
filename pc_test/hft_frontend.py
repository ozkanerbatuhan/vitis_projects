import os
import threading
import socket
import time
import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox
import struct

# Set theme and appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class HFTFrontendApp(ctk.CTk):
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
        self.log_message("SYSTEM", "Arayüz başlatıldı. C++ motoruna bağlanılıyor...")
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
        self.lbl_conn_text = ctk.CTkLabel(self.frame_conn, text="Bağlantı Bekleniyor", font=ctk.CTkFont(size=14))
        self.lbl_conn_text.pack(side="left", padx=10)
        
        self.btn_reconnect = ctk.CTkButton(self.frame_left, text="Tekrar Bağlan", command=self.connect_to_engine, fg_color="gray", hover_color="darkgray")
        self.btn_reconnect.grid(row=2, column=0, padx=20, pady=10)
        
        # --- Model Setup ---
        lbl_model = ctk.CTkLabel(self.frame_left, text="Model Yükleme", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_model.grid(row=3, column=0, padx=20, pady=(30, 5), sticky="w")
        
        self.btn_select_model = ctk.CTkButton(self.frame_left, text="Model Seç (.bin)", command=self.select_model_file)
        self.btn_select_model.grid(row=4, column=0, padx=20, pady=5)
        
        self.btn_send_model = ctk.CTkButton(self.frame_left, text="Modeli Gönder", state="disabled", fg_color="#b8860b", hover_color="#8b6508", command=self.send_model)
        self.btn_send_model.grid(row=5, column=0, padx=20, pady=5)
        
        # --- Spacer ---
        
        # --- Stream Setup ---
        lbl_stream = ctk.CTkLabel(self.frame_left, text="Veri Akışı (Streaming)", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_stream.grid(row=7, column=0, padx=20, pady=(20, 5), sticky="w")
        
        self.btn_select_csv = ctk.CTkButton(self.frame_left, text="Veri Dosyası Seç (.csv)", command=self.select_csv_file)
        self.btn_select_csv.grid(row=8, column=0, padx=20, pady=5)
        
        # Delay Slider
        self.lbl_delay_val = ctk.CTkLabel(self.frame_left, text="Paket Gecikmesi: 100 ms")
        self.lbl_delay_val.grid(row=9, column=0, padx=20, pady=(10, 0), sticky="w")
        self.slider_delay = ctk.CTkSlider(self.frame_left, from_=0, to=1000, number_of_steps=100, command=self.update_delay_lbl)
        self.slider_delay.set(100)
        self.slider_delay.grid(row=10, column=0, padx=20, pady=5)
        
        self.btn_stream = ctk.CTkButton(self.frame_left, text="Gerçek Veri Akışını Başlat", fg_color="green", hover_color="darkgreen", command=self.toggle_stream)
        self.btn_stream.grid(row=11, column=0, padx=20, pady=10)
        
        self.btn_test_stream = ctk.CTkButton(self.frame_left, text="Test Akışı (Random)", fg_color="#1f538d", hover_color="#14375e", command=self.toggle_test_stream)
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
        self.card_status = ctk.CTkFrame(self.frame_dash, fg_color="#2b2b2b", corner_radius=10)
        self.card_status.grid(row=0, column=0, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_status, text="Son Tahmin", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_status = ctk.CTkLabel(self.card_status, text="-", font=ctk.CTkFont(size=40, weight="bold"))
        self.lbl_dash_status.pack(pady=10)
        
        # Dash Card: Latency
        self.card_lat = ctk.CTkFrame(self.frame_dash, fg_color="#2b2b2b", corner_radius=10)
        self.card_lat.grid(row=0, column=1, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_lat, text="Son Gecikme (us)", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_lat = ctk.CTkLabel(self.card_lat, text="0.00", font=ctk.CTkFont(size=40, weight="bold"), text_color="#3498db")
        self.lbl_dash_lat.pack(pady=10)
        
        # Dash Card: Counter
        self.card_cnt = ctk.CTkFrame(self.frame_dash, fg_color="#2b2b2b", corner_radius=10)
        self.card_cnt.grid(row=0, column=2, sticky="nsew", padx=5)
        ctk.CTkLabel(self.card_cnt, text="İşlenen Paket", font=ctk.CTkFont(size=14)).pack(pady=(10, 0))
        self.lbl_dash_cnt = ctk.CTkLabel(self.card_cnt, text="0", font=ctk.CTkFont(size=40, weight="bold"), text_color="#f1c40f")
        self.lbl_dash_cnt.pack(pady=10)
        
        # --- Log Console ---
        self.frame_log = ctk.CTkFrame(self.frame_right)
        self.frame_log.grid(row=1, column=0, sticky="nsew")
        self.frame_log.grid_columnconfigure(0, weight=1)
        self.frame_log.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(self.frame_log, text="Sistem Logları", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        
        self.log_textbox = ctk.CTkTextbox(self.frame_log, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

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
            self.lbl_conn_text.configure(text="Motora Bağlı (Port 5005)")
            self.btn_reconnect.configure(state="disabled")
            self.log_message("NET", "C++ HFT Motoruna başarıyla bağlanıldı.")
            threading.Thread(target=self.tcp_listener, daemon=True).start()
        except Exception as e:
            self.is_connected = False
            self.lbl_conn_indicator.configure(text_color="red")
            self.lbl_conn_text.configure(text="Bağlantı Koptu")
            self.btn_reconnect.configure(state="normal")
            self.log_message("ERROR", f"Motora bağlanılamadı. Lütfen terminalden C++ uygulamasını başlatın. Hata: {str(e)}")

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
        self.lbl_conn_text.configure(text="Bağlantı Koptu")
        self.btn_reconnect.configure(state="normal")
        self.btn_stream.configure(state="normal", text="Gerçek Veri Akışını Başlat", fg_color="green", hover_color="darkgreen")
        self.btn_test_stream.configure(state="normal", text="Test Akışı (Random)", fg_color="#1f538d", hover_color="#14375e")
        self.log_message("NET", "C++ motoruyla bağlantı kesildi veya zaman aşımına uğradı.")

    def handle_engine_message(self, msg):
        if msg == "STATUS:MODEL_OK":
            self.log_message("FPGA", "Model ağırlıkları FPGA'e yüklendi ve doğrulandı.")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg.startswith("STATUS:ERROR") or msg == "STATUS:TIMEOUT":
            self.log_message("WARNING", f"Hata veya Zaman Aşımı: {msg}")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg == "STATUS:STREAM_FINISHED" or msg == "STATUS:STOPPED":
            self.is_streaming = False
            self.log_message("INFO", "Veri akışı tamamlandı veya durduruldu.")
            self.after(0, lambda: self.btn_stream.configure(state="normal", text="Gerçek Veri Akışını Başlat", fg_color="green", hover_color="darkgreen"))
            self.after(0, lambda: self.btn_test_stream.configure(state="normal", text="Test Akışı (Random)", fg_color="#1f538d", hover_color="#14375e"))
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
            self.log_message("ERROR", "Komut gönderilemedi. C++ motoruna bağlı değilsiniz.")
            self.connect_to_engine()
        if self.is_connected:
            try:
                self.sock.sendall((cmd_str + "\n").encode('utf-8'))
            except Exception as e:
                self.is_connected = False
                self.log_message("ERROR", f"Gönderim hatası: {str(e)}")

    # ===============================
    # UI EVENT HANDLERS
    # ===============================
    def update_delay_lbl(self, val):
        self.lbl_delay_val.configure(text=f"Paket Gecikmesi: {int(val)} ms")

    def select_model_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Model Files", "*.pth *.bin *.txt"), ("All Files", "*.*")])
        if filepath:
            self.model_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_model.configure(text=f"Seçildi: {filename}")
            self.btn_send_model.configure(state="normal")
            self.log_message("SETUP", f"Model dosyası seçildi: {filepath}")

    def process_pth_model(self, pth_file):
        try:
            import torch
        except ImportError:
            self.log_message("ERROR", "PyTorch yüklü değil! '.pth' yüklemek için 'pip install torch' çalıştırın.")
            messagebox.showerror("Hata", "PyTorch yüklü değil. Terminalden:\npip install torch\nçalıştırın.")
            return None

        try:
            self.log_message("SETUP", f"PyTorch modeli işleniyor: {pth_file}")
            state_dict = torch.load(pth_file, map_location='cpu', weights_only=True)
            
            weights = []
            biases = []
            for key, tensor in state_dict.items():
                val = tensor.numpy()
                if 'weight' in key:
                    weights.append(val) # Shape: (out_features, in_features)
                elif 'bias' in key:
                    biases.append(val)
                    
            if len(weights) != 4:
                self.log_message("ERROR", "Desteklenmeyen model mimarisi. 4 katman (Linear) bekleniyor.")
                return None
                
            # W1 PADDING: PyTorch has W1=(64, 40). Hardware expects (64, 64).
            w1 = weights[0]
            if w1.shape[1] == 40:
                self.log_message("SETUP", "Layer 1 ağırlıkları donanım için (64, 64) boyutuna pad ediliyor...")
                import numpy as np
                w1_padded = np.zeros((64, 64), dtype=np.float32)
                w1_padded[:, :40] = w1
                weights[0] = w1_padded
                
            # L1(64x64) + B1(64) + L2(32x64) + B2(32) + L3(16x32) + B3(16) + L4(3x16) + B4(3)
            # Flatten everything in C-order (which matches row-major, meaning sequence is row0, row1...)
            # Actually, standard layout is what we need.
            out_floats = []
            for w, b in zip(weights, biases):
                out_floats.extend(w.flatten().tolist())
                out_floats.extend(b.flatten().tolist())
                
            if len(out_floats) != 6819:
                self.log_message("ERROR", f"Beklenen 6819 float, ancak {len(out_floats)} bulundu!")
                return None
                
            temp_bin = "temp_weights.bin"
            with open(temp_bin, "wb") as f:
                for val in out_floats:
                    f.write(struct.pack('f', val))
                    
            self.log_message("SETUP", "PyTorch modeli 6819 parametreli FPGA '.bin' formatına başarıyla çevrildi.")
            return os.path.abspath(temp_bin)
            
        except Exception as e:
            self.log_message("ERROR", f"PyTorch işleme hatası: {e}")
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
            
        self.log_message("SETUP", "Model FPGA'e gönderiliyor, lütfen bekleyin...")
        self.send_command(f"MODEL:{target_file}")

    def select_csv_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Data Files", "*.csv *.parquet"), ("All Files", "*.*")])
        if filepath:
            self.csv_filepath = filepath
            filename = os.path.basename(filepath)
            self.btn_select_csv.configure(text=f"Seçildi: {filename}")
            self.log_message("SETUP", f"Veri dosyası seçildi: {filepath}")

    def reset_ui_on_error(self):
        self.is_streaming = False
        self.btn_stream.configure(text="Gerçek Veri Akışını Başlat", fg_color="green", hover_color="darkgreen")
        self.btn_test_stream.configure(state="normal")

    def toggle_stream(self):
        if not self.csv_filepath:
            self.log_message("ERROR", "Gerçek veri akışı için önce bir veri (CSV/Parquet) dosyası seçmelisiniz!")
            messagebox.showwarning("Uyarı", "Lütfen önce bir veri (CSV/Parquet) dosyası seçin!")
            return
            
        if self.is_streaming:
            self.is_streaming = False
            self.btn_stream.configure(text="Gerçek Veri Akışını Başlat", fg_color="green", hover_color="darkgreen")
            self.btn_test_stream.configure(state="normal")
            self.send_command("STOP")
            self.log_message("STREAM", "Akışı durdurma isteği gönderildi.")
        else:
            self.is_streaming = True
            self.packet_count = 0
            self.btn_stream.configure(text="Akışı Durdur", fg_color="#c0392b", hover_color="#922b21")
            self.btn_test_stream.configure(state="disabled")
            
            stream_target = self.csv_filepath
            if stream_target.endswith(".parquet"):
                self.log_message("STREAM", "Parquet dosyası algılandı. Arka planda CSV'ye dönüştürülüyor, lütfen bekleyin...")
                
                def convert_and_start():
                    try:
                        import pandas as pd
                        temp_csv = "temp_stream_converted.csv"
                        pd.read_parquet(stream_target).to_csv(temp_csv, index=False, header=False)
                        target = os.path.abspath(temp_csv)
                        self.log_message("STREAM", "Parquet dönüşümü başarılı. Akış başlıyor...")
                        delay_ms = str(int(self.slider_delay.get()))
                        self.send_command(f"STREAM:{target}:{delay_ms}")
                        self.log_message("STREAM", f"Gerçek veri akışı başlatıldı. Gecikme: {delay_ms}ms")
                    except ImportError:
                        self.log_message("ERROR", "Pandas veya PyArrow kütüphanesi eksik! (Terminalden 'pip install pandas pyarrow' çalıştırın)")
                        self.after(0, self.reset_ui_on_error)
                    except Exception as e:
                        self.log_message("ERROR", f"Parquet dönüştürme hatası: {e}")
                        self.after(0, self.reset_ui_on_error)

                threading.Thread(target=convert_and_start, daemon=True).start()
                return # Thread will handle sending the stream command
            
            delay_ms = str(int(self.slider_delay.get()))
            self.send_command(f"STREAM:{stream_target}:{delay_ms}")
            self.log_message("STREAM", f"Gerçek veri akışı başlatıldı. Gecikme: {delay_ms}ms")

    def toggle_test_stream(self):
        if self.is_streaming:
            self.is_streaming = False
            self.btn_test_stream.configure(text="Test Akışı (Random)", fg_color="#1f538d", hover_color="#14375e")
            self.btn_stream.configure(state="normal")
            self.send_command("STOP")
            self.log_message("STREAM", "Test akışını durdurma isteği gönderildi.")
        else:
            self.is_streaming = True
            self.packet_count = 0
            self.btn_test_stream.configure(text="Test Akışını Durdur", fg_color="#c0392b", hover_color="#922b21")
            self.btn_stream.configure(state="disabled")
            delay_ms = str(int(self.slider_delay.get()))
            self.send_command(f"TEST_STREAM:{delay_ms}")
            self.log_message("STREAM", f"Rastgele verilerle Test Akışı başlatıldı. Gecikme: {delay_ms}ms")

    def update_dashboard(self, status, latency, count):
        def update():
            # Update Counters
            self.lbl_dash_cnt.configure(text=f"{count}")
            self.lbl_dash_lat.configure(text=f"{latency:.2f}")
            
            # Update Status text and color
            if status == "SELL":
                self.lbl_dash_status.configure(text="SELL", text_color="#e74c3c")  # Red
            elif status == "HOLD":
                self.lbl_dash_status.configure(text="HOLD", text_color="#95a5a6")  # Gray
            elif status == "BUY":
                self.lbl_dash_status.configure(text="BUY", text_color="#2ecc71")   # Green
            else:
                self.lbl_dash_status.configure(text=status, text_color="#f39c12")  # Orange
                
        self.after(0, update)

if __name__ == "__main__":
    app = HFTFrontendApp()
    app.mainloop()
