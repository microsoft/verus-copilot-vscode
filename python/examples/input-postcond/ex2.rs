Failed post-condition
```
Line 15-15:
        ret == (exists |k:usize| 2 <= k < n && is_ten_times(n, k)),
```
Failed location
```
Line 26-26:
        return true;
```

Code
```
use vstd::prelude::*;
fn main() {}

verus! {

spec fn is_ten_times(n: usize, k: usize) -> bool {
    n == 10 * k
}

fn while_loop(n: usize) -> (ret: bool)
    requires
        n >= 2,
        n <= 1000,
    ensures
        ret == (exists |k:usize| 2 <= k < n && is_ten_times(n, k)),
{
    let mut i = 2;
    while i < n
        invariant
            i <= n,
            n <= 1000,
            n >= 2,
            i >= 2,
    {
      if (n == 10 * i) {
        return true;
      }
      i += 1;
    }
    false
}

}
```