#ifndef MLP_WEIGHT_LOADER_H
#define MLP_WEIGHT_LOADER_H

#include "mlp_driver.h"
#include "xil_io.h"
#include <math.h>

/* Q8.8 formati icin yardimci fonksiyon (Kayan nokta -> Q8.8) */
static inline int float_to_q88(float val) { return (int)(val * 256.0f); }

/**
 * @brief Tek bir katmana ait agirlik ve bias'lari Pipelined SIMD donanima
 * yukler.
 *
 * @param base_addr   Bu katmanin BRAM'deki baslangic satir adresi. Islem
 * sonunda bir sonraki katman icin guncellenir.
 * @param num_neurons Bu katmandaki noron sayisi.
 * @param num_inputs  Bu katmana gelen giris sayisi (max 64).
 * @param W_Layer     Agirlik matrisi (1D flatten edilmis: [num_neurons *
 * num_inputs]).
 * @param Bias_Layer  Bias dizisi (Boyut: num_neurons).
 */
static inline void load_layer_to_hw(int *base_addr, int num_neurons,
                                    int num_inputs, const float *W_Layer,
                                    const float *Bias_Layer) {
  // Her saat vurusunda 3 noron islendigi icin satir sayisini 3'e bolup yukari
  // yuvarliyoruz.
  int num_words = (int)ceil(num_neurons / 3.0);

  for (int k = 0; k < num_words; k++) {
    int word_addr = *base_addr + k;

    for (int n = 0; n < 3; n++) {
      int actual_neuron_idx = (k * 3) + n;

      if (actual_neuron_idx >= num_neurons) {
        // Bu donanim slotu bostur (Zero-padding)
        for (int i = 0; i < 64; i++) {
          int bram_idx = (n * 64) + i;
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4), 0x0000);
        }
      } else {
        // Gercek agirliklari bas
        for (int i = 0; i < num_inputs; i++) {
          int bram_idx = (n * 64) + i;
          int weight_val =
              float_to_q88(W_Layer[actual_neuron_idx * num_inputs + i]);
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4),
                        weight_val);
        }

        // 64'ten az giris varsa geri kalani 0 ile doldur (Zero-padding for
        // inputs)
        for (int i = num_inputs; i < 64; i++) {
          int bram_idx = (n * 64) + i;
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4), 0x0000);
        }
      }

      // Bias degerini bas
      int bias_val = 0;
      if (actual_neuron_idx < num_neurons && Bias_Layer != NULL) {
        bias_val = float_to_q88(Bias_Layer[actual_neuron_idx]);
      }

      // Bias BRAM indeksleri: 192, 193, 194
      int bias_bram_idx = 192 + n;
      mlp_write_reg(0x20000 + (bias_bram_idx * 512) + (word_addr * 4),
                    bias_val);
    }
  }

  // Bir sonraki katman icin base_addr degiskenini ileri al
  *base_addr += num_words;
}

/**
 * @brief Tum yapay sinir agini (4 katmanli ornek) yeni donanima yukler.
 *
 * Eger projede agirliklarin kayitli oldugu dizilerin (W1_arr, B1_arr, vb.)
 * isimleri farkliysa asagidaki isimlendirmeleri degistirebilirsiniz veya
 * bu fonksiyonu direkt cagirabilirsiniz.
 */
static inline void load_weights_to_hw(const float *W1, const float *B1, int n1,
                                      int i1, const float *W2, const float *B2,
                                      int n2, int i2, const float *W3,
                                      const float *B3, int n3, int i3,
                                      const float *W4, const float *B4, int n4,
                                      int i4) {
  int current_base_addr = 0;

  // 1. Katman
  if (W1)
    load_layer_to_hw(&current_base_addr, n1, i1, W1, B1);
  // 2. Katman
  if (W2)
    load_layer_to_hw(&current_base_addr, n2, i2, W2, B2);
  // 3. Katman
  if (W3)
    load_layer_to_hw(&current_base_addr, n3, i3, W3, B3);
  // 4. Katman
  if (W4)
    load_layer_to_hw(&current_base_addr, n4, i4, W4, B4);
}

/**
 * @brief Basit bir makro ile eger katmanlariniz (64, 32, 16, 3) seklinde sabit
 * ise: load_default_network(W1, B1, W2, B2, W3, B3, W4, B4);
 */
static inline void load_default_network(const float *W1, const float *B1,
                                        const float *W2, const float *B2,
                                        const float *W3, const float *B3,
                                        const float *W4, const float *B4) {
  load_weights_to_hw(W1, B1, 64,
                     64, // Katman 1: 64 Noron, 64 Giris (Ornegin
                         // MLP_FEATURE_COUNT=40 olsa da 64 pad edilebilir)
                     W2, B2, 32, 64, // Katman 2: 32 Noron, 64 Giris
                     W3, B3, 16, 32, // Katman 3: 16 Noron, 32 Giris
                     W4, B4, 3, 16   // Katman 4:  3 Noron, 16 Giris
  );
}

#endif // MLP_WEIGHT_LOADER_H
