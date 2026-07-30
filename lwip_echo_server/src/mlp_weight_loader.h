#ifndef MLP_WEIGHT_LOADER_H
#define MLP_WEIGHT_LOADER_H

#include "mlp_driver.h"
#include "xil_io.h"
#include <math.h>

/* Float to Q8.8 conversion helper */
static inline int float_to_q88(float val) { return (int)(val * 256.0f); }

/**
 * @brief Load the weights and biases of one layer into the pipelined SIMD
 * hardware.
 *
 * @param base_addr   Starting BRAM row address for this layer. Advanced to
 * the next layer on return.
 * @param num_neurons Number of neurons in this layer.
 * @param num_inputs  Number of inputs to this layer (at most 64).
 * @param W_Layer     Weight matrix, flattened to [num_neurons *
 * num_inputs].
 * @param Bias_Layer  Bias array of length num_neurons.
 */
static inline void load_layer_to_hw(int *base_addr, int num_neurons,
                                    int num_inputs, const float *W_Layer,
                                    const float *Bias_Layer) {
  // Three neurons are processed per clock, so the row count is the neuron
  // count divided by three, rounded up.
  int num_words = (int)ceil(num_neurons / 3.0);

  for (int k = 0; k < num_words; k++) {
    int word_addr = *base_addr + k;

    for (int n = 0; n < 3; n++) {
      int actual_neuron_idx = (k * 3) + n;

      if (actual_neuron_idx >= num_neurons) {
        // This hardware slot is unused: zero-pad it
        for (int i = 0; i < 64; i++) {
          int bram_idx = (n * 64) + i;
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4), 0x0000);
        }
      } else {
        // Write the real weights
        for (int i = 0; i < num_inputs; i++) {
          int bram_idx = (n * 64) + i;
          int weight_val =
              float_to_q88(W_Layer[actual_neuron_idx * num_inputs + i]);
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4),
                        weight_val);
        }

        // Fewer than 64 inputs: zero-pad the remainder
        for (int i = num_inputs; i < 64; i++) {
          int bram_idx = (n * 64) + i;
          mlp_write_reg(0x20000 + (bram_idx * 512) + (word_addr * 4), 0x0000);
        }
      }

      // Write the bias
      int bias_val = 0;
      if (actual_neuron_idx < num_neurons && Bias_Layer != NULL) {
        bias_val = float_to_q88(Bias_Layer[actual_neuron_idx]);
      }

      // Bias BRAM indices: 192, 193, 194
      int bias_bram_idx = 192 + n;
      mlp_write_reg(0x20000 + (bias_bram_idx * 512) + (word_addr * 4),
                    bias_val);
    }
  }

  // Advance base_addr for the next layer
  *base_addr += num_words;
}

/**
 * @brief Load a whole four-layer network into the hardware.
 *
 * If the arrays holding the weights are named differently in your project,
 * either rename them below or call this function directly.
 */
static inline void load_weights_to_hw(const float *W1, const float *B1, int n1,
                                      int i1, const float *W2, const float *B2,
                                      int n2, int i2, const float *W3,
                                      const float *B3, int n3, int i3,
                                      const float *W4, const float *B4, int n4,
                                      int i4) {
  int current_base_addr = 0;

  // Layer 1
  if (W1)
    load_layer_to_hw(&current_base_addr, n1, i1, W1, B1);
  // Layer 2
  if (W2)
    load_layer_to_hw(&current_base_addr, n2, i2, W2, B2);
  // Layer 3
  if (W3)
    load_layer_to_hw(&current_base_addr, n3, i3, W3, B3);
  // Layer 4
  if (W4)
    load_layer_to_hw(&current_base_addr, n4, i4, W4, B4);
}

/**
 * @brief Convenience wrapper for the fixed (64, 32, 16, 3) shape:
 * load_default_network(W1, B1, W2, B2, W3, B3, W4, B4);
 */
static inline void load_default_network(const float *W1, const float *B1,
                                        const float *W2, const float *B2,
                                        const float *W3, const float *B3,
                                        const float *W4, const float *B4) {
  load_weights_to_hw(W1, B1, 64,
                     64, // Layer 1: 64 neurons, 64 inputs (even with
                         // MLP_FEATURE_COUNT=40 the input is padded to 64)
                     W2, B2, 32, 64, // Layer 2: 32 neurons, 64 inputs
                     W3, B3, 16, 32, // Layer 3: 16 neurons, 32 inputs
                     W4, B4, 3, 16   // Layer 4:  3 neurons, 16 inputs
  );
}

#endif // MLP_WEIGHT_LOADER_H
