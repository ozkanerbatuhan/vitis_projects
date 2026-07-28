#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

// # Build
// g++ -O2 -o hft_engine_linux hft_engine_linux.cpp -lpthread
// # Run
// ./hft_engine_linux

// POSIX Sockets
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define FPGA_IP "192.168.1.10"
#define FPGA_PORT 7000
#define IPC_PORT 5005
#define UDP_TIMEOUT_MS 2000

// FPGA fixed architecture (must match the Vitis firmware EXACTLY):
//   W1 64x64, B1 64 | W2 32x64, B2 32 | W3 16x32, B3 16 | W4 3x16, B4 3
// Total = 6819 float32 values.
#define FPGA_MODEL_FLOATS 6819

#define LOG_FILENAME "execution_log_linux.csv"

/* ── Bit-exact dogrulama destegi ────────────────────────────────────────────
 * 1) f2q88(): float -> Q8.8 donusumu. Onceki kod static_cast<int16_t> ile
 *    tasan degerleri SESSIZCE SARMALIYORDU (ornek: BTC fiyati 76834.36 ->
 *    x256 = 19,669,596 -> int16'da 8796 = "price mod 256"). Artik RTL'in
 *    kendi saturate() fonksiyonu gibi doyuruyor.
 * 2) log_filename(): HFT_LOG ortam degiskeni ile kosum basina ayri log
 *    dosyasi. Motor log'u ios::app ile aciyor; ayni dosyaya tekrar yazmak
 *    satir hizalamasini bozar ve dogrulamayi anlamsiz kilar.
 *      HFT_LOG=log_model_new.csv ./hft_engine_linux
 * ─────────────────────────────────────────────────────────────────────────── */
static inline int16_t f2q88(float v) {
  if (!std::isfinite(v))
    return 0;
  long x = lrintf(v * 256.0f);
  if (x > 32767)
    x = 32767;
  if (x < -32768)
    x = -32768;
  return (int16_t)x;
}

static const char *log_filename() {
  const char *e = getenv("HFT_LOG");
  return (e && *e) ? e : LOG_FILENAME;
}

using namespace std;

// Global thread & socket state
atomic<bool> is_streaming{false};
thread stream_thread;
int udp_sock = -1;
int tcp_client_sock = -1;
sockaddr_in board_addr;
mutex tcp_mutex;

