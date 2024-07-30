use vstd::multiset::Multiset;
use vstd::prelude::*;
fn main() {}

verus! {

spec fn sorted_between(a: Seq<u32>, from: int, to: int) -> bool {
    forall|i: int, j: int| from <= i < j < to ==> a[i] <= a[j]
}

spec fn multiset_from_seq<T>(input: Seq<T>) -> Multiset<T>
    decreases input.len(),
{
    if input.len() == 0 {
        Multiset::empty()
    } else {
        multiset_from_seq(input.drop_last()).insert(input.last())
    }
}

fn test1(nums: &mut Vec<u32>)
    ensures
        sorted_between(nums@, 0, nums@.len() as int),
        multiset_from_seq(old(nums)@) === multiset_from_seq(nums@),
{
    let n = nums.len();
    let mut i = 0;
    while i < n
        invariant
            0 <= i,
            i <= n,
            sorted_between(nums@, 0, i as int),
            multiset_from_seq(old(nums)@.subrange(0, i as int)) === multiset_from_seq(
                nums@.subrange(0, i as int),
            ),
    {
        let mut j = i;
        while j > 0
            invariant
                0 <= j,
                j <= i,
                i <= n,
                sorted_between(nums@, 0, j as int),
                multiset_from_seq(old(nums)@.subrange(0, i as int)) === multiset_from_seq(
                    nums@.subrange(0, i as int),
                ),
        {
            if nums[j - 1] > nums[j] {
                let temp = nums[j - 1];
                nums.set(j - 1, nums[j]);
                nums.set(j, temp);
            }
            j = j - 1;
        }
        i = i + 1;
    }
}

} // verus!
