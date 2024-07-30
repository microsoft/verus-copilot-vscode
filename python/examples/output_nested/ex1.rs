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
                0 <= j, //Copied from inner loop
                j < 100, //Copied from inner loop
        {
            while j < 50
                invariant
                    i < 10, //Outer loop's loop condition
                    0 <= i, //Copied from outter loop
                    a == 10, //Copied from outter loop
                    0 <= j,
                    j < 100,
            {
                j = j + i + a; 
            }
            i = i + 1;
        }
    }
}
