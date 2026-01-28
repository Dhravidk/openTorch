// [START kernel.cu]
#include <cuda.h>
#include <cuda_runtime.h>

template <typename T>
__device__ __forceinline__ T zero_val();
template <>
__device__ __forceinline__ float zero_val<float>() { return 0.0f; }
template <>
__device__ __forceinline__ double zero_val<double>() { return 0.0; }
template <>
__device__ __forceinline__ __half zero_val<__half>() { return __float2half(0.0f); }

template <typename T>
__device__ __forceinline__ float to_float(T v) { return static_cast<float>(v); }
template <>
__device__ __forceinline__ float to_float<__half>(__half v) { return __half2float(v); }

template <typename T>
__device__ __forceinline__ T from_float(float v) { return static_cast<T>(v); }
template <>
__device__ __forceinline__ __half from_float<__half>(float v) { return __float2half(v); }

template <typename scalar_t>
__global__ void linear_1x1024_w10x1024_bias10_kernel(
    scalar_t* __restrict__ out,         // [1, 10]
    const scalar_t* __restrict__ inp,   // [1, 1024]
    const scalar_t* __restrict__ w,     // [10, 1024]
    const scalar_t* __restrict__ b      // [10]
) {
    // One block handles one or more output columns (0..9)
    // Each block computes one output element out[0, j]
    int64_t j = (int64_t)blockIdx.x;
    if (j >= 10) return;

    // Parallel reduction over K=1024
    float acc = 0.0f;
    for (int64_t k = (int64_t)threadIdx.x; k < 1024; k += (int64_t)blockDim.x) {
        float a = to_float<scalar_t>(inp[k]);           // inp[0, k]
        float ww = to_float<scalar_t>(w[j * 1024 + k]); // w[j, k]
        acc += a * ww;
    }

    // Block reduction (sum)
    __shared__ float smem[256]; // threads fixed to 256 below
    smem[threadIdx.x] = acc;
    __syncthreads();

    for (int stride = 128; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) smem[threadIdx.x] += smem[threadIdx.x + stride];
        __syncthreads();
    }

    if (threadIdx.x == 0) {
        float bias = to_float<scalar_t>(b[j]);
        float y = smem[0] + bias;
        out[j] = from_float<scalar_t>(y); // out[0, j] contiguous is just out[j]
    }
}

#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>

#define CUDA_CHECK(err) TORCH_CHECK((err) == cudaSuccess, "CUDA error: ", cudaGetErrorString(err))

torch::Tensor launch(torch::Tensor arg0, torch::Tensor arg1, torch::Tensor arg2) {
    // arg0: input [1, 1024]
    // arg1: weight [10, 1024]
    // arg2: bias [10]
    TORCH_CHECK(arg0.is_cuda(), "arg0 must be a CUDA tensor");
    TORCH_CHECK(arg1.is_cuda(), "arg1 must be a CUDA tensor");
    TORCH_CHECK(arg2.is_cuda(), "arg2 must be a CUDA tensor");

    TORCH_CHECK(arg0.is_contiguous(), "arg0 must be contiguous");
    TORCH_CHECK(arg1.is_contiguous(), "arg1 must be contiguous");
    TORCH_CHECK(arg2.is_contiguous(), "arg2 must be contiguous");

    TORCH_CHECK(arg0.dim() == 2, "arg0 must be rank-2 [1, 1024]");
    TORCH_CHECK(arg1.dim() == 2, "arg1 must be rank-2 [10, 1024]");
    TORCH_CHECK(arg2.dim() == 1, "arg2 must be rank-1 [10]");

    TORCH_CHECK(arg0.size(0) == 1 && arg0.size(1) == 1024, "arg0 must have shape [1, 1024]");
    TORCH_CHECK(arg1.size(0) == 10 && arg1.size(1) == 1024, "arg1 must have shape [10, 1024]");
    TORCH_CHECK(arg2.size(0) == 10, "arg2 must have shape [10]");

    TORCH_CHECK(arg0.scalar_type() == arg1.scalar_type() && arg0.scalar_type() == arg2.scalar_type(),
                "arg0, arg1, arg2 must have the same dtype");
    TORCH_CHECK(arg0.device().index() == arg1.device().index() && arg0.device().index() == arg2.device().index(),
                "arg0, arg1, arg2 must be on the same CUDA device");

    auto out = torch::empty({1, 10}, torch::TensorOptions().dtype(arg0.dtype()).device(arg0.device()));

    const int threads = 256;
    const int blocks = 10;

    cudaStream_t stream = at::cuda::getDefaultCUDAStream();

    AT_DISPATCH_FLOATING_TYPES_AND_HALF(arg0.scalar_type(), "linear_1x1024_w10x1024_bias10", [&] {
        using scalar_t_ = scalar_t;
        linear_1x1024_w10x1024_bias10_kernel<scalar_t_><<<blocks, threads, 0, stream>>>(
            (scalar_t_*)out.data_ptr<scalar_t_>(),
            (const scalar_t_*)arg0.data_ptr<scalar_t_>(),
            (const scalar_t_*)arg1.data_ptr<scalar_t_>(),
            (const scalar_t_*)arg2.data_ptr<scalar_t_>()
        );
    });

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    return out;
}
// [END kernel.cu]