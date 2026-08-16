#include "avsys/version.hpp"

#include <gtest/gtest.h>

TEST(SysBnd001NativeOnly, CoreMetadataDoesNotRequirePython) {
  EXPECT_EQ(avsys::native_component_name(), "avsys_core");
  EXPECT_EQ(avsys::version(), "0.1.0");
}
