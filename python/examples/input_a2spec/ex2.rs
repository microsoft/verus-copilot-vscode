use vstd::prelude::*;
fn main() {}
verus! {

fn sum (x: usize, y:usize) -> (r: usize)
    requires
        x < 1000,
        y < 1000,

{
    //Code commented
}

fn sumsum (x: usize, y: usize) -> (r: usize)
{
    assert!(x < 1000);
    assert!(y < 1000);

    let mut i1: usize = sum ( x, y);

    assert!(i2 < 2000);

    i1
}
}
