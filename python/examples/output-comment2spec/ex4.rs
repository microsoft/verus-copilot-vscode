//fn foo(v: &Vec<u8>) -> (ret:u8)
//precondition: the lenth of v is larger than 0
//postcondition: the returned value is a valid index of v and points to a positive element
//  requires
//      v@.len() > 0,
//  ensures
//      0 <= ret < v@.len(),
//      v[ret as int] > 0,