// High-resolution clock (CLOCK_MONOTONIC, nanoseconds)
static inline uint64_t now_ns() {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

// Send live status/latency back to the Python frontend over TCP
void send_tcp_message(const string &msg) {
  lock_guard<mutex> lock(tcp_mutex);
  if (tcp_client_sock >= 0) {
    string packet = msg + "\n";
    send(tcp_client_sock, packet.c_str(), packet.length(), 0);
  }
}

// Background worker thread that streams live data from a file
void stream_task(string filepath, int delay_ms) {
  ifstream file(filepath);
  if (!file) {
    send_tcp_message("STATUS:ERROR_FILE");
    is_streaming = false;
    return;
  }

  ofstream log_file(LOG_FILENAME, ios::app);
  if (log_file.tellp() == 0) {
    // stage tick columns are filled only when the firmware is built with
    // ENABLE_STAGE_TIMING (21-byte reply); otherwise left empty
    log_file << "Timestamp_us,Latency_us,Result,"
                "recv_ticks,parse_ticks,dma_ticks,pl_ticks,read_ticks\n";
  }

  string line;

  while (is_streaming && getline(file, line)) {
    if (line.empty())
      continue;
    // Strip trailing \r coming from Windows-formatted files
    if (!line.empty() && line.back() == '\r')
      line.pop_back();

    vector<int16_t> q88_features;
    stringstream ss(line);
    string token;

    // Parse comma-separated values
    while (getline(ss, token, ',')) {
      try {
        float val = stof(token);
        q88_features.push_back(f2q88(val));
      } catch (...) {
      }
    }

    // Zero-pad / truncate to 64 features
    if (q88_features.size() < 64)
      q88_features.resize(64, 0);
    else if (q88_features.size() > 64)
      q88_features.resize(64);

    // Packet (0x02 header + padding)
    vector<uint8_t> payload;
    payload.push_back(0x02);
    payload.push_back(0x00);
    payload.push_back(0x00);
    payload.push_back(0x00);

    const uint8_t *q88_bytes =
        reinterpret_cast<const uint8_t *>(q88_features.data());
    payload.insert(payload.end(), q88_bytes,
                   q88_bytes + (64 * sizeof(int16_t)));

    // HFT UDP signal send + microsecond latency measurement
    uint64_t t0 = now_ns();
    sendto(udp_sock, payload.data(), payload.size(), 0, (sockaddr *)&board_addr,
           sizeof(board_addr));

    char rx_buf[64];
    sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr *)&from,
                     &fromlen);
    uint64_t t1 = now_ns();

    double latency_us = (double)(t1 - t0) / 1000.0;
    auto now_us = chrono::duration_cast<chrono::microseconds>(
                      chrono::system_clock::now().time_since_epoch())
                      .count();

    if (n > 0) {
      uint8_t res = static_cast<uint8_t>(rx_buf[0]);
      string result_str;
      /* Firmware (main.c) encoding: 0=SELL, 1=HOLD, 2=BUY */
      if (res == 0)
        result_str = "SELL";
      else if (res == 1)
        result_str = "HOLD";
      else if (res == 2)
        result_str = "BUY";
      else if (res == 0xDD) {
        rx_buf[n] = '\0';
        result_str = string(rx_buf + 1);
      } else
        result_str = "UNKNOWN";

      // IPC: forward result to the Python client
      ostringstream msg;
      msg << "STATUS:" << result_str << "|LATENCY:" << fixed << setprecision(2)
          << latency_us;
      send_tcp_message(msg.str());

      // Write to disk and flush immediately
      log_file << now_us << "," << fixed << setprecision(2) << latency_us << ","
               << result_str;
      // ENABLE_STAGE_TIMING firmware: reply = [decision][5x u32 LE ticks]
      if (n >= 21) {
        uint32_t stg[5];
        memcpy(stg, rx_buf + 1, sizeof(stg));
        for (int k = 0; k < 5; k++)
          log_file << "," << stg[k];
      } else {
        log_file << ",,,,,";
      }
      /* Firmware yamasi: reply = [karar][5x u32 tick][3x s16 logit] = 27 bayt */
      if (n >= 27) {
        int16_t outs[3];
        memcpy(outs, rx_buf + 21, sizeof(outs));
        for (int k = 0; k < 3; k++)
          log_file << "," << outs[k];
      } else {
        log_file << ",,,";
      }
      log_file << "\n";
      log_file.flush();
    } else {
      send_tcp_message("STATUS:TIMEOUT");
      log_file << now_us << ",TIMEOUT,TIMEOUT\n";
      log_file.flush();
    }

    // Stream pacing delay
    if (delay_ms > 0 && is_streaming) {
      this_thread::sleep_for(chrono::milliseconds(delay_ms));
    }
  }

  if (is_streaming) {
    send_tcp_message("STATUS:STREAM_FINISHED");
  }
  is_streaming = false;
}

