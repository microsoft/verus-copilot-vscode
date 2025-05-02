use vstd::prelude::*;
fn main() {}
verus!{
pub fn myfun(a: &Vec<i32>) -> (ret: i32)
    requires
        exists |i:int| 0<= i < a.len() && a[i] > 0,
    ensures
        ret > 0,
{
    let mut i: usize = 0;

    while (i < a.len())
    {
        if a[i] > 0 {
            break;
        }
        i = i + 1;
    }
    a[i]
}
}
