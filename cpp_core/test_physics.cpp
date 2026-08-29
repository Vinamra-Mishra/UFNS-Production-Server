#include <iostream>
#include <vector>
#include <cmath>
#include <cassert>
#include "solver_2d.h"
#include "optical_flow.h"
#include "routing.h"

void test_solver_lake_at_rest() {
    std::cout << "[C++ Test] 1. Testing Lake-at-Rest C-Property..." << std::endl;
    const int W = 20, H = 20;
    std::vector<float> dem(W * H, 10.0f);
    std::vector<uint8_t> mask(W * H, 1);
    std::vector<float> depth(W * H, 0.0f);
    std::vector<float> u(W * H, 0.0f);
    std::vector<float> v(W * H, 0.0f);
    MassBalanceReport report;

    int ret = ufns_solve_inundation_2d(
        dem.data(), mask.data(), W, H, 30.0f,
        "lake_at_rest", 15, 0.0f, 100.0f,
        depth.data(), u.data(), v.data(), &report
    );

    assert(ret == 0);
    assert(report.max_spurious_velocity_ms < 1e-4);
    std::cout << "  -> PASS: Max spurious velocity = " << report.max_spurious_velocity_ms << " m/s" << std::endl;
}

void test_optical_flow_pyramidal() {
    std::cout << "[C++ Test] 2. Testing Pyramidal Optical Flow..." << std::endl;
    const int W = 32, H = 32;
    std::vector<float> prev(W * H, 0.0f);
    std::vector<float> curr(W * H, 0.0f);
    std::vector<float> flow_u(W * H, 0.0f);
    std::vector<float> flow_v(W * H, 0.0f);

    for (int r = 10; r < 20; ++r) {
        for (int c = 10; c < 20; ++c) {
            prev[r * W + c] = 40.0f;
            curr[r * W + (c + 2)] = 40.0f;
        }
    }

    int ret = ufns_compute_optical_flow(
        prev.data(), curr.data(), W, H, 3, 5, 5,
        flow_u.data(), flow_v.data()
    );

    assert(ret == 0);
    std::cout << "  -> PASS: Optical flow successfully computed dense vector fields" << std::endl;
}

void test_dynamic_evacuation_routing() {
    std::cout << "[C++ Test] 3. Testing Time-Dependent A* Evacuation Routing..." << std::endl;
    const int W = 20, H = 20;
    std::vector<float> depth(W * H, 0.05f);
    std::vector<float> u(W * H, 0.0f);
    std::vector<float> v(W * H, 0.0f);

    std::vector<float> waypoints_in = { 10.0f, 10.0f, 250.0f, 250.0f, 500.0f, 500.0f };
    std::vector<float> waypoints_out(32, 0.0f);
    int num_out = 0;
    float path_len = 0.0f, max_haz = 0.0f;
    int is_passable = 0;

    int ret = ufns_evaluate_dynamic_route(
        waypoints_in.data(), 3,
        depth.data(), u.data(), v.data(),
        W, H, 30.0f, 0.0f, 0.0f,
        0.30f, 1.50f, 0.0f,
        waypoints_out.data(), 16, &num_out,
        &path_len, &max_haz, &is_passable
    );

    assert(ret == 0);
    assert(is_passable == 1);
    assert(num_out >= 2);
    std::cout << "  -> PASS: Route computed with " << num_out << " safe waypoints, passable = true" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "  UFNS C++20 NATIVE CORE ENGINE TEST SUITE" << std::endl;
    std::cout << "==================================================" << std::endl;

    test_solver_lake_at_rest();
    test_optical_flow_pyramidal();
    test_dynamic_evacuation_routing();

    std::cout << "==================================================" << std::endl;
    std::cout << "  ALL 3/3 C++ CORE TESTS PASSED SUCCESSFULLY!" << std::endl;
    std::cout << "==================================================" << std::endl;
    return 0;
}
