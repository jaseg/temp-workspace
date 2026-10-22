use yanartas_mesh_core::graph::{chacha20_block, Rng};

/// RFC 8439, 2.3.2: the ChaCha20 block function's test vector.
#[test]
fn chacha20_block_matches_rfc8439() {
    let mut key = [0u32; 8];
    for (i, w) in key.iter_mut().enumerate() {
        let b = (4 * i) as u32;
        *w = u32::from_le_bytes([b as u8, (b + 1) as u8, (b + 2) as u8, (b + 3) as u8]);
    }
    let out = chacha20_block(&key, [1, 0x0900_0000, 0x4a00_0000, 0]);
    assert_eq!(
        out,
        [
            0xe4e7f110, 0x15593bd1, 0x1fdd0f50, 0xc47120a3, 0xc7f4d1c7, 0x0368c033, 0x9aaa2204,
            0x4e6cd4c3, 0x466482d2, 0x09aa9f07, 0x05d7c214, 0xa2028bd9, 0xd19c12b5, 0xb94e16de,
            0xe883d0cb, 0x4e3c50a2,
        ]
    );
}

/// The same key, the same stream; another key, another; draws in range, shuffles whole.
#[test]
fn rng_is_keyed_and_in_range() {
    let (mut a, mut b, mut c) = (Rng::new(&[7; 32]), Rng::new(&[7; 32]), Rng::new(&[8; 32]));
    let xs: Vec<u64> = (0..100).map(|_| a.next_u64()).collect();
    let ys: Vec<u64> = (0..100).map(|_| b.next_u64()).collect();
    let zs: Vec<u64> = (0..100).map(|_| c.next_u64()).collect();
    assert_eq!(xs, ys);
    assert_ne!(xs, zs);
    for _ in 0..1000 {
        let r = a.random();
        assert!((0.0..1.0).contains(&r));
        assert!(a.below(7) < 7);
    }
    let mut v: Vec<usize> = (0..50).collect();
    a.shuffle(&mut v);
    let mut w = v.clone();
    w.sort();
    assert_eq!(w, (0..50).collect::<Vec<_>>());
    assert_ne!(v, w);
}
