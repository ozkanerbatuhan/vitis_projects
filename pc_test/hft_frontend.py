import os
import threading
import socket
import time
import customtkinter as ctk
from tkinter import filedialog, messagebox

class HFTFrontendApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("FPGA HFT Accelerator - Control Panel (IPC Client)")
        self.geometry("700x550")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=20, fill="both", expand=True)
        
        self.tab_setup = self.tabview.add("Setup (Model Yükleme)")
        self.tab_stream = self.tabview.add("HFT Streamer (Canlı Akış)")
        
        self.build_setup_tab()
        self.build_stream_tab()
        
        self.model_filepath = None
        self.csv_filepath = None
        
        self.is_connected = False
        self.is_streaming = False
        self.sock = None
        
        # Debounce/Batch update mantigi icin degiskenler
        self.latest_status = None
        self.latest_latency = 0.0
        self.packet_count = 0
        self.last_ui_update = time.time()
        
        # Baslangicta motora baglanmayi dene
        self.connect_to_engine()

    def connect_to_engine(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(("127.0.0.1", 5005))
            self.is_connected = True
            threading.Thread(target=self.tcp_listener, daemon=True).start()
        except:
            self.is_connected = False
            messagebox.showwarning("Bağlantı Hatası", "C++ HFT Motoru (hft_engine.exe) çalışmıyor. Lütfen önce terminalden motoru başlatın.")

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
        self.after(0, lambda: self.btn_stream.configure(text="Tetikle / Akışı Başlat", fg_color="green", hover_color="darkgreen"))
        print("C++ motoruyla bağlantı kesildi.")

    def handle_engine_message(self, msg):
        if msg == "STATUS:MODEL_OK":
            self.update_setup_status("Başarılı! Model FPGA'e yüklendi (ACK alındı).", "green")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg.startswith("STATUS:ERROR") or msg == "STATUS:TIMEOUT":
            self.update_setup_status(f"Hata/Zaman Aşımı: {msg}", "red")
            self.after(0, lambda: self.btn_send_model.configure(state="normal"))
        elif msg == "STATUS:STREAM_FINISHED" or msg == "STATUS:STOPPED":
            self.is_streaming = False
            self.after(0, lambda: self.btn_stream.configure(text="Tetikle / Akışı Başlat", fg_color="green", hover_color="darkgreen"))
        elif msg.startswith("STATUS:"):
            # STATUS:BUY|LATENCY:12.34
            parts = msg.split('|')
            status = parts[0].split(':')[1]
            latency = 0.0
            if len(parts) > 1 and "LATENCY:" in parts[1]:
                try: latency = float(parts[1].split(':')[1])
                except: pass
            
            self.packet_count += 1
            self.latest_status = status
            self.latest_latency = latency
            
            # 50ms Debounce Mantigi (UI Kilitlenmesini Engeller)
            now = time.time()
            if now - self.last_ui_update > 0.05:
                self.last_ui_update = now
                self.update_stream_ui(self.latest_status, self.packet_count, self.latest_latency)

    def send_command(self, cmd_str):
        if not self.is_connected:
            self.connect_to_engine()
        if self.is_connected:
            try:
                self.sock.sendall((cmd_str + "\n").encode('utf-8'))
            except:
                self.is_connected = False

    # ===============================
    # TAB 1: MODEL SETUP
    # ===============================
    def build_setup_tab(self):
        title = ctk.CTkLabel(self.tab_setup, text="Model Ağırlıklarını Yükle", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=20)
        
        self.lbl_model_file = ctk.CTkLabel(self.tab_setup, text="Henüz dosya seçilmedi (.bin veya .txt)")
        self.lbl_model_file.pack(pady=10)
        
        btn_select = ctk.CTkButton(self.tab_setup, text="Dosya Seç", command=self.select_model_file)
        btn_select.pack(pady=10)
        
        self.btn_send_model = ctk.CTkButton(self.tab_setup, text="FPGA'e Gönder", state="disabled", fg_color="green", hover_color="darkgreen", command=self.send_model)
        self.btn_send_model.pack(pady=30)
        
        self.setup_status = ctk.CTkLabel(self.tab_setup, text="", text_color="yellow")
        self.setup_status.pack(pady=10)

    def select_model_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Model Files", "*.bin *.txt *.csv"), ("All Files", "*.*")])
        if filepath:
            self.model_filepath = filepath
            self.lbl_model_file.configure(text=os.path.basename(filepath))
            self.btn_send_model.configure(state="normal")

    def send_model(self):
        self.btn_send_model.configure(state="disabled")
        self.update_setup_status("C++ motoruna komut gönderiliyor...", "yellow")
        self.send_command(f"MODEL:{self.model_filepath}")

    def update_setup_status(self, text, color):
        self.after(0, lambda: self.setup_status.configure(text=text, text_color=color))

    # ===============================
    # TAB 2: HFT STREAMER
    # ===============================
    def build_stream_tab(self):
        title = ctk.CTkLabel(self.tab_stream, text="Canlı HFT Piyasası Simülasyonu", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=10)
        
        frame_file = ctk.CTkFrame(self.tab_stream)
        frame_file.pack(pady=10, padx=20, fill="x")
        self.lbl_csv_file = ctk.CTkLabel(frame_file, text="Veri dosyası (CSV): Seçilmedi")
        self.lbl_csv_file.pack(side="left", padx=10, pady=10)
        btn_csv = ctk.CTkButton(frame_file, text="Gözat", width=100, command=self.select_csv_file)
        btn_csv.pack(side="right", padx=10, pady=10)
        
        frame_delay = ctk.CTkFrame(self.tab_stream)
        frame_delay.pack(pady=10, padx=20, fill="x")
        lbl_delay = ctk.CTkLabel(frame_delay, text="Paket Arası Bekleme (Gecikme ms):")
        lbl_delay.pack(side="left", padx=10, pady=10)
        self.slider_delay = ctk.CTkSlider(frame_delay, from_=0, to=1000, number_of_steps=100)
        self.slider_delay.set(100)
        self.slider_delay.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.lbl_delay_val = ctk.CTkLabel(frame_delay, text="100 ms")
        self.lbl_delay_val.pack(side="right", padx=10, pady=10)
        self.slider_delay.configure(command=self.update_delay_lbl)
        
        self.btn_stream = ctk.CTkButton(self.tab_stream, text="Tetikle / Akışı Başlat", fg_color="green", hover_color="darkgreen", command=self.toggle_stream)
        self.btn_stream.pack(pady=10)
        
        self.lbl_result = ctk.CTkLabel(self.tab_stream, text="BEKLENİYOR...", font=ctk.CTkFont(size=30, weight="bold"), text_color="gray")
        self.lbl_result.pack(pady=20)
        
        self.lbl_stats = ctk.CTkLabel(self.tab_stream, text="Gönderilen Paket: 0 | Gecikme: 0.0 us")
        self.lbl_stats.pack(pady=5)

    def update_delay_lbl(self, val):
        self.lbl_delay_val.configure(text=f"{int(val)} ms")

    def select_csv_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")])
        if filepath:
            self.csv_filepath = filepath
            self.lbl_csv_file.configure(text=f"Dosya: {os.path.basename(filepath)}")

    def toggle_stream(self):
        if not self.csv_filepath:
            messagebox.showwarning("Uyarı", "Lütfen önce bir veri (CSV) dosyası seçin!")
            return
            
        if self.is_streaming:
            self.is_streaming = False
            self.btn_stream.configure(text="Tetikle / Akışı Başlat", fg_color="green", hover_color="darkgreen")
            self.send_command("STOP")
        else:
            self.is_streaming = True
            self.packet_count = 0
            self.btn_stream.configure(text="Akışı Durdur", fg_color="red", hover_color="darkred")
            delay_ms = str(int(self.slider_delay.get()))
            self.send_command(f"STREAM:{self.csv_filepath}:{delay_ms}")

    def update_stream_ui(self, status, count, latency):
        if status == "SELL":
            text, color = "SELL (SAT)", "red"
        elif status == "HOLD":
            text, color = "HOLD (BEKLE)", "gray"
        elif status == "BUY":
            text, color = "BUY (AL)", "green"
        else:
            text, color = f"HATA: {status}", "orange"
            
        def update():
            self.lbl_result.configure(text=text, text_color=color)
            self.lbl_stats.configure(text=f"Gönderilen Paket: {count} | Gecikme: {latency:.2f} us")
            
        self.after(0, update)

if __name__ == "__main__":
    app = HFTFrontendApp()
    app.mainloop()
