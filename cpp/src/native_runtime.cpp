#include "avsys/native_runtime.hpp"

#include <algorithm>
#include <limits>
#include <sstream>
#include <utility>

namespace avsys {
namespace {

[[nodiscard]] std::size_t checked_sample_count(std::size_t frames, std::size_t channels) {
  if (channels != 0 && frames > std::numeric_limits<std::size_t>::max() / channels) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::sample_count_overflow,
                             "frames * channels exceeds size_t");
  }
  return frames * channels;
}

[[nodiscard]] std::string make_message(NativeRuntimeErrorCode code,
                                       std::string_view detail) {
  std::ostringstream message;
  message << '[' << error_code_name(code) << "][native_runtime] " << detail;
  return message.str();
}

}  // namespace

std::string_view error_code_name(NativeRuntimeErrorCode code) noexcept {
  switch (code) {
    case NativeRuntimeErrorCode::invalid_channel_count:
      return "AVSYS_NATIVE_CHANNELS";
    case NativeRuntimeErrorCode::invalid_block_size:
      return "AVSYS_NATIVE_BLOCK_SIZE";
    case NativeRuntimeErrorCode::input_size_mismatch:
      return "AVSYS_NATIVE_INPUT_SIZE";
    case NativeRuntimeErrorCode::output_size_mismatch:
      return "AVSYS_NATIVE_OUTPUT_SIZE";
    case NativeRuntimeErrorCode::sample_count_overflow:
      return "AVSYS_NATIVE_SAMPLE_COUNT_OVERFLOW";
  }
  return "AVSYS_NATIVE_UNKNOWN";
}

NativeRuntimeError::NativeRuntimeError(NativeRuntimeErrorCode code, std::string detail)
    : std::invalid_argument(make_message(code, detail)), code_(code), detail_(std::move(detail)) {}

void passthrough_block(std::span<const float> input,
                       std::span<float> output,
                       std::size_t valid_frames,
                       std::size_t channels) {
  if (channels != 1 && channels != 2) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::invalid_channel_count,
                             "channels must be 1 (mono) or 2 (stereo)");
  }

  const auto valid_samples = checked_sample_count(valid_frames, channels);
  if (input.size() < valid_samples) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::input_size_mismatch,
                             "input span is smaller than valid_frames * channels");
  }
  if (output.size() < valid_samples) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::output_size_mismatch,
                             "output span is smaller than valid_frames * channels");
  }

  std::copy_n(input.begin(), valid_samples, output.begin());
}

void passthrough_stream(std::span<const float> input,
                        std::span<float> output,
                        std::size_t frames,
                        std::size_t channels,
                        std::size_t block_size) {
  if (channels != 1 && channels != 2) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::invalid_channel_count,
                             "channels must be 1 (mono) or 2 (stereo)");
  }
  if (block_size == 0) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::invalid_block_size,
                             "block_size must be greater than zero");
  }

  const auto sample_count = checked_sample_count(frames, channels);
  if (input.size() != sample_count) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::input_size_mismatch,
                             "input span must contain exactly frames * channels samples");
  }
  if (output.size() != sample_count) {
    throw NativeRuntimeError(NativeRuntimeErrorCode::output_size_mismatch,
                             "output span must contain exactly frames * channels samples");
  }

  for (std::size_t frame_offset = 0; frame_offset < frames;) {
    const auto valid_frames = std::min(block_size, frames - frame_offset);
    const auto sample_offset = frame_offset * channels;
    const auto remaining_samples = sample_count - sample_offset;
    passthrough_block(input.subspan(sample_offset, remaining_samples),
                      output.subspan(sample_offset, remaining_samples), valid_frames, channels);
    frame_offset += valid_frames;
  }
}

}  // namespace avsys
