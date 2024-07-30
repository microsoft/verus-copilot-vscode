use vstd::prelude::*;
fn main() {}
verus! {

fn sum (x: usize, y:usize) -> (r: usize)
    requires
        x < 1000,
{
    //Code commented
}

fn binary_search(v: &Vec<u64>, k: u64) -> (r: usize)
{
    let mut i1: usize = 0;
    let mut i2: usize = v.len() - 1;
    while i1 != i2
        invariant
            i2 < v.len(),
    {
        let ghost d = i2 - i1;
        let ix = i1 + (i2 - i1) / 2;
        assert!(ix < v.len());
        if v[ix] < k {
            assert!(ix < 1000); //Please add pre or post-condition to make it true
            i1 = sum (ix, 1);
            assert!(i1 < 2000); //Please add pre or post-condition to make it true
        } else {
            i2 = ix;
        }
    }
    i1
}
}
