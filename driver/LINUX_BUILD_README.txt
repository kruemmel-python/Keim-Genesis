Linux build artifact
====================

The uploaded sources were compiled into:
  driver/build/libCC_OpenCL.so

This is a Linux x86-64 shared library, not a kernel module. The archive did not contain a Linux kernel-driver Kbuild/Makefile.

Runtime dependency:
  libOpenCL.so.1

Build notes:
  - compiled with g++ as C++17 because the source uses C++ raw string literals for embedded OpenCL kernels.
  - include paths: driver/include and driver
  - link flags: -l:libOpenCL.so.1 -lm -lpthread

See driver/build/linux_build.log for the exact command and ldd output.
