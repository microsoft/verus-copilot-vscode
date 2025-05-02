Failed assertion
```
Line 17-17:
        assert(s[2] * 2 == s[1] + s[3]);
```

Context Code
```
verus!{
    spec fn is_positive (i: int) -> bool {
        i > 0
    }

    spec fn gap (i: int, j: int) -> int {
        j - i
    }
}

verus!{
    spec fn increasing_arithmetic_nseq (seq: Seq<int>) -> bool {
        &&& seq.len() > 1
        &&& forall |i: int| 0<= i < seq.len() ==> #[trigger] is_positive(seq[i])
        &&& 
            ({
                let delta = gap (seq[0], seq[1]);
                &&& forall |i: int, j: int| 0<= i < seq.len() - 1 && i + 1 == j ==> #[trigger] gap (seq[i], seq[j]) == delta
                &&& delta > 0
            })
    }
}
```

Target Code
```
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
        };
    }
}
```
