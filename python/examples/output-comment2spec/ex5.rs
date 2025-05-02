/*
 * Precondition:
 * - The input is positive
 * Postcondition:
 * - If the input is an even number, the function returns `Some(i)' where `i' is half of the input
 * - If the input is an odd number, the function returns `None'
 *
 *
 * fn half (x: u32) -> (result: Option<u32>)
 * requires
 *      x > 0,
 * ensures
 *      match result {
 *          Some(i) => x == i * 2,
 *          None => x % 2 == 1,
 *      },
 *
 */
