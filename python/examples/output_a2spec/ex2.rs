use vstd::prelude::*;
fn main() {}
verus! {

fn sum (x: usize, y:usize) -> (r: usize)
    requires
        x < 1000,
        y < 1000,
    ensures
        r < 2000,

{
    //Code commented
}

fn sumsum (x: usize, y: usize) -> (r: usize)
    requires
        x < 1000,
        y < 1000,
{
    assert!(x < 1000);
    assert!(y < 1000);

    let mut i1: usize = sum ( x, y);

    assert!(i2 < 2000);

    i1
}
}
