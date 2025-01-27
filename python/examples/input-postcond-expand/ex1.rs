Failed post-condition
```
Line 20-20:
        &&& ret < x + y
```
Failed location
```
Line 23-25:
{
    10 * n
}
```

Code
```
use vstd::prelude::*;
fn main() {}

verus! {

spec fn is_ten_times(n: usize, k: usize) -> bool {
    n == 10 * k
}

fn myfun(n: usize) -> (ret: usize)
    requires
        0 < n < 100,
    ensures
    ({
        let x = 2 * n;
        let y = 3 * n;
        let z = n + 1;
        &&& ret > 0
        &&& ret > x + z
        &&& ret < x + y
        &&& is_ten_times(ret, x as usize)
    })
{
    let ret = 10 * n;
    ret
}

}
```
