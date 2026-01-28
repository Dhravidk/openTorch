// [START kernel.cu]
template <typename scalar_t>
__global__ void relu_kernel(
    scalar_t* output,
    const scalar_t* input,
    int64_t numel) {
  int64_t idx = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  int64_t stride = blockDim.x * static_cast<int64_t>(gridDim.x);
  for (; idx < numel; idx += stride) {
    scalar_t val = input[idx];
    scalar_t zero = static_cast<scalar_t>(0);
    output[idx] = val > zero ? val : zero;
  }
}

#include <cuda.h>
#include <cuda_runtime.h>
#include <torch/extension.h>

#define CUDA_CHECK(expr)                                            \
  do {                                                              \
    cudaError_t err = expr;                                         \
    if (err != cudaSuccess) {                                       \
      TORCH_CHECK(false, "CUDA error: ", cudaGetErrorString(err));  \
    }                                                               \
  } while (0)

torch::Tensor launch(const torch::Tensor& input, bool inplace) {
  TORCH_CHECK(input.is_cuda(), "input must be a CUDA tensor");
  TORCH_CHECK(input.is_contiguous(), "input must be contiguous");
  const int64_t numel = input.numel();

  torch::Tensor output = inplace ? input : torch::empty_like(input);
  if (numel == 0) {
    return output;
  }

  const int threads = 256;
  const int blocks = static_cast<int>((numel + threads - 1) / threads);

  AT_DISPATCH_FLOATING_TYPES_AND_HALF(
      input.scalar_type(), "relu_cuda", [&]() {
        relu_kernel<scalar_t><<<blocks, threads>>>(
            output.data_ptr<scalar_t>(),
            input.data_ptr<scalar_t>(),
            numel);
      });

  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());

  return output;
}

// [END kernel.cu]