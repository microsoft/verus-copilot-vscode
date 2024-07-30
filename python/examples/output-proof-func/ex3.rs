{
    "seq_to_set_rec_contains": "proof fn seq_to_set_rec_contains<A>(seq: Seq<A>)\n    ensures forall |a| #[trigger] seq.contains(a) <==> seq_to_set_rec(seq).contains(a)\n    decreases seq.len()\n{\n    if seq.len() > 0 {\n        assert(forall |a| #[trigger] seq.drop_last().contains(a) <==> seq_to_set_rec(seq.drop_last()).contains(a)) by {\n            seq_to_set_rec_contains(seq.drop_last());\n        }\n\n        assert(seq.ext_equal(seq.drop_last().push(seq.last())));\n        assert forall |a| #[trigger] seq.contains(a) <==> seq_to_set_rec(seq).contains(a) by {\n            if !seq.drop_last().contains(a) {\n                if a == seq.last() {\n                    assert(seq.contains(a));\n                    assert(seq_to_set_rec(seq).contains(a));\n                } else {\n                    assert(!seq_to_set_rec(seq).contains(a));\n                }\n            }\n        }\n    }\n}",
    "seq_to_set_equal_rec": "proof fn seq_to_set_equal_rec<A>(seq: Seq<A>)\n    ensures seq.to_set() == seq_to_set_rec(seq)\n{\n    assert(forall |n| #[trigger] seq.contains(n) <==> seq_to_set_rec(seq).contains(n)) by {\n        seq_to_set_rec_contains(seq);\n    }\n    assert(forall |n| #[trigger] seq.contains(n) <==> seq.to_set().contains(n));\n    assert(seq.to_set().ext_equal(seq_to_set_rec(seq)));\n}",
    "lemma_seq_push_to_set_insert": "proof fn lemma_seq_push_to_set_insert<T>(s: Seq<T>, val: T)\nensures\n    s.push(val).to_set() === s.to_set().insert(val),\n{\n    seq_to_set_equal_rec(s.push(val));\n    assert(s.ext_equal(s.push(val).drop_last()));\n    seq_to_set_equal_rec(s);\n    assert(s.push(val).to_set() === seq_to_set_rec(s.push(val)));\n    assert(s.push(val).to_set() === seq_to_set_rec(s.push(val).drop_last()).insert(val));\n}"
}