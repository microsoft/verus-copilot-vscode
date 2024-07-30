use vstd::prelude::*;
fn main() {}

verus!{
pub fn example(A: &Vec<u64>, B: &mut Vec<u64>)
requires 
    old(B).len() == 0,
ensures 
    B@ == A@,
{
    let mut k: usize = 0;
    
    assert(B@ == A@.take(0)); 
    while (k < A.len()) 
        invariant 
            k <= A.len(),
            B@ == A@.take(k as int),
    { 

        B.push(A[k]);

        k = k + 1;
        assert(A@.take(k as int).drop_last() == A@.take(k -1));//This is sometimes needed to prove
                                                               //assert related to Seq::take
        reveal(Seq::filter);
        assert(B@ == A@.take(k as int));
    }
    assert(A@ == A@.take(A.len() as int)); //This is often needed to prove things related to
                                           //Seq::take
}
}
