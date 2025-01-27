Failed assertion
```
Line 18-18:
            assert(s[i] + 2 > 2);
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

    proof fn test_use_forall_fail(s: Seq<int>)
        requires
            forall |i: int| 0 <= i < s.len() ==> #[trigger] is_positive(s[i]),
        ensures
            forall |i: int| 0 <= i < s.len() ==> #[trigger] s[i] + 2 > 2,
    {
        assert forall |i: int| 0 <= i < s.len() implies s[i] + 2 > 2  by {
            assert(s[i] + 2 > 2) by {
                assert(forall |i: int| 0 <= i < s.len() ==> #[trigger] is_positive(s[i]));
            };
        };
    }
}
```

Context
```
verus! {
    spec fn is_positive(i: int) -> bool {
        i > 0
    }
}
```

