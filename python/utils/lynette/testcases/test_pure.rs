#[allow(unused_imports)]
use vstd::prelude::*;
fn main() {}
fn fibonacci_pure(n: usize) -> (ret: Vec<i32>)
    {
        let mut fib = Vec::new();
        fib.push(0);
        fib.push(1);
        let mut i = 2;
        while i < n
        {
            let next_fib = fib[i - 1] + fib[i - 2];
            fib.push(next_fib);
            i += 1;
        }
        fib
    }

verus! {
 
    spec fn fibo(n: nat) -> nat
    decreases n
    {
        if n == 0 { 0 } else if n == 1 { 1 }
        else { fibo((n - 2) as nat) + fibo((n - 1) as nat) }
    }
 
    spec fn fibo_fits_i32(n: nat) -> bool {
        fibo(n) < 0x8000_0000
    }
 
    proof fn fibo_nondec(n: nat)
    requires
        n > 0,
    ensures
        fibo(n) >= fibo(n - 1),
    decreases n
    {
        if n > 1 {
            fibo_nondec(n - 1);
        }
    }
 
    fn fibonacci(n: usize) -> (ret: Vec<i32>)
    requires
        fibo_fits_i32(n as nat),
        n >= 2,
    ensures
        forall |i: int| 2 <= i < n ==> #[trigger]ret@[i] == ret@[i-1] + ret@[i - 2],
        ret@.len() == n,
    {
        let mut fib = Vec::new();
        fib.push(0);
        fib.push(1);
        let mut i = 2;
        while i < n
        invariant
            2 <= i <= n,
            fib@.len() == i,
            forall |j: int| 2 <= j < i ==> #[trigger]fib@[j] == fib@[j - 1] + fib@[j - 2],
            fibo_fits_i32((i-1) as nat), 
            fib[0] == fibo(0) as i32, fib[1] == fibo(1) as i32,
            forall |j: int| 2 <= j < i ==> #[trigger] fib[j] == fibo(j as nat) as i32
        {
            proof {
                fibo_nondec((i - 1) as nat);
            }
            let next_fib = fib[i - 1] + fib[i - 2];
            assert(next_fib == fibo((i - 1) as nat) as i32 + fibo((i - 2) as nat) as i32) by {
                assert(fib[i - 1] == fibo((i - 1) as nat) as i32);
                assert(fib[i - 2] == fibo((i - 2) as nat) as i32);
            };
            fib.push(next_fib);
            i += 1;
        }
        fib
    }
}
