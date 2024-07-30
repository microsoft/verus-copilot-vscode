use vstd::prelude::*;
fn main() {}
verus! {
fn myfun( ) -> (r: i32)
{
    let mut i: i32 = 10;
    while i < 20
    {
      i += 1;
    }
    i
}
}
