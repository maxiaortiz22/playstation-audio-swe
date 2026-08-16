#pragma once

#include <string_view>

namespace avsys {

[[nodiscard]] constexpr std::string_view version() noexcept {
  return "0.1.0";
}

[[nodiscard]] std::string_view native_component_name() noexcept;

}  // namespace avsys
