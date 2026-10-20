use yanartas_mesh_core::geom::{crosses, dist, resample, P};
use yanartas_mesh_core::grid::Grid;
use yanartas_mesh_core::zones::Zones;
use yanartas_mesh_core::{settle, Input, Params};

#[test]
fn grid_finds_every_point_within_reach() {
    let p: Vec<P> = (0..400)
        .map(|k| [(k % 20) as f64 * 0.37, (k / 20) as f64 * 0.41])
        .collect();
    let g = Grid::new(&p, 0.5, |_| true);
    let q = [3.3, 4.1];
    let mut found = Vec::new();
    g.around(q, 1.0, |i| found.push(i));
    for (i, x) in p.iter().enumerate() {
        if dist(*x, q) <= 1.0 {
            assert!(found.contains(&i), "point {i} missed");
        }
    }
    assert!(!g.any_around([100.0, 100.0], 1.0));
}

#[test]
fn zones_tell_inside_from_out_and_holes() {
    let outer = vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]];
    let hole = vec![[4.0, 4.0], [6.0, 4.0], [6.0, 6.0], [4.0, 6.0]];
    let right = vec![[10.0, 0.0], [20.0, 0.0], [20.0, 10.0], [10.0, 10.0]];
    let z = Zones::new(&[vec![outer, hole], vec![right]], 0.6);
    assert_eq!(z.of([1.0, 1.0]), Some(0));
    assert_eq!(z.of([5.0, 5.0]), None);
    assert_eq!(z.of([15.0, 5.0]), Some(1));
    assert_eq!(z.of([25.0, 5.0]), None);
}

#[test]
fn resample_keeps_the_ends_and_evens_the_steps() {
    let p = vec![[0.0, 0.0], [1.0, 0.0], [1.0, 2.0]];
    let q = resample(&p, 0.1);
    assert_eq!(q[0], [0.0, 0.0]);
    assert_eq!(*q.last().unwrap(), [1.0, 2.0]);
    assert_eq!(q.len(), 31);
    assert!(q.windows(2).all(|w| (dist(w[0], w[1]) - 0.1).abs() < 0.05));
}

#[test]
fn crossing_is_strict() {
    assert!(crosses([0.0, 0.0], [2.0, 2.0], [0.0, 2.0], [2.0, 0.0]));
    assert!(!crosses([0.0, 0.0], [1.0, 1.0], [1.0, 1.0], [2.0, 0.0])); // (sharing an end)
    assert!(!crosses([0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]));
}

/// Two wavy traces in a box with a wide gap between them: settled, they keep a pitch apart,
/// stay in the box and their ends stay put.
#[test]
fn settling_keeps_clear_and_in_its_zone() {
    let pitch = 0.3;
    let wave = |y: f64| -> Vec<P> {
        (0..=200)
            .map(|k| {
                let x = k as f64 * 0.1;
                [x, y + 0.2 * (x * 1.3).sin()]
            })
            .collect()
    };
    let lines = vec![wave(2.0), wave(3.5)];
    let box_ = vec![[-0.5, 0.0], [20.5, 0.0], [20.5, 6.0], [-0.5, 6.0]];
    let mut edge = Vec::new();
    for k in 0..4 {
        edge.extend(resample(&[box_[k], box_[(k + 1) % 4]], 0.05));
    }
    let input = Input {
        lines: lines.clone(),
        pitch,
        edge,
        zones: vec![vec![box_]],
        keep: [0.0; 4],
    };
    let mut steps = 0;
    let out = settle(&input, &Params::default(), &mut |_| steps += 1);
    assert!(steps > 0);
    for (t, line) in out.iter().enumerate() {
        assert_eq!(line[0], lines[t][0]);
        assert_eq!(*line.last().unwrap(), *lines[t].last().unwrap());
        assert!(line
            .iter()
            .all(|q| q[0] > -0.5 && q[0] < 20.5 && q[1] > 0.0 && q[1] < 6.0));
    }
    let least = out[0]
        .iter()
        .flat_map(|a| out[1].iter().map(move |b| dist(*a, *b)))
        .fold(f64::MAX, f64::min);
    assert!(least > 0.95 * pitch, "traces {least} apart");
}

#[test]
fn grid_lookups_off_the_grid_find_nothing() {
    let p: Vec<P> = vec![[0.0, 0.0], [1.0, 1.0]];
    let g = Grid::new(&p, 0.5, |_| true);
    let mut n = 0;
    g.within([50.0, 0.5], 1.0, |_, _| n += 1);
    g.within([-50.0, -50.0], 1.0, |_, _| n += 1);
    assert_eq!(n, 0);
}

#[test]
fn untangle_keeps_the_curve_simple() {
    use yanartas_mesh_core::{curve::untangle, segs::crossing};
    let old: Vec<P> = vec![[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0], [-1.0, 0.5]];
    let mut new = old.clone();
    new[1] = [4.0, 2.0]; // (the edge 0-1 would cross 2-3)
    let all: Vec<usize> = (0..old.len()).collect();
    assert!(crossing(&old, &all).is_empty());
    assert!(!crossing(&new, &all).is_empty());
    let out = untangle(&old, &new);
    assert!(crossing(&out, &all).is_empty());
}

#[test]
fn arcs_follow_the_polyline_within_the_tolerance() {
    use yanartas_mesh_core::arcs::{fit, sample, Piece};
    use yanartas_mesh_core::geom::closest;
    // a straight run, a quarter circle (radius 1) and a straight run again
    let mut p: Vec<P> = (0..=10).map(|k| [k as f64 * 0.1, 0.0]).collect();
    for k in 1..=30 {
        let a = -std::f64::consts::FRAC_PI_2 + k as f64 / 30.0 * std::f64::consts::FRAC_PI_2;
        p.push([1.0 + a.cos(), 1.0 + a.sin()]);
    }
    p.extend((1..=10).map(|k| [2.0, 1.0 + k as f64 * 0.1]));
    let tol = 0.002;
    let pieces = fit(&p, tol);
    assert_eq!(pieces.len(), 3, "{pieces:?}");
    assert!(matches!(pieces[0], Piece::Line(..)));
    assert!(matches!(pieces[1], Piece::Arc(..)));
    assert!(matches!(pieces[2], Piece::Line(..)));
    // drawn again, within the tolerance of the polyline (and the polyline of it)
    let q = sample(&pieces, 0.01);
    let near = |x: P, line: &[P]| {
        line.windows(2)
            .map(|w| dist(closest(x, w[0], w[1]).0, x))
            .fold(f64::MAX, f64::min)
    };
    assert!(q.iter().all(|&x| near(x, &p) <= tol + 1e-9));
    assert!(p.iter().all(|&x| near(x, &q) <= tol + 1e-6));
    assert_eq!(q[0], p[0]);
    assert_eq!(*q.last().unwrap(), *p.last().unwrap());
}
