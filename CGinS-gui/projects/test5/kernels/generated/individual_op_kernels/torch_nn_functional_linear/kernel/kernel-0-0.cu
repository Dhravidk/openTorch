```cpp
// [START kernel.cu]
template <typename scalar_t>
__global__ void linear_kernel(
    bool has_bias,
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

  scalar_t