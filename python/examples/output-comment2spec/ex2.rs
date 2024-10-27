/*
 * precondition: vector v's not empty; every element in v is smaller than 10; 
 * postcondition: every element in result vector R is larger than 20; the length of R is the same as the length of v
 *  requires
 *      v@.len()>0,
 *      forall |i:int| 0<= i < v@.len() ==> v[i as int] < 10,
 *  ensures
 *      forall |i:int| 0<= i < R@.len() ==> R[i as int] > 20,
 *      R@.len() == v@.len(),
 */
