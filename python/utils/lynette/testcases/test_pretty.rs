#[allow(unused_imports)]
use vstd::prelude::*;
fn main() {}
 
verus! {
    fn fibonacci(n: usize) -> (ret: Vec<i32>)
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
}

fn foo() {}
fn bar() {}
