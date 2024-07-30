#[allow(unused_imports)]
use vstd::prelude::*;

fn main() {}

verus!{


fn get_element_check_property(arr: Vec<u64>, i: usize) -> (ret: u64)
    requires
        0<= i < 100,
        arr.len() == 100,
{
    assert(0<=i<100);
    assert(arr.len() == 100);
    arr[i]
}
}
