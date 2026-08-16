#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <vector>

namespace avsys {

// A bounded single-producer/single-consumer queue. One thread owns try_push
// calls and one thread owns try_pop calls. Cross-thread state queries are not
// exposed as correctness preconditions.
template <typename T>
class SpscRingBuffer final {
  static_assert(std::is_trivially_copyable_v<T>,
                "SpscRingBuffer elements must be trivially copyable");
  static_assert(std::is_default_constructible_v<T>,
                "SpscRingBuffer elements must be default constructible");

 public:
  explicit SpscRingBuffer(std::size_t capacity)
      : capacity_(validate_capacity(capacity)), mask_(capacity_ - 1), storage_(capacity_) {}

  SpscRingBuffer(const SpscRingBuffer&) = delete;
  SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;
  SpscRingBuffer(SpscRingBuffer&&) = delete;
  SpscRingBuffer& operator=(SpscRingBuffer&&) = delete;

  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }

  [[nodiscard]] bool try_push(const T& value) noexcept {
    const auto write = write_counter_.value.load(std::memory_order_relaxed);
    const auto read = read_counter_.value.load(std::memory_order_acquire);
    if (write - read == capacity_) {
      return false;
    }

    storage_[static_cast<std::size_t>(write) & mask_] = value;
    write_counter_.value.store(write + 1, std::memory_order_release);
    return true;
  }

  [[nodiscard]] bool try_pop(T& destination) noexcept {
    const auto read = read_counter_.value.load(std::memory_order_relaxed);
    const auto write = write_counter_.value.load(std::memory_order_acquire);
    if (write == read) {
      return false;
    }

    destination = storage_[static_cast<std::size_t>(read) & mask_];
    read_counter_.value.store(read + 1, std::memory_order_release);
    return true;
  }

 private:
  struct alignas(64) Counter {
    std::atomic<std::uint64_t> value{0};
  };

  [[nodiscard]] static std::size_t validate_capacity(std::size_t capacity) {
    constexpr auto max_live_distance = std::uint64_t{1} << 63;
    if (capacity == 0 || (capacity & (capacity - 1)) != 0) {
      throw std::invalid_argument("SpscRingBuffer capacity must be a non-zero power of two");
    }
    if (capacity >= max_live_distance ||
        capacity > static_cast<std::size_t>(std::numeric_limits<std::uint64_t>::max())) {
      throw std::invalid_argument("SpscRingBuffer capacity must be less than 2^63");
    }
    return capacity;
  }

  const std::size_t capacity_;
  const std::size_t mask_;
  std::vector<T> storage_;
  Counter write_counter_;
  Counter read_counter_;
};

}  // namespace avsys
