#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <chrono>
#include <thread>
#include <atomic>
#include <iomanip>
#include <mutex>
#include <winsock2.h>
#include <windows.h>
#include <mmsystem.h>
#include <random>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "winmm.lib")

#define FPGA_IP "192.168.1.10"
#define FPGA_PORT 7000
#define IPC_PORT 5005
#define UDP_TIMEOUT_MS 2000

using namespace std;

// Global Thread & Socket Degiskenleri
atomic<bool> is_streaming{false};
thread stream_thread;
SOCKET udp_sock = INVALID_SOCKET;
SOCKET tcp_client_sock = INVALID_SOCKET;
sockaddr_in board_addr;
mutex tcp_mutex;

// Python arayuzune TCP uzerinden anlik durum/gecikme yollama fonksiyonu
void send_tcp_message(const string& msg) {
    lock_guard<mutex> lock(tcp_mutex);
    if (tcp_client_sock != INVALID_SOCKET) {
        string packet = msg + "\n";
        send(tcp_client_sock, packet.c_str(), packet.length(), 0);
    }
}

// Canli akisi arka planda donduren is parcacigi (Thread)
void stream_task(string filepath, int delay_ms) {
    ifstream file(filepath);
    if (!file) { 
        send_tcp_message("STATUS:ERROR_FILE"); 
        is_streaming = false;
        return; 
    }

    ofstream log_file("execution_log.csv", ios::app);
    if (log_file.tellp() == 0) {
        log_file << "Timestamp_us,Latency_us,Result\n";
    }

    string line;
    LARGE_INTEGER freq, t0, t1;
    QueryPerformanceFrequency(&freq);

    while (is_streaming && getline(file, line)) {
        if (line.empty()) continue;

        vector<int16_t> q88_features;
        stringstream ss(line);
        string token;

        // Sayilari virgulle ayikla (pandas yok!)
        while (getline(ss, token, ',')) {
            try {
                float val = stof(token);
                q88_features.push_back(static_cast<int16_t>(val * 256.0f)); 
            } catch (...) {}
        }

        // 64'e zero-padding ile tamamla
        if (q88_features.size() < 64) q88_features.resize(64, 0);
        else if (q88_features.size() > 64) q88_features.resize(64);

        // Paket (0x02 Header + Padding)
        vector<uint8_t> payload;
        payload.push_back(0x02);
        payload.push_back(0x00);
        payload.push_back(0x00);
        payload.push_back(0x00);

        const uint8_t* q88_bytes = reinterpret_cast<const uint8_t*>(q88_features.data());
        payload.insert(payload.end(), q88_bytes, q88_bytes + (64 * sizeof(int16_t)));

        // HFT UDP Sinyal Gonderimi ve Mikrosaniye olcumu
        QueryPerformanceCounter(&t0);
        sendto(udp_sock, reinterpret_cast<const char*>(payload.data()), payload.size(), 0, (sockaddr*)&board_addr, sizeof(board_addr));

        char rx_buf[64];
        sockaddr_in from;
        int fromlen = sizeof(from);
        int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr*)&from, &fromlen);
        QueryPerformanceCounter(&t1);

        double latency_us = (double)(t1.QuadPart - t0.QuadPart) * 1000000.0 / (double)freq.QuadPart;
        auto now_us = chrono::duration_cast<chrono::microseconds>(chrono::system_clock::now().time_since_epoch()).count();

        if (n > 0) {
            uint8_t res = static_cast<uint8_t>(rx_buf[0]);
            string result_str;
            if (res == 0) result_str = "SELL";
            else if (res == 1) result_str = "HOLD";
            else if (res == 2) result_str = "BUY";
            else if (res == 0xDD) {
                rx_buf[n] = '\0';
                result_str = string(rx_buf + 1);
            }
            else result_str = "UNKNOWN";

            // IPC: Python Client'a yanit ilet
            ostringstream msg;
            msg << "STATUS:" << result_str << "|LATENCY:" << fixed << setprecision(2) << latency_us;
            send_tcp_message(msg.str());

            // Diske hizlica isleyip flushla
            log_file << now_us << "," << fixed << setprecision(2) << latency_us << "," << result_str << "\n";
            log_file.flush();
        } else {
            send_tcp_message("STATUS:TIMEOUT");
            log_file << now_us << ",TIMEOUT,TIMEOUT\n";
            log_file.flush();
        }

        // Akis hizi beklemesi
        if (delay_ms > 0 && is_streaming) {
            this_thread::sleep_for(chrono::milliseconds(delay_ms));
        }
    }
    
    if (is_streaming) {
        send_tcp_message("STATUS:STREAM_FINISHED");
    }
    is_streaming = false;
}

