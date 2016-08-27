cmake_minimum_required(VERSION 3.2)
project(Squall)

set(EXECUTABLE_OUTPUT_PATH ${BUILD_PATH})
set(BUILD_PATH, ${CMAKE_CURRENT_SOURCE_DIR}/build)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -std=c++11")

include(FindPackageHandleStandardArgs)
find_library(LIBEV_LIBRARY NAMES ev)
find_path(LIBEV_INCLUDE_DIR ev.h PATH_SUFFIXES include/ev)
find_package_handle_standard_args(libev DEFAULT_MSG LIBEV_LIBRARY LIBEV_INCLUDE_DIR)

include_directories(${CMAKE_CURRENT_SOURCE_DIR})

add_executable(hello demo/cxx/hello.cxx)
target_link_libraries(hello ${LIBEV_LIBRARY})
