#include "avsys/version.hpp"

#include <pybind11/pybind11.h>

#include <string>

namespace py = pybind11;

PYBIND11_MODULE(_native, module) {
  module.doc() = "Minimal native build and linkage metadata for avsys";
  module.def("version", [] { return std::string(avsys::version()); });
  module.def("component_name", [] { return std::string(avsys::native_component_name()); });
}
