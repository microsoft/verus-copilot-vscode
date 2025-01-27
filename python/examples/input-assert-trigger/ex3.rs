Failed assertion
```
Line 21-21:
        assert(isGood(B[2]));
```

Code
```
use builtin::*;
use builtin_macros::*;
use vstd::prelude::Seq;


verus! {
    pub fn main()
    {
    }

    #[verifier::external_body]
    spec fn isGood(i: int) -> bool;

    proof fn test_use_forall_fail(A: Seq<int>, B: Seq<int>)
        requires
            100 <= A.len(),
            A.len() == B.len(),
            forall |i: int| 0 <= i < A.len() - 1 ==> #[trigger] A[i] == B[i+1],
            forall |i: int| 0 <= i < A.len() ==> isGood(#[trigger] A[i]),
    {
        assert(isGood(B[2])) by{
            assert(forall |i: int| 0 <= i < A.len() - 1 ==> #[trigger] A[i] == B[i+1]);
            assert(forall |i: int| 0 <= i < A.len() ==> isGood(#[trigger] A[i]));
        };
    }
}
```
