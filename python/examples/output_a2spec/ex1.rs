use vstd::prelude::*;
fn main() {}
verus! {

fn sum (x: usize, y:usize) -> (r: usize)
    requires
        x < 1000,
    ensures
        r < 2000, //Added to prove assert!(i1 < 2000)
{
    //Code commented
}

fn binary_search(v: &Vec<u64>, k: u64) -> (r: usize)
    requires
        v.len() < 1000, //Added to prove assert!(ix < 1000)
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
            assert!(ix < 1000); //Added a pre-condition to binary_search
            i1 = sum (ix, 1);
            assert!(i1 < 2000); //Added a post-condition to sum
        } else {
            i2 = ix;
        }
    }
    i1
}
}
