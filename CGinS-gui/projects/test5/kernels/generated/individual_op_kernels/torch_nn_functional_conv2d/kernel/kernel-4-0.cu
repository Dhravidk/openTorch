// [START kernel.cu]
#include <cuda.h>
#include <cuda_runtime.h>

// ============ DEVICE CODE (CUDA kernels only) ============
template <typename scalar_t, typename acc_t>
__global__ void conv2d_nchw_forward_kernel(
    scalar_t* __restrict__ out,
    const scalar_t* __restrict__ inp,
    const scalar_t* __restrict__ w,
    const scalar_t* __restrict__ b, // may be nullptr
    int64_t N, int64_t C_in, int64_t H_in, int64_t W_in,
    int64_t C_out, int64_t K_h, int64_t K_w,
    int64_t H_out, int64_t W_out,
    int64_t stride_h, int64_t stride_w,
    int64_t pad_h, int64_t pad_w,
    int64_t dil_h, int64_t dil_w,
    int64_t groups,
    bool has_bias) {

  int64_t idx = (int64_t)blockIdx.x * (int64_t)blockDim.x + (int64_t)threadIdx.x;
  int64_t total = N * C_out * H_out * W_out;
  if (idx >= total) return;

  int64_t tmp = idx;
  int64_t ow = tmp % W_out; tmp /= W_out;
  int64_t oh = tmp % H_out; tmp /= H_out;
  int64_t oc = tmp % C_out; tmp /= C_out;
  int64_t n  = tmp;

  int64_t out_c_per_g = C_out / groups;
  int64_t in_c_per_g  = C_in / groups;
  int64_t g = oc / out_c_per_g;

  acc_t acc = (acc_t)0;
  if (has_bias) {
    acc = (acc_t)b[oc];
  }

  // w: [C_out, C_in/groups, K_h, K_w]
  const int64_t w_oc_base = ((oc * in_c_per_g) * K_h) * K_w;
  const int64_t in_c_start = g * in_c_per_g;

  for (int64_t icg = 0; icg < in_c_per_g; ++icg) {
    int64_t ic = in_c_start + icg;

    const int64_t inp_base = ((n * C_in + ic) * H_in) * W_in;
    const int64_t w_ic_base = w_oc_base + (icg * K_h) * K_w;

    for (int64_t kh = 0; kh < K_h; ++kh) {
      int64_t ih = oh * stride_h - pad_h + kh * dil_h;
      if ((uint64_t)ih >= (uint64_t)H_in) continue;

      for (int64_t kw = 0; kw < K_w; ++kw) {
        int64_t iw = ow * stride_w - pad_w + kw * dil_w;
        if ((uint64_t)iw >= (uint64_t)W_in) continue;

        acc_t x  = (acc_t)inp[inp_base + ih * W_in + iw];
        acc_t ww = (acc_t)w[w_ic_base + kh * K_w + kw];
        acc += x * ww;
      }
    }
  }

  out[idx] = (scalar_t)acc;
}

#include <torch/extension.h>
#include <ATen/ATen.h>
#include <ATen/Dispatch.h>
#include <ATen/cuda/CUDAContext.h>
#include <ATen/cuda/CUDAGuard.h>
#include <c10/util/Exception.h>

#include <vector>
#include <type_traits>
#include <cstdint>

#define CUDA_CHECK(err)                                                          \
  do {                                                                           \
    cudaError_t err__ = (err);                                                   \
    if (err__ != cudaSuccess) {                                                  \
      TORCH_CHECK(false, "CUDA error: ", cudaGetErrorString(err__));             \
    }                                                                            \
  } while (0)

static inline void get_2d_params(at::IntArrayRef v, int64_t def, int64_t& a, int64_t& b) {
  if (v.size() == 0) {
    a = def; b = def;
  } else if (v.size() == 1) {
    a = v[0]; b = v[0];
  } else {
    TORCH_CHECK(v.size() == 2, "expected IntArrayRef of size 1 or 2");
    a = v[0]; b = v[1];
  }
}

