use vstd::prelude::*;
fn main() {}
verus!{
pub fn myfun(a: &mut Vec<i32>, N: i32)
{
    let mut i: usize = 0;

    while (i < N as usize)
        invariant 
            N > 0,
            N < 100,
            0 <= i <= N,
            a.len() == N,
            forall |k:int| 0 <= k < i ==> a[k] == 0,
    {
        a.set(i, 0);
        i = i + 1;
    }

    i = 0;
    while (i < N as usize)
        invariant
            0 <= i <= N,
            a.len() == N,
            N > 0,
            N < 100,
            forall |k:int| 0 <= k < i ==> (N as usize % 2 == 0 && a[k] == 2) || (N as usize % 2 != 0 && a[k] == 1),
            forall |k:int| i <= k < N ==> a[k] == 0,
    {
        if (N as usize % 2 == 0) {
            a.set(i, a[i] + 2);
        } else {
            a.set(i, a[i] + 1);
        }
        i = i + 1;
    }
}
}