#include "avsys/spsc_ring_buffer.hpp"

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace {

static_assert(!std::is_copy_constructible_v<avsys::SpscRingBuffer<int>>);
static_assert(!std::is_copy_assignable_v<avsys::SpscRingBuffer<int>>);
static_assert(!std::is_move_constructible_v<avsys::SpscRingBuffer<int>>);
static_assert(!std::is_move_assignable_v<avsys::SpscRingBuffer<int>>);

class RtSpsc001And002CapacityTest : public testing::TestWithParam<std::size_t> {};

TEST_P(RtSpsc001And002CapacityTest, ExposesEveryConfiguredSlotAsUsable) {
  const auto capacity = GetParam();
  avsys::SpscRingBuffer<int> queue(capacity);
  EXPECT_EQ(queue.capacity(), capacity);

  for (std::size_t value = 0; value < capacity; ++value) {
    EXPECT_TRUE(queue.try_push(static_cast<int>(value)));
  }
  EXPECT_FALSE(queue.try_push(-1));
}

INSTANTIATE_TEST_SUITE_P(CapacitiesOneTwoAndLarger,
                         RtSpsc001And002CapacityTest,
                         testing::Values(1U, 2U, 8U));

TEST(RtSpsc001Construction, RejectsZeroAndNonPowerOfTwoCapacity) {
  EXPECT_THROW((avsys::SpscRingBuffer<int>{0}), std::invalid_argument);
  EXPECT_THROW((avsys::SpscRingBuffer<int>{3}), std::invalid_argument);
}

TEST(RtQue001Through005Boundaries, FullEmptyFifoAndFailedOperationsPreserveData) {
  avsys::SpscRingBuffer<int> queue(2);
  int destination = 77;

  EXPECT_FALSE(queue.try_pop(destination));
  EXPECT_EQ(destination, 77);
  EXPECT_TRUE(queue.try_push(10));
  EXPECT_TRUE(queue.try_push(20));
  EXPECT_FALSE(queue.try_push(30));

  EXPECT_TRUE(queue.try_pop(destination));
  EXPECT_EQ(destination, 10);
  EXPECT_TRUE(queue.try_pop(destination));
  EXPECT_EQ(destination, 20);
  EXPECT_FALSE(queue.try_pop(destination));
  EXPECT_EQ(destination, 20);
}

TEST(RtQue003StorageWraparound, PreservesFifoAcrossMultipleStorageWraparounds) {
  constexpr std::size_t capacity = 4;
  constexpr int rounds = 17;
  avsys::SpscRingBuffer<int> queue(capacity);
  int destination = -1;

  for (int round = 0; round < rounds; ++round) {
    for (std::size_t slot = 0; slot < capacity; ++slot) {
      const auto value = round * static_cast<int>(capacity) + static_cast<int>(slot);
      ASSERT_TRUE(queue.try_push(value));
    }
    EXPECT_FALSE(queue.try_push(-999));
    for (std::size_t slot = 0; slot < capacity; ++slot) {
      ASSERT_TRUE(queue.try_pop(destination));
      const auto expected = round * static_cast<int>(capacity) + static_cast<int>(slot);
      EXPECT_EQ(destination, expected);
    }
  }
}

TEST(RtQue006CounterWraparound, PreservesFifoAcrossReducedWidthCounterRollover) {
  constexpr std::size_t capacity = 4;
  constexpr int values_to_transfer = 300;
  avsys::SpscRingBuffer<int, std::uint8_t> queue(capacity);
  int destination = -1;

  for (int value = 0; value < values_to_transfer; ++value) {
    ASSERT_TRUE(queue.try_push(value));
    ASSERT_TRUE(queue.try_pop(destination));
    EXPECT_EQ(destination, value);
  }
}

}  // namespace
