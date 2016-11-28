cmake_minimum_required(VERSION 3.2)
project(Squall_Catch_Tests)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g -std=c++11")

include(FindPackageHandleStandardArgs)
find_library(LIBEV_LIBRARY NAMES ev)
find_path(LIBEV_INCLUDE_DIR ev.h PATH_SUFFIXES include/ev)
find_package_handle_standard_args(libev DEFAULT_MSG LIBEV_LIBRARY LIBEV_INCLUDE_DIR)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/..)
file(GLOB SRS "${CMAKE_CURRENT_SOURCE_DIR}/test_cxx/*.cxx")

add_executable(catch main.cpp ${SRS})
target_link_libraries(catch ${LIBEV_LIBRARY})

enable_testing()
add_test(NAME catch_tests COMMAND catch)
add_custom_command(TARGET catch POST_BUILD COMMAND ctest --output-on-failure)
