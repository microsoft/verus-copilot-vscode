{
    "proof_lemma_multiset_count": "proof fn proof_lemma_multiset_count<T>(input: Seq<T>, i: int)\n    requires\n        0 <= i < input.len(),\n    ensures\n        multiset_from_seq(input).count(input[i]) > 0,\n    decreases\n        input.len(),\n    {\n        let input_no_last = input.drop_last();\n        let c = multiset_from_seq(input).count(input[i]);\n        if i < (input.len() - 1) {\n            proof_lemma_multiset_count(input.drop_last(), i);\n            assert(c >= multiset_from_seq(input_no_last).count(input[i]));\n        } else {\n            assert(c == multiset_from_seq(input_no_last).count(input[i]) + 1);\n        }\n    }",
    "proof_lemma_multiset_insert": "proof fn proof_lemma_multiset_insert<T>(input: Seq<T>, i: int, v: T)\n    requires\n        0 <= i < input.len(),\n    ensures\n        multiset_from_seq(input.update(i, v)).ext_equal(multiset_from_seq(input).remove(input[i]).insert(v)),\n    decreases\n        input.len(),\n    {\n        let ret1 = multiset_from_seq(input.update(i, v));\n        let ret2 = multiset_from_seq(input);\n        let input_no_last = input.drop_last();\n        let ret1_no_last = multiset_from_seq(input_no_last.update(i, v));\n        let ret2_no_last = multiset_from_seq(input_no_last);\n        let last = input.last();\n        if i < input.len() - 1 {\n            proof_lemma_multiset_insert(input_no_last, i, v);\n            assert(ret2 === ret2_no_last.insert(last));\n            let input_update_no_last = input.update(i, v).drop_last();\n            assert(input_update_no_last.ext_equal(input_no_last.update(i, v)));\n            assert(ret1_no_last === ret2_no_last.remove(input[i]).insert(v));\n            assert(ret1 === ret1_no_last.insert(last));\n            assert(ret1.ext_equal(ret2_no_last.remove(input[i]).insert(v).insert(last)));\n            let ret2_remove_insert = ret2.remove(input[i]).insert(v);\n            assert(ret1.ext_equal(ret2_remove_insert)) by {\n                assert forall |w: T| ret1.count(w) == ret2_remove_insert.count(w)\n                by {\n                    let input_op: int = if (input[i] === w) {1} else {0};\n                    let v_op: int = if (v === w) {1} else {0};\n                    let last_op: int = if last === w {1}else {0};\n                    assert(ret2.remove(input[i]).count(w) + v_op == ret2_remove_insert.count(w));\n                    assert(ret2.count(input[i]) > 0 ) by {\n                        proof_lemma_multiset_count(input, i);\n                    }\n                    assert(ret2.count(w) - input_op == ret2.remove(input[i]).count(w));\n                    assert(ret2.count(w) == ret2_no_last.count(w) + last_op);\n                    assert(ret2_no_last.count(input[i]) > 0) by {\n                        proof_lemma_multiset_count(input_no_last, i);\n                    }\n                    assert(ret2_no_last.remove(input[i]).count(w) == ret2_no_last.count(w) - input_op);\n                    assert(ret2_no_last.remove(input[i]).insert(v).count(w) == ret2_no_last.remove(input[i]).count(w) + v_op);\n                    assert(ret1.count(w) == ret2_no_last.remove(input[i]).insert(v).count(w) + last_op);\n                }\n            }\n        } else {\n            assert(input.update(i, v).drop_last().ext_equal(input_no_last));\n            assert(ret1 === ret2_no_last.insert(v));\n            assert(ret2 === ret2_no_last.insert(input[i]));\n        }\n    }"
}