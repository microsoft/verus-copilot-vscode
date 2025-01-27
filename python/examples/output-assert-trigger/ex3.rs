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
        assert(isGood(B[2])) by {
            assert(forall |i: int| 0 <= i < A.len() - 1 ==> #[trigger] A[i] == B[i+1]);
            //A[i] is the trigger expression

            assert(forall |i: int| 0 <= i < A.len() ==> isGood(#[trigger] A[i]));
            //A[i] is the trigger expression

            assert(B[2] == A[1]);
            //this assert involves A[1], the trigger expression, and is relevant to the
            //failed assert (isGood(B[2]))            
        };
    }
}
