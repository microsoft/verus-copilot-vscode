use vstd::prelude::*;
fn main() {}
verus! {
fn myfun(x: i32, y: i32) -> (r: i32)
    requires
        i32::MIN <= x + y <= i32::MAX,
{
    x + y
}
}
