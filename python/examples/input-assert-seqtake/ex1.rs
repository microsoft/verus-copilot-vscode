Failed assertion
```
Line 24-24:
                    assert(B@ == A@.take(k as int));
```

Code
```
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

        assert(B@ == A@.take(k as int));
    }
}
}
