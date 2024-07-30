#[allow(unused_imports)]
use vstd::prelude::*;

fn main() {}

verus!{
spec fn f(seq: Seq<u64>, i: int) -> bool {
    seq[i] == i + 2
}

fn get_element_check_property(arr: Vec<u64>, i: usize) -> (ret: u64)
    ensures
        ret == i + 2,
        ret == arr@[i as int],
{
    proof {
        assert(f(arr@, i as int));
    }
    arr[i]
}
}