// ============ HOST CODE ============
torch::Tensor launch(
    torch::Tensor arg0,
    torch::Tensor arg1,
    c10::optional<torch::Tensor> arg2,
    at::IntArrayRef arg3,
    at::IntArrayRef arg4,
    at::IntArrayRef arg5,
    int64_t arg6) {

  TORCH_CHECK(arg0.defined() && arg1.defined(), "input and weight must be defined");
  TORCH_CHECK(arg0.is_cuda() && arg1.is_cuda(), "input and weight must be CUDA tensors");

  const at::cuda::CUDAGuard device_guard(arg0.device());

  if (!arg0.is_contiguous()) arg0 = arg0.contiguous();
  if (!arg1.is_contiguous()) arg1 = arg1.contiguous();

  TORCH_CHECK(arg0.scalar_type() == arg1.scalar_type(), "input and weight must have same dtype");
  TORCH_CHECK(arg0.dim() == 4, "input must be 4D (N,C,H,W)");
  TORCH_CHECK(arg1.dim() == 4, "weight must be 4D (C_out,C_in/groups,K_h,K_w)");
  TORCH_CHECK(arg6 >= 1, "groups must be >= 1");

  auto input = arg0;
  auto weight = arg1;

  bool has_bias = arg2.has_value() && arg2->defined() && arg2->numel() > 0;
  torch::Tensor bias_t;
  if (has_bias) {
    bias_t = *arg2;
    TORCH_CHECK(bias_t.is_cuda(), "bias must be CUDA tensor if provided");
    if (!bias_t.is_contiguous()) bias_t = bias_t.contiguous();
    TORCH_CHECK(bias_t.scalar_type() == input.scalar_type(), "bias dtype must match input dtype");
    TORCH_CHECK(bias_t.dim() == 1, "bias must be 1D (C_out)");
  }

  int64_t stride_h, stride_w, pad_h, pad_w, dil_h, dil_w;
  get_2d_params(arg3, /*def=*/1, stride_h, stride_w);
  get_2d_params(arg4, /*def=*/0, pad_h, pad_w);
  get_2d_params(arg5, /*def=*/1, dil_h, dil_w);

  TORCH_CHECK(stride_h >= 1 && stride_w >= 1, "stride must be >= 1");
  TORCH_CHECK(dil_h >= 1 && dil_w >= 1, "dilation must be >= 1");
  TORCH_CHECK(pad_h >= 0 && pad_w >= 0, "padding must be >= 0");

  int64_t N = input.size(0);
  int64_t C_in = input.size(1);
  int64_t H_in = input.size(2);
  int64_t W_in = input.size(3);

  int64_t C_out = weight.size(0);
  int64_t C_in_per_g = weight.size(1);
  int64_t K_h = weight.size(2);
  int64_t K_w = weight.size(3);

  TORCH_CHECK(C_in % arg6 == 0, "C_in must be divisible by groups");
  TORCH_CHECK(C_out % arg6 == 0, "C_out must be divisible by groups");
  TORCH_CHECK(C_in_per_g * arg6 == C_in, "weight C_in/groups mismatch with input/groups");
  if (has_bias) TORCH_CHECK(bias_t.size(0) == C_out, "bias must have shape [C_out]");

  int64_t eff_kh = dil_h * (K_h - 1) + 1;
  int64_t eff_kw = dil_w * (K_w - 1) + 1;

  int64_t H_out = (H_in + 2 * pad_h - eff_kh) / stride_h + 1;
  int64_t W_out = (W_in + 2 * pad_w - eff_kw) / stride_w + 1;

  TORCH_CHECK(H_out >= 0 && W_out >= 0, "calculated output size is negative");

  auto out = torch::empty({N, C_out, H_out, W_out}, input.options());
  if (out.numel() == 0) return out;

  int64_t total = out.numel();
  int threads = 256;
  int64_t blocks64 = (total + threads - 1) / threads;
  TORCH_CHECK(blocks64 <= (int64_t)2147483647, "too many blocks");
  int blocks = (int)blocks64;

  cudaStream_t stream = at::cuda::getDefaultCUDAStream();

  // Support float/double/half/bfloat16
  AT_DISPATCH_FLOATING_TYPES_AND2(at::ScalarType::Half, at::ScalarType::BFloat16,
                                  input.scalar_type(), "conv2d_nchw_forward_cuda", [&] {
    using acc_t = typename std::conditional<std::is_same<scalar_t, double>::value, double, float>::type;

    const scalar_t* inp_ptr = input.data_ptr<scalar_t>();
    const scalar_t* w_ptr = weight.data_ptr<scalar_t>();
    const scalar_t* b_ptr = has_bias ? bias_t.data_ptr<scalar_t>() : nullptr;
    scalar_t* out_ptr = out.data_ptr<scalar_t>();

    conv2d_nchw_forward_kernel<scalar_t, acc_t><<<blocks, threads, 0, stream>>>(
        out_ptr, inp_ptr, w_ptr, b_ptr,
        N, C_in, H_in, W_in,
        C_out, K_h, K_w,
        H_out, W_out,
        stride_h, stride_w,
        pad_h, pad_w,
        dil_h, dil_w,
        arg6,
        has_bias);
  });

  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  return out;
}
// [END kernel.cu]