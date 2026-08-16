#pragma once

#include <cstddef>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>

namespace avsys {

enum class NativeRuntimeErrorCode {
  invalid_channel_count,
  invalid_block_size,
  input_size_mismatch,
  output_size_mismatch,
  sample_count_overflow,
};

[[nodiscard]] std::string_view error_code_name(NativeRuntimeErrorCode code) noexcept;

class NativeRuntimeError : public std::invalid_argument {
 public:
  NativeRuntimeError(NativeRuntimeErrorCode code, std::string detail);

  [[nodiscard]] NativeRuntimeErrorCode code() const noexcept { return code_; }
  [[nodiscard]] std::string_view category() const noexcept { return "native_runtime"; }
  [[nodiscard]] std::string_view detail() const noexcept { return detail_; }

 private:
  NativeRuntimeErrorCode code_;
  std::string detail_;
};

// Copies valid_frames of frame-major, interleaved float32 PCM. Input and output
// spans may be larger than the valid region; samples beyond it are untouched.
void passthrough_block(std::span<const float> input,
                       std::span<float> output,
                       std::size_t valid_frames,
                       std::size_t channels);

// Processes one complete interleaved stream in blocks. The last call to
// passthrough_block receives the exact partial valid-frame count.
void passthrough_stream(std::span<const float> input,
                        std::span<float> output,
                        std::size_t frames,
                        std::size_t channels,
                        std::size_t block_size);

}  // namespace avsys
