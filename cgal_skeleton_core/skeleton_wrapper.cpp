#include <CGAL/Simple_cartesian.h>
#include <CGAL/Polygon_2.h>
#include <CGAL/create_straight_skeleton_2.h>
#include <CGAL/number_utils.h>
#include <boost/multiprecision/cpp_int.hpp>
#include <boost/multiprecision/number.hpp>
#include <boost/multiprecision/rational_adaptor.hpp>
#include <iostream>
#include <sstream>
#include <string>
#include <memory>
#include <iomanip>

// Use exact rational arithmetic throughout to avoid filtered predicates
typedef boost::multiprecision::number<boost::multiprecision::rational_adaptor<boost::multiprecision::cpp_int_backend<>>> Exact_NT;
typedef CGAL::Simple_cartesian<Exact_NT> Exact_K;

// Input kernel with doubles for reading coordinates
typedef CGAL::Simple_cartesian<double> Input_K;

// Use exact kernel for computation
typedef Exact_K K;
typedef K::Point_2                   Point;
typedef CGAL::Polygon_2<K>           Polygon_2;
typedef CGAL::Straight_skeleton_2<K> Ss;
typedef std::shared_ptr<Ss>          SsPtr;

int main()
{
    Polygon_2 poly;
    std::string line;

    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }

        std::istringstream iss(line);
        double x, y;
        if (iss >> x >> y) {
            // Convert double to exact rational
            poly.push_back(Point(Exact_NT(x), Exact_NT(y)));
        } else {
            std::cerr << "Error: Invalid input line: " << line << std::endl;
            return EXIT_FAILURE;
        }
    }

    if (poly.size() < 3) {
        std::cerr << "Error: Polygon must have at least 3 vertices" << std::endl;
        return EXIT_FAILURE;
    }

    if (!poly.is_counterclockwise_oriented()) {
        std::cerr << "Error: Polygon must be counter-clockwise" << std::endl;
        return EXIT_FAILURE;
    }

    SsPtr ss = CGAL::create_interior_straight_skeleton_2(poly.vertices_begin(), poly.vertices_end(), K());

    if (!ss) {
        std::cerr << "Error: Failed to create straight skeleton" << std::endl;
        return EXIT_FAILURE;
    }

    // Output skeleton edges
    // Iterate through all halfedges in the skeleton
    for (auto he = ss->halfedges_begin(); he != ss->halfedges_end(); ++he) {
        // Only output each edge once (skip the opposite halfedge)
        if (he->id() < he->opposite()->id()) {
            continue;
        }

        // Get the vertices at both ends of the halfedge
        auto v_source = he->vertex();
        auto v_target = he->opposite()->vertex();

        // Get times (distance from boundary)
        // Convert from exact rational to double for output
        double t1 = CGAL::to_double(v_source->time());
        double t2 = CGAL::to_double(v_target->time());

        // Skip contour edges (outline of the input polygon)
        // Contour edges have both vertices at time 0
        if (t1 == 0.0 && t2 == 0.0) {
            continue;
        }

        // Get coordinates
        double x1 = CGAL::to_double(v_source->point().x());
        double y1 = CGAL::to_double(v_source->point().y());
        double x2 = CGAL::to_double(v_target->point().x());
        double y2 = CGAL::to_double(v_target->point().y());

        // Output: start_x start_y end_x end_y start_time end_time
        std::cout << std::setprecision(12) << x1 << " " << y1 << " "
                  << x2 << " " << y2 << " "
                  << t1 << " " << t2 << std::endl;
    }

    return EXIT_SUCCESS;
}

