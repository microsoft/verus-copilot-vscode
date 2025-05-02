Failed assertion
```
Line 18-18:
            assert(s[i] + 2 > 2);
```

Context Code
```
verus! {
    spec fn is_positive(i: int) -> bool {
        i > 0
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
            forall |i: int| 0 <= i < s.len() ==> #[trigger] is_positive(s[i]),
        ensures
            forall |i: int| 0 <= i < s.len() ==> #[trigger] s[i] + 2 > 2,
    {
        assert forall |i: int| 0 <= i < s.len() implies s[i] + 2 > 2  by {
            assert(s[i] + 2 > 2) by {
                assert(forall |k: int| 0 <= k < s.len() ==> #[trigger] is_positive(s[k]));
            };
        };
    }
}
```
