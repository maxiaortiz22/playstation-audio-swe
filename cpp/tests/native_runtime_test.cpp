#include "avsys/native_runtime.hpp"

#include <gtest/gtest.h>

#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <tuple>
#include <vector>

namespace {

std::vector<float> make_interleaved_input(std::size_t frames, std::size_t channels) {
  std::vector<float> input(frames * channels);
  for (std::size_t index = 0; index < input.size(); ++index) {
    const auto bits = static_cast<std::uint32_t>(0x3d000000U + index * 7919U);
    input[index] = std::bit_cast<float>(bits);
  }
  if (!input.empty()) {
    input.front() = -0.0F;
  }
  return input;
}

void expect_bit_exact(const std::vector<float>& actual, const std::vector<float>& expected) {
  ASSERT_EQ(actual.size(), expected.size());
  for (std::size_t index = 0; index < actual.size(); ++index) {
    EXPECT_EQ(std::bit_cast<std::uint32_t>(actual[index]),
              std::bit_cast<std::uint32_t>(expected[index]))
        << "sample index " << index;
  }
}

class SysExe002AndRtBlk002PassthroughTest
    : public testing::TestWithParam<std::tuple<std::size_t, std::size_t>> {};

TEST_P(SysExe002AndRtBlk002PassthroughTest, NativeOnlyMonoStereoIsExactAcrossBlockSizes) {
  const auto [channels, block_size] = GetParam();
  const auto frames = block_size * 2 + 17;
  const auto input = make_interleaved_input(frames, channels);
  std::vector<float> output(input.size(), std::numeric_limits<float>::quiet_NaN());

  avsys::passthrough_stream(input, output, frames, channels, block_size);

  expect_bit_exact(output, input);
}

INSTANTIATE_TEST_SUITE_P(BlockSizes64And128,
                         SysExe002AndRtBlk002PassthroughTest,
                         testing::Combine(testing::Values(1U, 2U),
                                          testing::Values(64U, 128U)));

TEST(RtBlk004PartialFinalBlock, ExplicitValidFramesLeavesPaddingUntouched) {
  constexpr std::size_t channels = 2;
  constexpr std::size_t block_frames = 8;
  constexpr std::size_t valid_frames = 3;
  const auto input = make_interleaved_input(block_frames, channels);
  std::vector<float> output(input.size(), -91.0F);

  avsys::passthrough_block(input, output, valid_frames, channels);

  for (std::size_t index = 0; index < valid_frames * channels; ++index) {
    EXPECT_EQ(std::bit_cast<std::uint32_t>(output[index]),
              std::bit_cast<std::uint32_t>(input[index]));
  }
  for (std::size_t index = valid_frames * channels; index < output.size(); ++index) {
    EXPECT_EQ(output[index], -91.0F);
  }
}

TEST(SysExe004NativeErrors, InvalidRuntimeArgumentsCarryStableCodesAndDetails) {
  const std::vector<float> samples(4);
  std::vector<float> output(4);

  try {
    avsys::passthrough_stream(samples, output, 4, 1, 0);
    FAIL() << "expected invalid block size";
  } catch (const avsys::NativeRuntimeError& error) {
    EXPECT_EQ(error.code(), avsys::NativeRuntimeErrorCode::invalid_block_size);
    EXPECT_EQ(error.category(), "native_runtime");
    EXPECT_EQ(error.detail(), "block_size must be greater than zero");
    EXPECT_EQ(avsys::error_code_name(error.code()), "AVSYS_NATIVE_BLOCK_SIZE");
  }
}

}  // namespace
