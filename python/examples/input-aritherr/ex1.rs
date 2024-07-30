use vstd::prelude::*;
fn main() {}
verus! {
fn myfun(x: i32, y: i32) -> (r: i32)
{
    let mut i: usize = 0;
    let mut z: i32 = 0;
    while i < 4
        invariant
            0 <= i,
            i <= 4,
    {
      z = x + y;
      i += 1;
    }
    z
}
}
