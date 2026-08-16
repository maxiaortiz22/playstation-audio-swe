#include "avsys/native_runtime.hpp"
#include "avsys/version.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cstddef>
#include <cstdint>
#include <sstream>
#include <string>
#include <string_view>

namespace py = pybind11;

namespace {

[[noreturn]] void raise_runtime_error(const py::object& error_type,
                                      std::string_view code,
                                      std::string_view category,
                                      std::string detail) {
  std::ostringstream message;
  message << '[' << code << "][" << category << "] " << detail;
  py::object instance = error_type(py::str(message.str()));
  instance.attr("code") = py::str(code);
  instance.attr("category") = py::str(category);
  instance.attr("detail") = py::str(detail);
  PyErr_SetObject(error_type.ptr(), instance.ptr());
  throw py::error_already_set();
}

}  // namespace

PYBIND11_MODULE(_native, module) {
  module.doc() = "Native runtime boundary for avsys";
  py::exception<void> runtime_error(module, "NativeRuntimeError", PyExc_ValueError);

  module.def("version", [] { return std::string(avsys::version()); });
  module.def("component_name", [] { return std::string(avsys::native_component_name()); });
  module.def(
      "native_passthrough",
      [runtime_error](const py::array& input, py::ssize_t block_size) {
        if (!input.dtype().is(py::dtype::of<float>())) {
          raise_runtime_error(runtime_error, "AVSYS_BUFFER_DTYPE", "buffer_contract",
                              "input dtype must be native-endian numpy.float32; received " +
                                  py::str(input.dtype()).cast<std::string>());
        }
        if (input.ndim() != 2) {
          raise_runtime_error(runtime_error, "AVSYS_BUFFER_RANK", "buffer_contract",
                              "input rank must be 2 with shape (frames, channels); received rank " +
                                  std::to_string(input.ndim()));
        }

        const auto frames = input.shape(0);
        const auto channels = input.shape(1);
        if (frames <= 0) {
          raise_runtime_error(runtime_error, "AVSYS_BUFFER_SHAPE", "buffer_contract",
                              "input must contain at least one frame; received shape (" +
                                  std::to_string(frames) + ", " + std::to_string(channels) + ")");
        }
        if (channels != 1 && channels != 2) {
          raise_runtime_error(runtime_error, "AVSYS_BUFFER_CHANNELS", "buffer_contract",
                              "input channels must be 1 (mono) or 2 (stereo); received " +
                                  std::to_string(channels));
        }
        if ((input.flags() & py::array::c_style) == 0) {
          raise_runtime_error(runtime_error, "AVSYS_BUFFER_CONTIGUITY", "buffer_contract",
                              "input must be C-contiguous with frame-major interleaved samples");
        }
        const auto input_address = reinterpret_cast<std::uintptr_t>(input.data());
        const auto alignment_remainder = input_address % alignof(float);
        if (alignment_remainder != 0) {
          raise_runtime_error(
              runtime_error, "AVSYS_BUFFER_ALIGNMENT", "buffer_contract",
              "input data pointer is not aligned to alignof(float): required alignment=" +
                  std::to_string(alignof(float)) + " bytes, address remainder=" +
                  std::to_string(alignment_remainder));
        }
        if (block_size <= 0) {
          raise_runtime_error(runtime_error, "AVSYS_BLOCK_SIZE", "native_runtime",
                              "block_size must be greater than zero; received " +
                                  std::to_string(block_size));
        }

        py::array_t<float> output({frames, channels});
        const auto* input_samples = static_cast<const float*>(input.data());
        auto* output_samples = output.mutable_data();
        const auto frame_count = static_cast<std::size_t>(frames);
        const auto channel_count = static_cast<std::size_t>(channels);
        const auto sample_count = frame_count * channel_count;

        try {
          py::gil_scoped_release release;
          avsys::passthrough_stream(
              std::span<const float>(input_samples, sample_count),
              std::span<float>(output_samples, sample_count), frame_count, channel_count,
              static_cast<std::size_t>(block_size));
        } catch (const avsys::NativeRuntimeError& error) {
          raise_runtime_error(runtime_error, avsys::error_code_name(error.code()),
                              error.category(), std::string(error.detail()));
        }

        return output;
      },
      py::arg("input").noconvert(), py::arg("block_size") = 128,
      R"doc(Process one float32 interleaved mono/stereo stream in native blocks.

The input must be a C-contiguous NumPy array shaped (frames, channels), and its
data pointer must satisfy alignof(float). It is borrowed read-only for the
duration of this coarse call and is never modified. The return value is a new,
writable, Python-owned C-contiguous float32 array.
)doc");
}