// Test akisi icin random veri ureten thread
void test_stream_task(int delay_ms) {
    ofstream log_file("execution_log.csv", ios::app);
    if (log_file.tellp() == 0) {
        log_file << "Timestamp_us,Latency_us,Result\n";
    }

    LARGE_INTEGER freq, t0, t1;
    QueryPerformanceFrequency(&freq);

    random_device rd;
    mt19937 mt(rd());
    uniform_real_distribution<float> dist(-1.0f, 1.0f);

    while (is_streaming) {
        vector<int16_t> q88_features(64);
        for(int i=0; i<64; ++i) {
            q88_features[i] = static_cast<int16_t>(dist(mt) * 256.0f);
        }

        vector<uint8_t> payload;
        payload.push_back(0x02);
        payload.push_back(0x00);
        payload.push_back(0x00);
        payload.push_back(0x00);

        const uint8_t* q88_bytes = reinterpret_cast<const uint8_t*>(q88_features.data());
        payload.insert(payload.end(), q88_bytes, q88_bytes + (64 * sizeof(int16_t)));

        QueryPerformanceCounter(&t0);
        sendto(udp_sock, reinterpret_cast<const char*>(payload.data()), payload.size(), 0, (sockaddr*)&board_addr, sizeof(board_addr));

        char rx_buf[64];
        sockaddr_in from;
        int fromlen = sizeof(from);
        int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr*)&from, &fromlen);
        QueryPerformanceCounter(&t1);

        double latency_us = (double)(t1.QuadPart - t0.QuadPart) * 1000000.0 / (double)freq.QuadPart;
        auto now_us = chrono::duration_cast<chrono::microseconds>(chrono::system_clock::now().time_since_epoch()).count();

        if (n > 0) {
            uint8_t res = static_cast<uint8_t>(rx_buf[0]);
            string result_str;
            if (res == 0) result_str = "SELL";
            else if (res == 1) result_str = "HOLD";
            else if (res == 2) result_str = "BUY";
            else if (res == 0xDD) {
                rx_buf[n] = '\0';
                result_str = string(rx_buf + 1);
            }
            else result_str = "UNKNOWN";

            ostringstream msg;
            msg << "STATUS:" << result_str << "|LATENCY:" << fixed << setprecision(2) << latency_us;
            send_tcp_message(msg.str());

            log_file << now_us << "," << fixed << setprecision(2) << latency_us << "," << result_str << "\n";
            log_file.flush();
        } else {
            send_tcp_message("STATUS:TIMEOUT");
            log_file << now_us << ",TIMEOUT,TIMEOUT\n";
            log_file.flush();
        }

        if (delay_ms > 0 && is_streaming) {
            this_thread::sleep_for(chrono::milliseconds(delay_ms));
        }
    }
    
    if (is_streaming) {
        send_tcp_message("STATUS:STREAM_FINISHED");
    }
    is_streaming = false;
}

// Gelen string komutlarini (MODEL, STREAM, STOP) yonet
void process_command(string cmd) {
    if (cmd.find("MODEL:") == 0) {
        string filepath = cmd.substr(6);
        vector<float> floats;
        
        if (filepath.find(".bin") != string::npos) {
            ifstream file(filepath, ios::binary);
            if (file) {
                float val;
                while (file.read(reinterpret_cast<char*>(&val), sizeof(float))) {
                    floats.push_back(val);
                }
            }
        } else {
            ifstream file(filepath);
            if (file) {
                string word;
                while (file >> word) {
                    if (word.back() == ',') word.pop_back();
                    try { floats.push_back(stof(word)); } catch (...) {}
                }
            }
        }

        if (floats.empty()) {
            send_tcp_message("STATUS:ERROR_EMPTY_MODEL");
            return;
        }

        vector<uint8_t> payload;
        payload.push_back(0x01);
        payload.push_back(0x00);
        payload.push_back(0x00);
        payload.push_back(0x00);

        const uint8_t* float_bytes = reinterpret_cast<const uint8_t*>(floats.data());
        payload.insert(payload.end(), float_bytes, float_bytes + (floats.size() * sizeof(float)));

        sendto(udp_sock, reinterpret_cast<const char*>(payload.data()), payload.size(), 0, (sockaddr*)&board_addr, sizeof(board_addr));

        char rx_buf[64];
        sockaddr_in from;
        int fromlen = sizeof(from);
        int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr*)&from, &fromlen);

        if (n > 0 && static_cast<uint8_t>(rx_buf[0]) == 0xFF) {
            send_tcp_message("STATUS:MODEL_OK");
        } else {
            send_tcp_message("STATUS:TIMEOUT");
        }
    } 
    else if (cmd.find("STREAM:") == 0) {
        // STREAM:<csv_yolu>:<gecikme_ms>
        string args = cmd.substr(7);
        size_t last_colon = args.find_last_of(':');
        if (last_colon != string::npos) {
            string filepath = args.substr(0, last_colon);
            int delay_ms = 0;
            try { delay_ms = stoi(args.substr(last_colon + 1)); } catch (...) {}

            if (is_streaming) {
                is_streaming = false;
                if (stream_thread.joinable()) stream_thread.join();
            }

            is_streaming = true;
            stream_thread = thread(stream_task, filepath, delay_ms);
        }
    }
    else if (cmd == "STOP") {
        if (is_streaming) {
            is_streaming = false;
            if (stream_thread.joinable()) stream_thread.join();
            send_tcp_message("STATUS:STOPPED");
        }
    }
    else if (cmd == "TEST_MODEL") {
        // C++ kodu ilk basta ping atarak FPGA baglantisini kontrol etsin
        send_tcp_message("STATUS:PING_CHECKING");
        int ping_res = system("ping -n 1 -w 500 192.168.1.10 > nul");
        if (ping_res != 0) {
            send_tcp_message("STATUS:WARNING_PING_FAILED_BUT_TRYING");
        } else {
            send_tcp_message("STATUS:PING_OK_SENDING_MODEL");
        }

        vector<float> floats(6819); // Cok Onemli: Zynq 6819 float bekliyor (Aksi takdirde Data Abort)
        random_device rd;
        mt19937 mt(rd());
        uniform_real_distribution<float> dist(-0.5f, 0.5f);
        for(auto& f : floats) f = dist(mt);

        vector<uint8_t> payload;
        payload.push_back(0x01);
        payload.push_back(0x00);
        payload.push_back(0x00);
        payload.push_back(0x00);

        const uint8_t* float_bytes = reinterpret_cast<const uint8_t*>(floats.data());
        payload.insert(payload.end(), float_bytes, float_bytes + (floats.size() * sizeof(float)));

        sendto(udp_sock, reinterpret_cast<const char*>(payload.data()), payload.size(), 0, (sockaddr*)&board_addr, sizeof(board_addr));

        char rx_buf[64];
        sockaddr_in from;
        int fromlen = sizeof(from);
        int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr*)&from, &fromlen);

        if (n > 0 && static_cast<uint8_t>(rx_buf[0]) == 0xFF) {
            send_tcp_message("STATUS:MODEL_OK");
        } else {
            send_tcp_message("STATUS:TIMEOUT");
        }
    }
    else if (cmd.find("TEST_STREAM:") == 0) {
        string args = cmd.substr(12);
        int delay_ms = 0;
        try { delay_ms = stoi(args); } catch (...) {}

        if (is_streaming) {
            is_streaming = false;
            if (stream_thread.joinable()) stream_thread.join();
        }

        is_streaming = true;
        stream_thread = thread(test_stream_task, delay_ms);
    }
}

