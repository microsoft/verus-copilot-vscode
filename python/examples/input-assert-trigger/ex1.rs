Failed assertion
```
Line 18-18:
        assert(s[3] % 2 == 0);
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
            4 <= s.len(),
            forall |i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i]),
        ensures
            s[3] % 2 == 0,
    {
        assert(s[3] % 2 == 0) by {
            assert(forall |i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i]));
        };
    }
}
```

Context
```
verus! {
    spec fn is_even(i: int) -> bool {
        i % 2 == 0
    }
}
```


