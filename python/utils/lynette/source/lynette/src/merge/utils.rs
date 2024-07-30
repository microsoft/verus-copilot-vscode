use crate::utils::*;

pub(super) fn iter_idx_or_err<T, U>(iter: &mut std::iter::Peekable<T>, err_msg: &str) -> Result<usize, Error>
where
    T: Iterator<Item = (usize, U)>,
{
    iter.peek().map(|&(idx, _)| idx).ok_or(Error::Conflict(String::from(err_msg)))
}

pub(super) fn iter_idx_or<T, U>(iter: &mut std::iter::Peekable<T>, default: usize) -> usize
where
    T: Iterator<Item = (usize, U)>,
{
    iter.peek().map(|&(idx, _)| idx).unwrap_or(default)
}

/// If a, b, c are equal, return default. Otherwise, return Conflict error.
pub(super) fn eq_or_conflict_3<T: PartialEq, U, F>(
    a: &T,
    b: &T,
    c: &T,
    err_msg: &str,
    default: F,
) -> Result<U, Error>
where
    F: FnOnce() -> U,
{
    if !(a == b && a == c) {
        Err(Error::Conflict(String::from(err_msg)))
    } else {
        Ok(default())
    }
}

pub(super) fn lcs<'a, T: PartialEq>(a: &'a [T], b: &'a [T]) -> Vec<&'a T> {
    let mut dp = vec![vec![0; b.len() + 1]; a.len() + 1];

    for i in 0..a.len() {
        for j in 0..b.len() {
            if a[i] == b[j] {
                dp[i + 1][j + 1] = dp[i][j] + 1;
            } else {
                dp[i + 1][j + 1] = std::cmp::max(dp[i + 1][j], dp[i][j + 1]);
            }
        }
    }

    let mut ret = Vec::new();
    let (mut i, mut j) = (a.len(), b.len());

    while i > 0 && j > 0 {
        if a[i - 1] == b[j - 1] {
            ret.push(&a[i - 1]);
            i -= 1;
            j -= 1;
        } else if dp[i - 1][j] > dp[i][j - 1] {
            i -= 1;
        } else {
            j -= 1;
        }
    }

    ret.reverse();

    ret
}