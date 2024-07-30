use vstd::prelude::*;

verus! {

    fn main() {

        let mut i = 0;
        let mut j = 0; 
        let a = 10;

        while i < 10
            invariant
                0<= i,
                a == 10, 
        {
            while j < 50
                invariant
                    0 <= j,
                    j < 100,
            {
                j = j + i + a; 
            }
            i = i + 1;
        }
    }
}
