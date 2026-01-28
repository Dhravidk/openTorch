```cpp
// [START kernel.cu]
#include <cstdint>

template <typename scalar_t>
__global__ void linear_kernel(
    int64_t batch_size,
    int64_t out_features,
    int64_t in_features,
    const scalar_t* __restrict__ input,
    const scalar_t* __restrict__ weight,
    const scalar_t* __restrict__ bias,
    scalar_t* __restrict__ output) {
  int64_t row = blockIdx.y * blockDim.y + threadIdx.y;
  int64_t col = blockIdx.x * blockDim.x + threadIdx.x;

  if (row >= batch_size || col >= out_features) {
    return;
  }

  const scalar_t* input_row = input + row * in_features;
  const scalar_t* weight_row = weight + col * in_features;
  scalar_t acc = scalar_t(0);
  for (int64_t k = 0; k < in_features; ++k) {
    acc += input_row[k] * weight_row[k];
  }
  acc += bias[col];
  output[row * out_features + col] = acc;
}

#include <cuda_runtime.h>
#include <torch/extension.h>

#define CUDA_CHECK(expr)                                                        \
  do {                                                                          \
    cudaError_t err = (expr);                                                   \
    TORCH_CHECK(err == cudaSuccess, "CUDA error: ", cudaGetErrorString(err));