int main() {
    timeBeginPeriod(1); // Windows Scheduler hizlandirmasi (1ms)
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return 1;

    // UDP Soketi (HFT Veri Gönderimi İçin)
    udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    DWORD timeout = UDP_TIMEOUT_MS;
    setsockopt(udp_sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout, sizeof(timeout));

    memset(&board_addr, 0, sizeof(board_addr));
    board_addr.sin_family = AF_INET;
    board_addr.sin_addr.s_addr = inet_addr(FPGA_IP);
    board_addr.sin_port = htons(FPGA_PORT);

    // TCP Soketi (Python IPC İletişimi İçin Daemon)
    SOCKET server_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    
    // Uygulama kapanip acildiginda portu hizlica yeniden baglayabilmek icin
    int opt = 1;
    setsockopt(server_sock, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));

    sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    server_addr.sin_port = htons(IPC_PORT);

    if (bind(server_sock, (sockaddr*)&server_addr, sizeof(server_addr)) == SOCKET_ERROR) {
        cout << "TCP Port " << IPC_PORT << " zaten kullanimda! Baska bir hft_engine arkada acik." << endl;
        closesocket(server_sock);
        WSACleanup();
        return 1;
    }

    listen(server_sock, 1);
    cout << "HFT Engine Hazir (Daemon). Port " << IPC_PORT << " uzerinden dinleniyor..." << endl;

    // Python arayuzunden gelen baglantilari bekle
    while (true) {
        sockaddr_in client_addr;
        int client_len = sizeof(client_addr);
        tcp_client_sock = accept(server_sock, (sockaddr*)&client_addr, &client_len);
        
        if (tcp_client_sock != INVALID_SOCKET) {
            cout << "[DAEMON] Python Frontend baglandi." << endl;
            char buffer[1024];
            
            while (true) {
                int bytes_received = recv(tcp_client_sock, buffer, sizeof(buffer) - 1, 0);
                if (bytes_received <= 0) {
                    cout << "[DAEMON] Baglanti koptu." << endl;
                    break;
                }
                buffer[bytes_received] = '\0';
                
                stringstream ss(buffer);
                string cmd;
                while (getline(ss, cmd, '\n')) {
                    if (!cmd.empty() && cmd.back() == '\r') cmd.pop_back();
                    if (!cmd.empty()) {
                        process_command(cmd);
                    }
                }
            }
            
            is_streaming = false;
            if (stream_thread.joinable()) stream_thread.join();
            
            {
                lock_guard<mutex> lock(tcp_mutex);
                closesocket(tcp_client_sock);
                tcp_client_sock = INVALID_SOCKET;
            }
        }
    }

    closesocket(server_sock);
    closesocket(udp_sock);
    WSACleanup();
    timeEndPeriod(1);
    return 0;
}
