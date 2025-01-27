Failed assertion
```
Line 28-28:
    assert(ret == 11 * m); //reflects one of the function post-condition
```

Code
```
use vstd::prelude::*;
fn main() {}

verus! {

spec fn is_ten_times_and_big (n: int, k: int) -> bool {
    &&& n > 100
    &&& k > 100
    &&& n == 10 * k
}

fn myfun(n: usize, m: usize) -> (ret: usize)
    requires
        0 < n < 10000,
        0 < m < 10000,
        is_ten_times_and_big(n + 10, m + 1),
    ensures
    ({
        let x = n;
        let y = m;
        &&& ret > 0
        &&& ret > n 
        &&& ret == 11 * m
    })
{
    let ret =  n + m;

    assert(ret == 11 * m); //reflects one of the function post-condition

    ret
}

}
```