// Worker thread that generates random data for test streaming
void test_stream_task(int delay_ms) {
  ofstream log_file(log_filename(), ios::app);
  if (log_file.tellp() == 0) {
    log_file << "Timestamp_us,Latency_us,Result,"
                "recv_ticks,parse_ticks,dma_ticks,pl_ticks,read_ticks,"
                "out0,out1,out2\n";
  }

  random_device rd;
  mt19937 mt(rd());
  uniform_real_distribution<float> dist(-1.0f, 1.0f);

  while (is_streaming) {
    vector<int16_t> q88_features(64);
    for (int i = 0; i < 64; ++i) {
      q88_features[i] = f2q88(dist(mt));
    }

    vector<uint8_t> payload;
    payload.push_back(0x02);
    payload.push_back(0x00);
    payload.push_back(0x00);
    payload.push_back(0x00);

    const uint8_t *q88_bytes =
        reinterpret_cast<const uint8_t *>(q88_features.data());
    payload.insert(payload.end(), q88_bytes,
                   q88_bytes + (64 * sizeof(int16_t)));

    uint64_t t0 = now_ns();
    sendto(udp_sock, payload.data(), payload.size(), 0, (sockaddr *)&board_addr,
           sizeof(board_addr));

    char rx_buf[64];
    sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr *)&from,
                     &fromlen);
    uint64_t t1 = now_ns();

    double latency_us = (double)(t1 - t0) / 1000.0;
    auto now_us = chrono::duration_cast<chrono::microseconds>(
                      chrono::system_clock::now().time_since_epoch())
                      .count();

    if (n > 0) {
      uint8_t res = static_cast<uint8_t>(rx_buf[0]);
      string result_str;
      /* Firmware (main.c) encoding: 0=SELL, 1=HOLD, 2=BUY */
      if (res == 0)
        result_str = "SELL";
      else if (res == 1)
        result_str = "HOLD";
      else if (res == 2)
        result_str = "BUY";
      else if (res == 0xDD) {
        rx_buf[n] = '\0';
        result_str = string(rx_buf + 1);
      } else
        result_str = "UNKNOWN";

      ostringstream msg;
      msg << "STATUS:" << result_str << "|LATENCY:" << fixed << setprecision(2)
          << latency_us;
      send_tcp_message(msg.str());

      log_file << now_us << "," << fixed << setprecision(2) << latency_us << ","
               << result_str;
      if (n >= 21) {
        uint32_t stg[5];
        memcpy(stg, rx_buf + 1, sizeof(stg));
        for (int k = 0; k < 5; k++)
          log_file << "," << stg[k];
      } else {
        log_file << ",,,,,";
      }
      /* Firmware yamasi: reply = [karar][5x u32 tick][3x s16 logit] = 27 bayt */
      if (n >= 27) {
        int16_t outs[3];
        memcpy(outs, rx_buf + 21, sizeof(outs));
        for (int k = 0; k < 3; k++)
          log_file << "," << outs[k];
      } else {
        log_file << ",,,";
      }
      log_file << "\n";
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

// Handle incoming string commands (MODEL, STREAM, STOP, ...)
void process_command(string cmd) {
  if (cmd.find("MODEL:") == 0) {
    string filepath = cmd.substr(6);
    vector<float> floats;

    if (filepath.find(".bin") != string::npos) {
      ifstream file(filepath, ios::binary);
      if (file) {
        float val;
        while (file.read(reinterpret_cast<char *>(&val), sizeof(float))) {
          floats.push_back(val);
        }
      }
    } else {
      ifstream file(filepath);
      if (file) {
        string word;
        while (file >> word) {
          if (word.back() == ',')
            word.pop_back();
          try {
            floats.push_back(stof(word));
          } catch (...) {
          }
        }
      }
    }

    if (floats.empty()) {
      send_tcp_message("STATUS:ERROR_EMPTY_MODEL");
      return;
    }

    // Sanity check against the fixed FPGA template size
    if (floats.size() != FPGA_MODEL_FLOATS) {
      cout << "[WARN] Model has " << floats.size() << " floats, expected "
           << FPGA_MODEL_FLOATS << ". Sending anyway." << endl;
    }

    vector<uint8_t> payload;
    payload.push_back(0x01);
    payload.push_back(0x00);
    payload.push_back(0x00);
    payload.push_back(0x00);

    const uint8_t *float_bytes =
        reinterpret_cast<const uint8_t *>(floats.data());
    payload.insert(payload.end(), float_bytes,
                   float_bytes + (floats.size() * sizeof(float)));

    sendto(udp_sock, payload.data(), payload.size(), 0, (sockaddr *)&board_addr,
           sizeof(board_addr));

    char rx_buf[64];
    sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr *)&from,
                     &fromlen);

    if (n > 0 && static_cast<uint8_t>(rx_buf[0]) == 0xFF) {
      send_tcp_message("STATUS:MODEL_OK");
    } else {
      send_tcp_message("STATUS:TIMEOUT");
    }
  } else if (cmd.find("STREAM:") == 0) {
    // STREAM:<csv_path>:<delay_ms>
    string args = cmd.substr(7);
    size_t last_colon = args.find_last_of(':');
    if (last_colon != string::npos) {
      string filepath = args.substr(0, last_colon);
      int delay_ms = 0;
      try {
        delay_ms = stoi(args.substr(last_colon + 1));
      } catch (...) {
      }

      if (is_streaming) {
        is_streaming = false;
        if (stream_thread.joinable())
          stream_thread.join();
      }

      is_streaming = true;
      stream_thread = thread(stream_task, filepath, delay_ms);
    }
  } else if (cmd == "STOP") {
    if (is_streaming) {
      is_streaming = false;
      if (stream_thread.joinable())
        stream_thread.join();
      send_tcp_message("STATUS:STOPPED");
    }
  } else if (cmd == "TEST_MODEL") {
    // Connectivity check (Linux)
    send_tcp_message("STATUS:PING_CHECKING");
    int ping_res = system("ping -c 1 -W 1 192.168.1.10 > /dev/null 2>&1");
    if (ping_res != 0) {
      send_tcp_message("STATUS:WARNING_PING_FAILED_BUT_TRYING");
    } else {
      send_tcp_message("STATUS:PING_OK_SENDING_MODEL");
    }

    vector<float> floats(FPGA_MODEL_FLOATS);
    random_device rd;
    mt19937 mt(rd());
    uniform_real_distribution<float> dist(-0.5f, 0.5f);
    for (auto &f : floats)
      f = dist(mt);

    vector<uint8_t> payload;
    payload.push_back(0x01);
    payload.push_back(0x00);
    payload.push_back(0x00);
    payload.push_back(0x00);

    const uint8_t *float_bytes =
        reinterpret_cast<const uint8_t *>(floats.data());
    payload.insert(payload.end(), float_bytes,
                   float_bytes + (floats.size() * sizeof(float)));

    sendto(udp_sock, payload.data(), payload.size(), 0, (sockaddr *)&board_addr,
           sizeof(board_addr));

    char rx_buf[64];
    sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    int n = recvfrom(udp_sock, rx_buf, sizeof(rx_buf), 0, (sockaddr *)&from,
                     &fromlen);

    if (n > 0 && static_cast<uint8_t>(rx_buf[0]) == 0xFF) {
      send_tcp_message("STATUS:MODEL_OK");
    } else {
      send_tcp_message("STATUS:TIMEOUT");
    }
  } else if (cmd.find("TEST_STREAM:") == 0) {
    string args = cmd.substr(12);
    int delay_ms = 0;
    try {
      delay_ms = stoi(args);
    } catch (...) {
    }

    if (is_streaming) {
      is_streaming = false;
      if (stream_thread.joinable())
        stream_thread.join();
    }

    is_streaming = true;
    stream_thread = thread(test_stream_task, delay_ms);
  }
}

