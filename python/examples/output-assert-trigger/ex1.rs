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
            forall |i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i]),
         ensures
            s[3] % 2 == 0,
   {
        assert(s[3] % 2 == 0) by {
            assert(forall |i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i]));
            //Trigger expression is is_even(s[i]) 
            
            assert(is_even(s[3])); 
            //This assert contains the trigger-expression and is relevant to
            //the failed assert
        }

    }
}
