#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Polygon_2.h>
#include <CGAL/create_straight_skeleton_2.h>
#include <iostream>
#include <sstream>
#include <string>
#include <memory>

typedef CGAL::Exact_predicates_inexact_constructions_kernel K;
typedef K::Point_2                   Point;
typedef CGAL::Polygon_2<K>           Polygon_2;
typedef CGAL::Straight_skeleton_2<K> Ss;
typedef std::shared_ptr<Ss>          SsPtr;

int main()
{
    // Read polygon from stdin
    Polygon_2 poly;
    std::string line;

    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }

        std::istringstream iss(line);
        double x, y;
        if (iss >> x >> y) {
            poly.push_back(Point(x, y));
        } else {
            std::cerr << "Error: Invalid input line: " << line << std::endl;
            return EXIT_FAILURE;
        }
    }

    if (poly.size() < 3) {
        std::cerr << "Error: Polygon must have at least 3 vertices" << std::endl;
        return EXIT_FAILURE;
    }

    // Ensure counter-clockwise orientation
    if (!poly.is_counterclockwise_oriented()) {
        poly.reverse_orientation();
    }

    // Create interior straight skeleton
    SsPtr ss = CGAL::create_interior_straight_skeleton_2(poly.vertices_begin(), poly.vertices_end());

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

