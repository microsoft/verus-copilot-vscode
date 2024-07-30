use vstd::prelude::*;
fn main() {}
verus! {

fn myFun(v: &Vec<u64>, k: u64) -> (r: usize)
{
    let mut i1: usize = 0;
    let mut i2: usize = v.len() - 1;
    let mut s: usize = 0;
    while i1 != i2
        invariant
            i2 < v.len(),
    {
        assert!(i1 < 100);
        s = s + v[i1];
        i1 = i1 + 1;
    }
    s 
}
}