int main() {
  // UDP socket (for HFT data transmission)
  udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (udp_sock < 0) {
    cerr << "Failed to create UDP socket!" << endl;
    return 1;
  }

  // Receive timeout (Linux: struct timeval)
  struct timeval tv;
  tv.tv_sec = UDP_TIMEOUT_MS / 1000;
  tv.tv_usec = (UDP_TIMEOUT_MS % 1000) * 1000;
  setsockopt(udp_sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

  memset(&board_addr, 0, sizeof(board_addr));
  board_addr.sin_family = AF_INET;
  board_addr.sin_addr.s_addr = inet_addr(FPGA_IP);
  board_addr.sin_port = htons(FPGA_PORT);

  // TCP socket (daemon for Python IPC communication)
  int server_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (server_sock < 0) {
    cerr << "Failed to create TCP socket!" << endl;
    close(udp_sock);
    return 1;
  }

  // Allow quick rebind of the port after restart
  int opt = 1;
  setsockopt(server_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

  sockaddr_in server_addr;
  memset(&server_addr, 0, sizeof(server_addr));
  server_addr.sin_family = AF_INET;
  server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
  server_addr.sin_port = htons(IPC_PORT);

  if (bind(server_sock, (sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
    cout << "TCP port " << IPC_PORT
         << " is already in use! Another hft_engine is running." << endl;
    close(server_sock);
    close(udp_sock);
    return 1;
  }

  listen(server_sock, 1);
  cout << "HFT Engine ready (Linux daemon). Listening on port " << IPC_PORT
       << "..." << endl;

  // Wait for connections from the Python frontend
  while (true) {
    sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    tcp_client_sock =
        accept(server_sock, (sockaddr *)&client_addr, &client_len);

    if (tcp_client_sock >= 0) {
      cout << "[DAEMON] Python frontend connected." << endl;
      char buffer[1024];

      while (true) {
        int bytes_received =
            recv(tcp_client_sock, buffer, sizeof(buffer) - 1, 0);
        if (bytes_received <= 0) {
          cout << "[DAEMON] Connection closed." << endl;
          break;
        }
        buffer[bytes_received] = '\0';

        stringstream ss(buffer);
        string cmd;
        while (getline(ss, cmd, '\n')) {
          if (!cmd.empty() && cmd.back() == '\r')
            cmd.pop_back();
          if (!cmd.empty()) {
            process_command(cmd);
          }
        }
      }

      is_streaming = false;
      if (stream_thread.joinable())
        stream_thread.join();

      {
        lock_guard<mutex> lock(tcp_mutex);
        close(tcp_client_sock);
        tcp_client_sock = -1;
      }
    }
  }

  close(server_sock);
  close(udp_sock);
  return 0;
}
