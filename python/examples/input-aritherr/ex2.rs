use vstd::prelude::*;
fn main() {}
verus! {
fn myfun(x: i32, y: i32) -> (r: i32)
{
    x + y
}
}
