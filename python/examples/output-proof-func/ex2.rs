{
    "triangle_is_monotonic": "proof fn triangle_is_monotonic(i: nat, j: nat)\n    requires\n        i <= j,\n    ensures\n        triangle(i) <= triangle(j),\n    decreases j\n{\n    if i < j {\n        triangle_is_monotonic(i, (j - 1) as nat);\n    }\n}"
}