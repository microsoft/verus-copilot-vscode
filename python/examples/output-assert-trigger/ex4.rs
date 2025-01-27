use builtin::*;
use builtin_macros::*;
use vstd::prelude::Seq;

verus! {
    pub fn main()
    {
    }

    proof fn test_use_forall_fail(s: Seq<int>)
        requires
            4 <= s.len(),
            increasing_arithmetic_nseq(s),
         ensures
            s[2] * 2 == s[1] + s[3],
    {

           
        assert(s[2] * 2 == s[1] + s[3]) by {
            assert(increasing_arithmetic_nseq(s));
            assert({
                let delta = gap (seq[0], seq[1]);
                forall |i: int, j: int| 0<= i < seq.len() - 1 && i + 1 == j ==> #[trigger] gap (seq[i], seq[j]) == delta
            });
            //Trigger expression is gap (seq[i], seq[j]) 
            
            assert(gap (s[1], s[2]) == gap (s[2], s[3]));
            //This assert contains the trigger expression
        };
    }
}
