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
        invariant
            0 <= i <= a.len(),
            exists |k: int| i <= k < a.len() && a[k] > 0,
        ensures
            a[i as int] > 0,
    {
        if a[i] > 0 {
            break;
        }
        i = i + 1;
    }
    a[i]
}
}
