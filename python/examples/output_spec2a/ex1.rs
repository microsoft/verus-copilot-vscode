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

fn binary_search(v: &Vec<u64>, k: u64) -> (r: usize)
    requires
        forall|i:int, j:int| 0 <= i <= j < v.len() ==> v[i] <= v[j],
        exists|i:int| 0 <= i < v.len() && k == v[i],
    ensures
        r < v.len(),
        k == v[r as int],
{
    let mut i1: usize = 0;
    let mut i2: usize = v.len() - 1;
    while i1 != i2
        invariant
            i2 < v.len(),
            exists|i:int| i1 <= i <= i2 && k == v[i],
            forall|i:int, j:int| 0 <= i <= j < v.len() ==> v[i] <= v[j],
    {
        let ghost d = i2 - i1;
        let ix = i1 + (i2 - i1) / 2;
        if v[ix] < k {
            assert!(ix < 1000);
            assert!(1 < 1000);
            i1 = sum (ix, 1);
        } else {
            i2 = ix;
        }
    }
    i1
}
}
