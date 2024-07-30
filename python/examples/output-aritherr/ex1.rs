use vstd::prelude::*;
fn main() {}
verus! {
fn myfun(x: i32, y: i32) -> (r: i32)
{
    let mut i: usize = 0;
    let mut z: i32 = 0;
    assert!(0< x<10000);
    assert!(0< y<10000);
    while i < 4
        invariant
            x < 10000,
            y < 10000,
            0 < x,
            0 < y,
            0 <= i,
            i <= r,
    {
      z = x + y;
      i += 1;
    }
    z
}
}
