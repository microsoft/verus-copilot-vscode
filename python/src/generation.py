import os
import re
import json
import time
from pathlib import Path
from infer import LLM
from houdini import houdini
from refinement import Refinement
from veval import VEval, EvalScore
from utils import evaluate, code_change_is_safe, compare_and_choose_by_loop, merge_outputs, choose_best, proved_by_verus, merge_with_highlight, merge_with_highlight_post, get_aritherror, is_preconderr_only, remove_redundant_loopinv, process_precondition_error, check_syntaxerr_inv, remove_redundant_req, clean_code, get_func_body, get_nonlinear_lines

class Generation:
    def __init__(self, config, logger, phase1_examples=["3", "6", "7"], repair_uniform=False):
        self.config = config
        self.llm = LLM(config, logger)
        self.logger = logger
        self.refine_funcs = [
            self.constantrefine_inference,
            self.arraylen_inference,
            self.bound2check_inference,
            self.arrayrefine_inference,
            self.condlooprefine_inference,
            self.breakloop_inference,
            self.nonlinear_inference,
            self.nonlbound_inference,
        ]
        self.default_refine_funcs = [
            self.constantrefine_inference,
            self.arraylen_inference,
            self.arrayrefine_inference,
            self.condlooprefine_inference,
        ]
        self.simple_refine_funcs = [
            self.constantrefine_inference,
        ]
        self.refine_no_merge = [2, 4, 5] 
        self.refine_prefer_no_change = [3]
        self.hdn = houdini(config)
        #TODO: I suspect we can merge infer_funcs w/ refine_funcs later
        self.infer_funcs = [
            self.direct_inference,
            self.constantrefine_inference,
            self.arraylen_inference,
            self.arrayrefine_inference,
            self.condlooprefine_inference,
        ]
        self.refinement = Refinement(config, logger)
        self.phase1_examples = phase1_examples
        self.repair_uniform = repair_uniform

        self.logger.warning("Generation initialized with phase1_examples: %s", self.phase1_examples)
        self.logger.warning("Generation initialized with repair_uniform: %s", self.repair_uniform)


    def direct_full_inference(self, code, temp=0, answer_num=1, error="", use_simple=True, use_misc_examples=True):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        complex_instruction = """Your missions are to
1. Add loop invariants to the given Rust code, if there are loops in the code, so that Verus can verify the give function behaves exact what is described in the specifications
2. Add the proof blocks that could help Verus to prove the following code snippet. You need to analyze which locations in the code need to be proved and add the proof blocks to help Verus to prove the correctness of the code. You can insert multiple proof blocks in the code as long as they are necessary to prove the correctness of the code. You can also include new ghost variables that could help you to prove the correctness of the code.

Here are some principles that you have to follow:
Respond with the Rust code only, do not include any explanation.
If a function is marked with unimplemented!(), please leave it there and do NOT try to add new implementation.
You should never change or delete any existing code.
If this function contains no loop, feel free to leave it as it is without adding anything.

Please follow these steps in adding loop invariants for every loop:
1. You should identify every variable that is read in the loop  (e.g., x[k], y), particularly for array elements like x[k], and add an invariant about the initial value for EACH such variable and array;
2. You should identify every variable that is written (e.g., y = ..., x.set(..,..)) in every loop, and add an invariant about the value of that variable. Even if an invariant is already specified earlier in the program, please do repeat it in every loop suitable. Copy them in the response.
3. You should fully utilize the spec functions and proof functions in the invariant.

Here are some common locations where you can add proof blocks:
1. In the beginning of the function
2. Before the loop
3. In the beginning of the loop
4. In the end of the loop
5. Before the key operations
6. After the key operations

The proof block looks like this:
```
proof {
    // your proof code here
    // assert(...)
    // LEMMA_FUNCTION(...)
    // ...
} // Added by AI
```
The ghost variable looks like this:
```
let ghost ...; // Added by AI
```

If there is nothing to add for a function, that is OK. 
"""
        simple_instruction = """Please generate loop invariants and proof blocks for the given Rust code, so that Verus can verify the give function behaves exact what is described in the specifications. 

Respond with the Rust code only, do not include any explanation.
"""

        if use_simple:
            self.logger.warning("Using simple instruction ...")
            instruction = simple_instruction
        else:
            self.logger.warning("Using complex instruction ...")
            instruction = complex_instruction

        examples = []
        if use_misc_examples:
            for f in sorted(os.listdir(os.path.join(self.config.example_path, "input-temp"))):
                if f.endswith(".rs") and f.startswith("ex"):
                    input_file = os.path.join(self.config.example_path, "input-temp", f)
                    output_file = os.path.join(self.config.example_path, "output-temp", f)
                    input_content = open(input_file).read()
                    output_content = open(output_file).read()
                    examples.append({"query": input_content, "answer": output_content})
        else:
            for f in sorted(os.listdir(os.path.join(self.config.example_path, "input"))):
                if f.endswith(".rs") and f[2] in self.phase1_examples:
                    input_file = os.path.join(self.config.example_path, "input", f)
                    output_file = os.path.join(self.config.example_path, "output", f)
                    input_content = open(input_file).read()
                    output_content = open(output_file).read()
                    examples.append({"query": input_content, "answer": output_content})
        with open("example.log", "w") as f:
            for ex in examples:
                f.write(ex["query"] + "\n")
                f.write(ex["answer"] + "\n\n")

        self.logger.info("Direct Full Inference ...")
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

    def direct_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

#I changed the instruction so that 
#1. it is only about adding loop invariants but not asserts 
#2. I deleted "You should never change the requires and ensures code blocks at the beginning of the function.", as this is needed for my inter-procedural.
#3. I split the array length invariant out of the original direct_inference 
#
#The following is deleted, as it is not needed for intra_procedure:
#  If a function is marked with unimplemented!(), please leave it there and do NOT try to add new implementation.
#
#   
#  Copy them in the response.
#  If there is nothing to add for a function, that is OK. 

        instruction = """Your mission is to add loop invariants to the given Rust code, if there are loops in the code, so that Verus can verify the give function behaves exact what is described in the specifications. 

Here are some principles that you have to follow:
Respond with Rust code only, do not include any explanation.
You should never change or delete existing Rust code.

Please follow these steps in adding loop invariants for every loop:
1. You should identify every variable that is read in the loop  (e.g., x[k], y), particularly for array elements like x[k], and add an invariant about the initial value for EACH such variable and array;
2. You should identify every variable that is written (e.g., y = ..., x.set(..,..)) in every loop, and add an invariant about the value of that variable. Even if an invariant is already specified earlier in the program, please do repeat it in every loop suitable.
3. You can leverage the spec functions and proof functions in the invariant.
"""
        # Integrate the Seq knowledge if needed
        instruction += self.refinement.add_seq_knowledge(code, instruction)

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input"))):
            if f.endswith(".rs") and f[2] in self.phase1_examples:
                input_file = os.path.join(self.config.example_path, "input", f)
                output_file = os.path.join(self.config.example_path, "output", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)
    
    def direct_inference_with_refinement(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """
## Step 1: Add Loop Invariants
Your mission is to add loop invariants to the given Rust code, if there are loops in the code, so that Verus can verify the give function behaves exact what is described in the specifications.

Here are some principles that you have to follow:
Respond with Rust code only, do not include any explanation.
You should never change or delete existing Rust code.

Please follow these steps in adding loop invariants for every loop:
1. You should identify every variable that is read in the loop  (e.g., x[k], y), particularly for array elements like x[k], and add an invariant about the initial value for EACH such variable and array;
2. You should identify every variable that is written (e.g., y = ..., x.set(..,..)) in every loop, and add an invariant about the value of that variable. Even if an invariant is already specified earlier in the program, please do repeat it in every loop suitable.
3. You can leverage the spec functions and proof functions in the invariant.

## Step 2: Constant propagation refinement

If an upper bound or a lower bound about a constant function parameter (e.g., X < ..., X > ...) is provided in the function pre-condition (i.e., in the `requires' code block at the beginning of the function), 
please copy that (e.g., X < 10, X > 5) as a loop invariant to every loop in the function. 
Even if an invariant is already specified earlier in the program, please do repeat it in every loop suitable.

## Step 3: Array length refinement

For every loop in the function, please identify every array that is read (e.g., x[k]) or written (e.g., x.set(..,..)) in it, and then add a loop invariant that specifies the length of the array (i.e., x.len() == ...).

## Step 4: Quantifier range refinement

Please take the following steps to check every loop invariant that involves an array (e.g., x[k]) in the given Rust code:
If this array x[k] has been modified in this loop through x.set(), leave this invariant as it is, do NOT make any changes, and move on to the next invariant. 
Otherwise, when there is no x.set() in the loop, please make sure that the invariant covers every element in the array and hence has the form like `forall |k:int| 0<= k < x.len() ==> whatever-property'. When you make this change, please use a comment to explain why you believe the related array is never changed in the loop. Do NOT make any other changes to the code or the loop invariant!

## Step 5: Conditional loop invariant refinement

Your mission is to refine some loop invariants in the given Rust code only if the loop has special handling for the first iteration. This is what you should do: if an existing loop invariant P holds for all iterations of the loop except for the first iteration (e.g., some variable updates may only (not) occur during the first loop iteration), please leave P as it is and add another loop invariant conditioned on the loop index (e.g., index > 0 ==> P), following the example below. 
Do not change P or any other loop invariants in any other way."""

        self.logger.warning("Direct Inference unified with Refinement ...")

        # Integrate the Seq knowledge if needed
        instruction += self.refinement.add_seq_knowledge(code, instruction)

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input"))):
            if f.endswith(".rs") and f[2] in self.phase1_examples:
                input_file = os.path.join(self.config.example_path, "input", f)
                output_file = os.path.join(self.config.example_path, "output", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

    def arraylen_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """
        For every loop in the function, please identify every array that is read (e.g., x[k]) or written (e.g., x.set(..,..)) in it, and then add a loop invariant that specifies the length of the array (i.e., x.len() == ...).

Here are some principles that you have to follow:
 You should only response with Rust code, and not include any explanation. 
 You should not make any other changes to the program.
"""
        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)




    def whether_nonlinear_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to determine whether this code needs non-linear assertions to help Verus prove the correctness of the code. In Verus, nonlinear arithmetic about integers are very difficult (or expensive) to reason about fully automatically. Nonlinear arithmetic involves equations that multiply, divide, or take the remainder of integer variables (e.g., x * (y * z) == (x * y) * z). Given a code snippet, you should analyze whether there is any nonlinear arithmetic in the code. Hint: you can refer to the ensures clause, if there is any nonlinear arithmetic (e.g., x*x is nonlinear, while 2*N is not) in the ensures clause, then you nonlinear assertions is needed. Even though there is only addition operation is the code. Response with json format like this: {"reason": the reason why you think this code needs or doesn't need nonlinear assertions, "result": true/false}"""

        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp, json=True)


    def condlooprefine_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one checks if any loop invariant should be made to be conditional on loop indx, particularly if the invariant holds for all but the first interation of the loop.

        In terms of error fixing:
        ** If Verus complains that an array-related loop invariant does not hold before the loop, 
        we can try this refinement. 
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to refine some loop invariants in the given Rust code only if the loop has special handling for the first iteration. This is what you should do: if an existing loop invariant P holds for all iterations of the loop except for the first iteration (e.g., some variable updates may only (not) occur during the first loop iteration), please leave P as it is and add another loop invariant conditioned on the loop index (e.g., index > 0 ==> P), following the example below. 
Do not change P or any other loop invariants in any other way. """

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input-condinv"))):
            if f.endswith(".rs"):
                input_file = os.path.join(self.config.example_path, "input-condinv", f)
                output_file = os.path.join(self.config.example_path, "output-condinv", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})


        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)


    def arrayrefine_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one checks if an array-related loop invariant has the right range clause:
        if the array was not modified in the loop, the range clause should be 0<= .. <array.len()
        otherwise, the range clause should be 0<= .. <i or i<= .. <array.len()

        In terms of error fixing:
        ** If Verus complains that an array-related loop invariant does not hold after the loop, 
        we can check whether this array is actually not modified and hence should use [0, array.len) clause. 
        or if this array is actually modified and hence should NOT use [0, array.len) clause.
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Please take the following steps to check every loop invariant that involves an array (e.g., x[k]) in the given Rust code:
        If this array x[k] has been modified in this loop through x.set(), leave this invariant as it is, do NOT make any changes, and move on to the next invariant. 
        Otherwise, when there is no x.set() in the loop, please make sure that the invariant covers every element in the array and hence has the form like `forall |k:int| 0<= k < x.len() ==> whatever-property'. When you make this change, please use a comment to explain why you believe the related array is never changed in the loop. Do NOT make any other changes to the code or the loop invariant!

You should only response with Rust code, and not include any explanation.
You should NEVER ever add new variables, NEVER!
You should only make changes to existing loop invariants in the following ways, and you should not make any other changes to the program.
"""
        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)


    def constantrefine_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one checks if any constant parameter related invariant is missing.

        In terms of error fixing:
        ** If Verus complains about arithmetic overflow,
        we can run this refinement. 
        """


        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """
If an upper bound or a lower bound about a constant function parameter (e.g., X < ..., X > ...) is provided in the function pre-condition (i.e., in the `requires' code block at the beginning of the function), 
please copy that (e.g., X < 10, X > 5) as a loop invariant to every loop in the function. 
Even if an invariant is already specified earlier in the program, please do repeat it in every loop suitable.

Here are some principles that you have to follow:
 You should only response with Rust code, and not include any explanation. 
 You should not make any other changes to the program.
"""

        examples = []
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)


    def nonlinear_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one checks if any loop invariant is related to a non-linear property. 

        In terms of error fixing:
        ** If any invariant is non-linear ...
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add assert statements into the given Rust function to help Verus prove non-linear properties.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should only add assertions with non-linear property if necessary in the following ways, and you should not make any other changes to the program.

Nonlinear arithmetic involves equations that multiply, divide, or take the remainder of integer variables (e.g., x * (y * z) == (x * y) * z). Verus can reason about nonlinear arithmetic, but it needs to be told when to do so. To do this, you need to add a special keyword `nonlinear_arith' to the assert statement.
For example, if we know that variable X equals k*k+2*k and that variable Y equals (k+1)*(k+1), to prove that X+1 equals Y, we have to write the following statement to help Verus:

    assert(X+1 == Y) by (nonlinear_arith)
        requires
            X == k*k+2*k,
            Y == (k+1)*(k+1),
            0 < k,
            k < N,
            N <= 300,
            {}

In this example, the `nonlinear_arith' would enable Verus to use its non-linear reasoning to prove X+1 equals Y. The requires statements should include all the information that is needed to reason about the assert statement, including any variable bound information that is need to prove no-arithmetic overflow.

Please check the given program, and add nonlinear_arith assertion when Verus needs to reason about non-linear properties."""

        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)

    def breakloop_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one should be applied to loops that have early breaks 
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """The break keyword serves as another way to prematurely exit a loop, but it carries a slight complication in terms of loop specifications. Unlike simple while loops whose loop conditions must only be false upon exiting, loops with a break command can exit regardless of whether the loop condition is true or not. Code including break commands are expected to explicitly specify post-loop conditions using ensures clause. Take a look at the example below about how to add `ensures` clause for a loop with break, and then add `ensures' clause for any loop that contains break in the provided code accordingly. If a loop does not have break in it, please do NOT make any changes.

You should only response with Rust code, and not include any explanation.
"""
        examples = self.refinement.get_examples("loopbreak")

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)



    def nonlbound_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one is to add bound for any nonlinear expressions.

        In terms of error fixing:
        ** arithmetic overflow
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add assertions with `nonlinear_arith' keyword in the given Rust function to help Verus prove there is no arithmetic overflow for any non-linear expressions.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should only add assertions with non-linear property in the following ways, and you should not make any other changes to the program. Do not delete any existing assertions.

Verus cannot prove that a non-linear expression does not overflow unless you tell it the range of the expression.
For example, if a non-linear expression x*x*x is used in the program, only tell Verus 0 <= x <= 10 is not enough, we have to write the following statement to help Verus prove no arithmetic overflow for x*x*x:

    assert(0 < x*x*x <= 10 * 10 * 10) by (nonlinear_arith)
        requires
            0 < x,
            x <= 10,
            {}

In this example, the `nonlinear_arith' keyword enables Verus to use its non-linear reasoning, and 
the `requires' statements should include all the variable bound information needed to prove no-arithmetic overflow.

Please check the given program, and add above nonlinear_arith assertions when needed. Note that both the lower bound and upper bound of the expression should be specified in the assertion.
"""

        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)
    

    def bound2check_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one is to double check if we have missed any loop invariant, particularly the ones related to bounds. 

        In terms of error fixing:
        ** arithmetic overflow
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add any missing loop invariants to help Verus verify the given code behaves exact what is described in the specifications.
Particularly, make sure that any non-array variable, used in a loop has BOTH its lower bound and upper bound specified as loop invariants. Especially for the loop variable `i', make sure that its lower bound (e.g., x if `i' is initialized as x before the loop) and upper bound (e.g., N) are specified as loop invariants.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should never EVER add new variables, NEVER!
You should not delete any code in the program.
"""

        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)

    #to fix old related errors
    def oldrefine_inference(self, code, temp=0, answer_num=1, error=""):
        """
        In terms of error fixing:
        **  
        """
 
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """If a loop invariant declares that the value of an array element equals its old value 
        (e.g., A[i] == old(A)[i]), please either replace that old(A)[i] with a concrete value (e.g., B, 10, etc.) or delete this loop invariant. 

You should only response with Rust code, and not include any explanation.
You should NEVER ever add new variables, NEVER!
You should only make changes to existing loop invariants in the following ways, and you should not make any other changes to the program.

"""
        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)

    #nested loop related invariants inference
    def nestedlooprefine_inference(self, code, temp=0, answer_num=1, error=""):
        """
        This one helps make sure there is no missing invariants in nested loops.

        In terms of error fixing:
        ** for any errors inside nested loops
        we can run this refinement. 
        """


        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """If the program contains nested loops, please add two types of invariants for the inner loop:

        (1) Check every invariant of the outter loop; if it is also an invariant for the inner loop, please copy it to the inner loop. 
        (2) Please copy the outerloop's loop condition as an invariant for the inner loop (e.g., if the outter loop is `while( x>10 && y<0)', then x>10 && y<0 is an invariant candidate for the inner loop. 

        We have to do this, because the outter loop's invariants are invisble to Verus when it reasons about the inner loop.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
If a function is marked with unimplemented!(), please leave it there and do NOT try to add new implementation.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.
If the code contains no nested loop, just leave it unchanged.
"""


        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_nested"))):
            if f.endswith(".rs") and f[2] in ["1"]:
                input_file = os.path.join(self.config.example_path, "input_nested", f)
                output_file = os.path.join(self.config.example_path, "output_nested", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=temp)


    #add loop invariants based on error messages
    def aritherror_inference(self, code, temp=0.2, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        if error=="":
            print("Aritherror_inference called without error input. To Abort ...")
            exit()

        errlinenum, errline, errexp = get_aritherror(error)
        if errlinenum == -1:
            print("Fail to extract arithmetic overflow errors from error message:")
            print(error)
            exit()
        

#TODO: this two instructions should both be used
        #instruction = "Verus reports an error for the statement " + errline + " in line " + errlinenum + " of the following program. Your mission is to add loop invariants so that Verus verification can go through. Specifically, Verus thinks there may be arithmetic overflow or underflow of the expression " + errexp +" in that statement. You can either specify a proper upper bound and a proper lower bound for this expression " + errexp + " as loop invariants, or you can specify lower bounds and upper bounds for every variable involved in this expression. After you add a loop invariant (e.g., E < 10000 as a new loop invariant), please also add an assert right before the loop (e.g., assert(E<10000)). Remember do NOT use Rust-style assert!(..). Please use Verus-style assert(...), without the exclamation mark. Please make sure you add loop invariant, not just assert." 

#Using Rust style assert! actually is good, as they can be removed by Houdini afterwards...
        instruction = "For each variable x involved in the expression `" + errexp + "' in line " + str(errlinenum) + " of the following program, please specify a constant lower bound (i.e. x> ...) and a constant upper bound (i.e., x < ...) as a loop invariant and an assert right before the loop (e.g., assert!(N)). If the program does not offer a bound, you can add a constant bound like 10000. Do not miss any variable in `" + errexp + ", and do NOT add bound information related to any other variables. Please do not change function post-conditions." 

        instruction += """
        Response requirements:
        Respond with the verus code only, do not include any explanation.
        You should only add loop invariants, and you should NOT make any other changes to the program.
        """

        examples = []
        #TODO: example 2 expresses bound for the whole expression
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input-aritherr"))):
            if f.endswith(".rs") and f[2] in ["1"]:
                input_file = os.path.join(self.config.example_path, "input-aritherr", f)
                output_file = os.path.join(self.config.example_path, "output-aritherr", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        print("\n[Error-guided inference] instruction:")
        print(instruction)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)


    ##Inter Procedural##
    def direct_spec_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add function pre- and post- conditions to the given Rust code in the form of `requires' (for pre-condition) and `ensures' (for post-condition), so that Verus can 
        (1) verify all loop invariants and assert specified in the function are guaranteed to be true. 
        (2) verify the post-condition is guaranteed to satisfy at the end of its execution whenever the pre-condition is satisfied at the beginning of the function, 
        (3) verify that there will be no arithmetic underflow or overflow in the function, 
        (4) verify that there will be no array index underflow or overflow in the function, 

        Keep in mind that, `requires' indicates what condition should be satisfied before the function's execution, and `ensures' indicates what should be true at the end of the function's execution. Please do not mix these two up.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
Please add `requires' and `ensures' at the beginning of every function.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.
Again, you should NEVER add new variables, NEVER!
"""

        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_spec"))):
            if f.endswith(".rs") and f[2] in ["1", "2", "3", "5"]:
                input_file = os.path.join(self.config.example_path, "input_spec", f)
                output_file = os.path.join(self.config.example_path, "output_spec", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

    #TODO: need parser support to reject changes beyond require clause
    def direct_require_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add function pre-conditions to the given Rust code in the form of `requires'.

        Your first task is to add `requires' to any implemented function, if it does not already have one.
        If you decide not to add `requires' to a function, please use comment to explain why.
        Do NOT add function post-conditions (i.e., `ensures')!

        Next, to figure out what pre-conditions to put under the `requires' block, please make sure that we 
        want to help Verus to
        (1) verify all loop invariants and assert specified in the function are guaranteed to be true. 
        (2) verify the post-condition is guaranteed to satisfy at the end of its execution whenever the pre-condition is satisfied at the beginning of the function, 
        (3) verify that there will be no arithmetic underflow or overflow in the function, 
        (4) verify that there will be no array index underflow or overflow in the function, 

        Keep in mind that, `requires' indicates what condition should be satisfied before the function's execution.


Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
Please add `requires' at the beginning of every function! This is a MUST!
You should NOT add any `ensures' for any function.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.
"""

        print ("Direct Require Inference ...")
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_require"))):
            if f.endswith(".rs") and f[2] in ["1", "3", "5"]:
                input_file = os.path.join(self.config.example_path, "input_require", f)
                output_file = os.path.join(self.config.example_path, "output_require", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)


    ##Inter Procedural##
    def spec2assert_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        if not error:
            instruction = """Your mission is to add assert statement right before each function call to reflect every 
            callee function's pre-condition. Specifically, every function's pre-condition is specified in the form of 
            `requires' at the beginning of the function. These pre-conditions must be satisfied before this function
            executes. You should identify every place a function (e.g., foo()) is called in the given Rust code, and
            add an assert statement right before the call site to reflect foo's pre-condition.

            Here are some principles that you have to follow:
            Response with the Rust code only, do not include any explanation.
            You should never EVER add new variables, NEVER!
            You should never change or delete any existing code.
            Again, you should NEVER add new variables, NEVER!
            """
        else:
            #Get detailed information about which exact function's which exact precondition is violated at which line
            self.logger.info("spec2assert infernece guided by error messages")

            err_calllnnum, err_call, err_prefun, err_precond = process_precondition_error(error, code)
            instruction = "Verus verification finds potential pre-condition violation(s) at some call site(s). Your mission is to add assert statement(s) right before those call site(s) to reflect those condition(s) that Verus failed to prove. Please do not add assertions that Verus does not complain about. Here is the list of potential violations:\n"

            for i, line in enumerate(err_calllnnum):
                instruction += "{}) the pre-condition ".format(i+1) + err_precond[i] + " of function prototype " + err_prefun[i] + " may be violated by the function invocation " + err_call[i] + " at line " + line + " of the input file;\n"

            instruction += """
            Here are some principles that you have to follow:
            Response with the Rust code only, do not include any explanation.
            You should never EVER add new variables, NEVER!
            You should never change or delete any existing code.
            Again, you should NEVER add new variables, NEVER!
            """
            print(instruction)

        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_spec2a"))):
            if f.endswith(".rs") and f[2] in ["1"]:
                input_file = os.path.join(self.config.example_path, "input_spec2a", f)
                output_file = os.path.join(self.config.example_path, "output_spec2a", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

#Please add loop invariants to reflect the assert inside the loop
    def assert2inv_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

#        instruction = """Your mission is to add loop invariants to the given Rust code so that Verus can prove every assert inside loops to be correct. Specifically, for every assert statement inside a loop like `assert!(E)', please add E as a loop invariant, inserted into the existing invariant block of the loop.

        instruction = """For every loop in the program, check if there exists any assert statement in it like `assert!(E)'. If there is, make sure that `E' is an invariant to that loop (you don't need to change E) and use a comment to explain the invariant you added, as shown by the example. If the assert is inside a nested loop, make sure that E is added as an invariant to every level of the loop. Please do NOT add any other loop invariants. If you choose not to turn an assert! statement into a loop invariant, please use comments to explain why. 

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.
Again, you should NEVER add new variables, NEVER!
"""

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_a2inv"))):
            if f.endswith(".rs") and f[2] in ["1"]:
                input_file = os.path.join(self.config.example_path, "input_a2inv", f)
                output_file = os.path.join(self.config.example_path, "output_a2inv", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})


        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

 
 #TODO: need parser support to make sure the changes are not beyond requires and ensures
#Please add `requires' and `ensures' at the beginning of every function.
     ##Inter Procedural##
    def assert2spec_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Your mission is to add function pre- or post- conditions to the given Rust code in the form of `requires' (for pre-condition) and `ensures' (for post-condition), so that Verus can prove every `assert' statement to be true. Specifically, pay attention to every assert statement, assert!(P), in the given code. If the correctness of P depends on the return value of an earlier function call (e.g., foo), please add a suitable post-condition (i.e., `ensures') for that function `foo', so that Verus can prove assert!(P) to succeed. If the correctness of an assert property P depends on the parameters of the function it is located in, please add a suitable pre-condition (i.e., `requires') for the function, so that Verus can prove assert!(P) to be always hold. Pleae do NOT add any pre-condition or post-conditio that is unnecessary. Keep in mind that pre-condition is guaranteed to satisfy when a function starts its execution; and the post-condition is guaranteed to satisfy when a function finishes its execution.
        If you decide not to add any pre-condition or post-condition for an assert, please explain why not using comments.
        Please do not add any pre-condition or post-condition that does not help to prove the correctness of an existing assert in the program!

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.
Again, you should NEVER add new variables, NEVER!
"""

        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_a2spec"))):
            if f.endswith(".rs") and f[2] in ["1", "2"]:
                input_file = os.path.join(self.config.example_path, "input_a2spec", f)
                output_file = os.path.join(self.config.example_path, "output_a2spec", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

     ##Inter Procedural##
    def ensurerefine_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """Please check every function in the program.

            If a function currently has no ensures block, you should make NO change to this function. Do NOT add ensures to this function. 

            If a function's existing ensures block claims something related to the function return value, you need to adjust the function prototype to give a name to the return value through --> (return_variable_name: return_type). For example, given a function `fn foo(x: i32) -> i32', you can change it to be `fn foo(x:i32) -> (ret:i32)', which would allow you to use `ret' to refer to the return value of function foo in its ensures block. 

            Do NOT make any other changes to the code.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should never change or delete any existing code.
You should NOT add ensures, if a function currently does not have ensures.

""" 
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_ensurerefine"))):
            if f.endswith(".rs") and f[2] in ["1", "5"]:
                input_file = os.path.join(self.config.example_path, "input_ensurerefine", f)
                output_file = os.path.join(self.config.example_path, "output_ensurerefine", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)

    ##Inter Procedural##
    def removeexec_inference(self, code, temp=0, answer_num=1, error=""):
        ###This one is not working very well. We should maybe only use it during diagnosis.
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

        instruction = """
        Verus does not allow assert, loop invariant, ensures, or requires block to invoke any executable functions, or to access any private field of an object. Please check if any existing assert, loop invariant, ensures, or requires block does such things. Remove those if they do. Please make NO other changes to the program.

        Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should never EVER add new variables, NEVER!
You should never change or delete any existing code.

Here is an example of correct function pre and post conditions: \n
"""

        example_file = os.path.join(self.config.example_path, "example_ensurequire.rs")
        example_content = open(example_file).read()

        instruction += example_content

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input_removeexec"))):
            if f.endswith(".rs") and f[2] in ["1"]:
                input_file = os.path.join(self.config.example_path, "input_removeexec", f)
                output_file = os.path.join(self.config.example_path, "output_removeexec", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})


        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)
    
    def merge_code_with_errors(self, codes, errors):
        system = """You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."""

        instruction = """Please generate a correct rust code with the Verus invariant by refering to the following code snippets along with the error messages. The error messages are provided to help you understand the potential issues in the code. You should consider the error messages when generating the correct the code snippets.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.

Here are the code snippets along with the error messages:"""

        for i, code in enumerate(codes):
            instruction += f"\n\n\tCode snippet {i+1}:\n```\n{code}\n```\n\tError message:\n```\n{errors[i]}\n```"
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, [], [], system, answer_num=1, max_tokens=self.config.max_token, temp=0.5)
    
    def proof_func_inference(self, code, temp=0, answer_num=1, error=""):
        """Infer the helper proof functions for the code."""
        system = """You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."""

        instruction = """Please generate the proof functions to the given Rust code to help Verus prove the correctness of the code. The proof functions could be considered as the helper lemmas that could help you to prove the correctness of the code.

Here are some principles that you have to follow:
 You should only response with the JSON format:
{
    "proof_func_name": "proof_func_code",
}

Note, all the proof functions' names should start with `lemma_`.
Note, please don't generate the proof functions that are similar to the existing proof/lemma functions in the code!
Note, if you really believe that the code can be already proved by using current proof functions, you can just return an empty dictionary.
"""
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input-proof-func"))):
            if f.endswith(".rs"):
                input_file = os.path.join(self.config.example_path, "input-proof-func", f)
                output_file = os.path.join(self.config.example_path, "output-proof-func", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})
        with open("proof_block_example.txt", "w") as f:
            f.write("Query:\n" + examples[0]["query"])
            f.write("\n\nAnswer:\n" + examples[0]["answer"])

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=4096, temp=temp)

    def proof_block_inference(self, code, temp=0, answer_num=1, error=""):
        system = """You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."""

        instruction = """Please add proof blocks to the given Rust code to help Verus prove the correctness of the code. You need to analyze which locations in the code need to be proved and add the proof blocks to help Verus to prove the correctness of the code. You can insert multiple proof blocks in the code as long as they are necessary to prove the correctness of the code. You can also include new ghost variables that could help you to prove the correctness of the code.

Here are some common locations where you can add proof blocks:
1. In the beginning of the function
2. Before the loop
3. In the beginning of the loop
4. In the end of the loop
5. Before the key operations
6. After the key operations

The proof block looks like this:
```
proof {
    // your proof code here
    // assert(...)
    // LEMMA_FUNCTION(...)
    // ...
} // Added by AI
```

The ghost variable looks like this:
```
let ghost ...; // Added by AI
```

Here are some principles that you have to follow:
 You should only response with Rust code, and not include any explanation."""
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input-proof"))):
            if f.endswith(".rs"):
                input_file = os.path.join(self.config.example_path, "input-proof", f)
                output_file = os.path.join(self.config.example_path, "output-proof", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})
        with open("proof_block_example.txt", "w") as f:
            f.write("Query:\n" + examples[0]["query"])
            f.write("\n\nAnswer:\n" + examples[0]["answer"])

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)


    def get_lemma_code(self, name):
        if not name.endswith(".rs"):
            name = name+".rs"
        input_file = os.path.join(self.config.lemma_path, name)
        input_content = open(input_file).read()
        return input_content

    def insert_loop_isolation(self, code):
        """Insert #[verifier::loop_isolation(false)]"""
        lines = code.splitlines()
        verus_line = -1
        for i, line in enumerate(lines):
            if "verus!" in line:
                verus_line = i
                break
        if verus_line == -1:
            self.logger.error("No verus! found in the code.")
            return code
        insert_line = "\n#[verifier::loop_isolation(false)]"
        new_code = "\n".join(lines[:verus_line+1] + [insert_line] + lines[verus_line+1:])
        return new_code
    
 
    def insert_lemma_func(self, code, lemmas):
        """Insert existing already-proved lemmas"""
        for lemma_name in lemmas:
            lemma_code = self.get_lemma_code(lemma_name)
            lemma_func_dict = {lemma_name: lemma_code}
            code = self.insert_proof_func(code, lemma_func_dict)
        return code
    
    def insert_proof_func(self, code, proof_func_dict):
        """Insert the proof functions into the code."""
        lines = code.splitlines()
        verus_line = -1
        for i, line in enumerate(lines):
            if "verus!" in line:
                verus_line = i
                break
        if verus_line == -1:
            self.logger.error("No verus! found in the code.")
            return code
        proof_func_code = "\n\n".join(proof_func_dict.values())
        new_code = "\n".join(lines[:verus_line+1] + [proof_func_code] + lines[verus_line+1:])
        return new_code
    
    def check_proof_func(self, code: str, proof_func_dict: dict, temp_dir=None):
        """Check the proof funcs and return the code with correct proof."""
        new_code = self.insert_proof_func(code, proof_func_dict) 
        if new_code == code:
            return code
        
        topological_order = {}
        for func_name, func_code in proof_func_dict.items():
            dependencies = set()
            for func_name2, _ in proof_func_dict.items():
                if func_name2 == func_name:
                    continue
                if func_name2 + "(" in func_code:
                    dependencies.add(func_name2)
            topological_order[func_name] = dependencies
        
        # Get the topological order of the proof functions.
        # NOTE, we don't handle the cyclic dependency here.
        order = []
        visited = set()
        def dfs(func_name):
            if func_name in visited:
                return
            visited.add(func_name)
            for dep in topological_order[func_name]:
                dfs(dep)
            order.append(func_name)
        for func_name in proof_func_dict:
            dfs(func_name)

        correct_proof_func = {}
        for func_name in order:
            func_code = proof_func_dict[func_name]

            dependency_error = False
            for dep in topological_order[func_name]:
                if dep not in correct_proof_func:
                    dependency_error = True
                    break
            if dependency_error:
                continue

            minimized_func = {func_name: func_code}
            new_code = self.insert_proof_func(code, minimized_func)

            res, _ = evaluate(new_code, self.config.verus_path, func_name=func_name)

            # No error, the proof function is correct.
            if res[0] > 0 and res[1] == 0:
                correct_proof_func.update(minimized_func)
                code = new_code
                continue
            
            # Try repairing the proof function.
            #new_code, _ = self.refinement.debug_type_error(new_code)
            if temp_dir:
                cur_temp_dir = os.path.join(temp_dir, func_name)
                os.makedirs(cur_temp_dir, exist_ok=True) 
            else:
                cur_temp_dir = None
            new_code = self.refinement.repair_veval(new_code, max_attempt=3, func_name=func_name, temp_dir=cur_temp_dir)
            res, msg = evaluate(new_code, self.config.verus_path, func_name=func_name)
            if res[0] > 0 and res[1] == 0:
                correct_proof_func.update(minimized_func)
                code = new_code
                continue

        return code
    
    def generate_with_hdn(self, code, with_refine=False, merge=True, verbose=False):
        """
        generate the first version of proof code
        """
        temp = 0.2 #TODO: should we start with 0?
        answer_num = 3
        attempt = 0
        original_code = code
        best_score_of_all = -1
        best_score_of_valid = -1
        code_pool = []
        while attempt < 3:
            codes = self.direct_inference(original_code, temp, answer_num)
            found = False
            for cand_code in codes:
                # simple filtering
                might_code = re.findall(r"```rust(.*)```|```verus(.*)```", cand_code, flags=re.DOTALL)
                if might_code:
                    cand_code = might_code[0][0] if might_code[0][0] else might_code[0][1]
                score, _ = evaluate(cand_code, self.config.verus_path)
                if score[0] > best_score_of_all:
                    best_score_of_all = score[0]
                    best_code_of_all = cand_code
                if "verus!" in cand_code and code_change_is_safe(original_code, cand_code, self.config.verus_path, self.logger):
                    found = True
                else:
                    continue
                code_pool.append(cand_code)
                if score[0] > best_score_of_valid:
                    best_score_of_valid = score[0]
                    code = cand_code
            if found:
                break
            self.logger.info("regenerate...")
            temp += 0.1    # generate a different one
            attempt += 1
        if best_score_of_valid == -1:
            # original code has been changed
            # code_pool needs reset
            code = best_code_of_all
            code_pool = [code]
        if verbose:
            self.logger.info(code)

        if not with_refine:
            return code

        nl_result = json.loads(self.whether_nonlinear_inference(code, 0.0)[0])
        if not nl_result["result"]:
            refine_funcs = [self.constantrefine_inference, self.arrayrefine_inference, self.condlooprefine_inference]
            refine_no_merge = []
            refine_prefer_no_change = [2]
        else:
            refine_funcs = self.refine_funcs
            refine_no_merge = self.refine_no_merge
            refine_prefer_no_change = self.refine_prefer_no_change
        
        for i, func in enumerate(refine_funcs):
            self.logger.info("refining with %s" % func.__name__)
            temp = 0
            attempt = 0
            original_code = code
            _, msg = evaluate(original_code, self.config.verus_path)
            while attempt < 3:
                code = func(original_code, temp)[0]
                # simple filtering
                might_code = re.findall(r"```rust(.*)```|```verus(.*)```", code, flags=re.DOTALL)
                if might_code:
                    code = might_code[0][0] if might_code[0][0] else might_code[0][1]
                if verbose:
                    self.logger.info(code)
                if "verus!" in code:
                    break
                self.logger.info("regenerate...")
                temp += 0.2    # generate a different one
                attempt += 1
            code_pool.append(code)
            if merge:
                _, msg_new = evaluate(code, self.config.verus_path)
                if i not in refine_no_merge:
                    if i in refine_prefer_no_change:
                        code_merge = merge_outputs(original_code, code, self.config.verus_path, prefer=0)
                        code_cmp = compare_and_choose_by_loop(code, original_code, msg_new.stderr, msg.stderr)
                        code = choose_best([original_code, code, code_merge, code_cmp], self.config.verus_path)
                    else:
                        code_merge = merge_outputs(original_code, code, self.config.verus_path)
                        code_cmp = compare_and_choose_by_loop(original_code, code, msg.stderr, msg_new.stderr)
                        code = choose_best([code, original_code, code_merge, code_cmp], self.config.verus_path)
                    if verbose:
                        self.logger.info("after merge")
                        self.logger.info(code)
            # if code != original_code:
            #     code = remove_comment(code)


        # run houdini
        score,_ = evaluate(code, self.config.verus_path)
        if score[1] == 0:
            return code
        self.logger.info("run houdini")
        for cp in code_pool:
            code = self.hdn.merge_code(code, cp)
        if verbose:
            self.logger.info(code)
        failures, code_h = self.hdn.run(code)
        if verbose:
            self.logger.info(code_h)
        if len(failures) == 0:
            return code_h
        return code
    
    def generate_baseline(self, code, retry=25):
        """
        Generate the proof code.
        """
        temp = 1.0
        answer_num = 5

        best_code_of_all = code
        best_score_of_all = EvalScore.get_worst_score()
        for i in range(retry):
            self.logger.info("Direct inference with baseline attempt %d" % i)
            candidates = self.direct_full_inference(code, temp, answer_num)
            for cand_code in candidates:
                cand_code = clean_code(cand_code)
                veval = VEval(cand_code, self.logger)
                score = veval.eval_and_get_score()
                if score.is_correct():
                    return cand_code
                if score > best_score_of_all:
                    best_score_of_all = score
                    best_code_of_all = cand_code
        return best_code_of_all

    
    def generate_with_proof_func(self, code, with_inference=True, with_refine=True, merge_cand=5, verbose=False, repair_steps=10, temp=1.0, temp_dir=Path("output-intermediate-temp"), disable_ranking=False):
        """
        Generate the proof code with helper proof functions.
        """
        temp_dir.mkdir(parents=True, exist_ok=True)
        answer_num = merge_cand
        original_code = code

        if with_inference:
            best_score_of_all = EvalScore.get_worst_score()
            best_score_of_valid = EvalScore.get_worst_score()
            code_pool = []
            best_code_of_all=original_code

            attempt = 0
            #changed from 5 to 4 just to see ...
            code_pool_stop_size = 4
            if disable_ranking:
                self.logger.warning("Disabled ranking")
                code_pool_stop_size = 1

            while attempt < 3:
                self.logger.info("Direct inference attempt {}".format(attempt))
                # Now use direct_inference.
                codes = self.direct_inference(original_code, temp=temp, answer_num=answer_num)
                found = False
                has_unsafe = False
                for i, cand_code in enumerate(codes):
                    self.logger.info(f"Checking candidate {attempt}-{i}")
                    cand_code = clean_code(cand_code)
                    newcode, _ = self.refinement.debug_type_error(cand_code)
                    if newcode:
                        cand_code = newcode

                    veval = VEval(cand_code, self.logger)
                    score = veval.eval_and_get_score()

                    is_safe_code_change = code_change_is_safe(original_code, cand_code, self.config.verus_path, self.logger)

                    if not is_safe_code_change:
                        has_unsafe = True

                    if score.is_correct() and is_safe_code_change:
                        self.logger.info("Verus succeeded!!")
                        return cand_code

                    if score > best_score_of_all:
                        best_score_of_all = score
                        best_code_of_all = cand_code

                    (temp_dir / f"{attempt}-{i}.rs").write_text(cand_code + "\n// is safe: " + str(is_safe_code_change) + "\n// Score: " + str(score))
                    # Now we will skip the loop invariants with compilation error
                    # TODO: We shouldn't skip code that has compilation error: we should try to delete the lines that
                    #       caused compilation errors
                    if "verus!" in cand_code and is_safe_code_change and not score.compilation_error:
                        found = True
                        self.logger.info(f"{attempt}-{i}.rs in code pool")
                        code_pool.append(cand_code)
                        if not (score < best_score_of_valid):
                            best_score_of_valid = score
                            self.logger.info(f"{attempt}-{i}.rs is now the best proof candidate")
                            code = cand_code
                        if len(code_pool) >= code_pool_stop_size:
                            break
    
                #TODO: I am doing this experiment to see whether it is helpful to regenerate once there were unsafe candidates
                if found and not has_unsafe:
                    break

                self.logger.info("Regenerate...")
                attempt += 1

            if best_score_of_valid == EvalScore.get_worst_score():
                self.logger.error("No valid code found!")
                code = best_code_of_all
                code_pool = [code]
            else:
                # Try merging the valid codes to see if there is a better one.

                # Will also try an all-together merge
                allmerged_code = code
                for i, cp in enumerate(code_pool):
                    self.logger.info(f"Working on merge-{i}.rs")
                    try:
                        merged_code = self.hdn.merge_invariant(code, cp)
                        allmerged_code = self.hdn.merge_invariant(allmerged_code, cp)
                    except Exception as e:
                        self.logger.error(f"Error in merging code at step {i}: {e}")
                        continue

                    #selectively merged 
                    veval = VEval(merged_code, self.logger)
                    score = veval.eval_and_get_score()
                    (temp_dir / f"merged-{i}.rs").write_text(merged_code + "\n// Score: " + str(score))
                    if score.is_correct():
                        self.logger.info("Merged code is correct.")
                        return merged_code

                    if disable_ranking:
                        if not score.compilation_error:
                            self.logger.info("Disabled ranking and the code is not correct.")
                            code = merged_code
                    elif not (score < best_score_of_valid):
                        self.logger.info("Merged code is better.")
                        best_score_of_valid = score
                        best_code_of_all = merged_code
                        # Only change the current code when the score isn't worse.
                        code = merged_code

                    self.logger.info(f"Running houdini on merge-{i}.rs")
                    hdn_failures, merge_code = self.hdn.run(merged_code)
                    if len(hdn_failures) == 0:
                        self.logger.info("Merged code with hdn is correct.")
                        return merge_code

                    #allmerged version
                    am_veval = VEval(allmerged_code, self.logger)
                    am_score = am_veval.eval_and_get_score()
                    (temp_dir / f"allmerged-{i}.rs").write_text(allmerged_code + "\n// Score: " + str(am_score))
                    if am_score.is_correct():
                        self.logger.info("All merged code is correct.")
                        return allmerged_code
                    hdn_failures, hdnam_code = self.hdn.run(allmerged_code)
                    if len(hdn_failures) == 0:
                        self.logger.info("All merged code with hdn is correct.")
                        return hdnam_code

        #the best candidate is `code' now
        #score is cur_score
        veval = VEval(code, self.logger)
        cur_score = veval.eval_and_get_score()

        if with_refine:
            refine_funcs = self.default_refine_funcs
            # If the code contains non-linear arithmetic
            nl_lines = get_nonlinear_lines(code, self.logger)
            if nl_lines:
                self.logger.warning("Non-linear arithmetic detected.")
                for (_, _ , text) in nl_lines:
                    self.logger.warning(text)
                refine_funcs.append(self.nonlinear_inference)
                refine_funcs.append(self.nonlbound_inference)

            for i, func in enumerate(refine_funcs):
                self.logger.info("refining with %s" % func.__name__)
                attempt = 0
                original_code = code

                while attempt < 3:
                    # Only 1 refined candidate.
                    code = func(original_code, temp=temp)[0]
                    # simple filtering
                    code = clean_code(code)
                    newcode = self.refinement.debug_type_error(code)[0]
                    if newcode:
                        code = newcode
                    if verbose:
                        self.logger.info(code)
                    if not code_change_is_safe(original_code, code, self.config.verus_path, self.logger):
                        self.logger.info("Unsafe code change")
                        code = original_code
                    if "verus!" in code:
                        break
                    
                    self.logger.info("regenerate...")
                    attempt += 1
                if code == original_code:
                    self.logger.info("Refinement did not change the code")
                    continue 

                veval = VEval(code, self.logger)
                new_score = veval.eval_and_get_score()
                if new_score.is_correct():
                    self.logger.info("Verus succeeded with refinement!!")
                    return code


                hdn_failures, hdn_code = self.hdn.run(code)
                if len(hdn_failures) == 0:
                    self.logger.info("Verus succeeded with refinement and Houdini!")
                    return hdn_code
    
                #still errors left, let's see if we should accept the new version
                if func.__name__ == "condlooprefine_inference":
                    # condloop-refine is not often helpful, so we need to be cautious here
                    # TODO: would this work for those diffy ones?
                    self.logger.info("New refined code under condloop is not better")
                    code = original_code
                elif disable_ranking:
                    if not score.compilation_error:
                        self.logger.info("Disabled ranking and the code is not correct.")
                        code = original_code
                elif new_score.is_good_repair(cur_score):
                    # Now we use a loose condition to accept the new code.
                    self.logger.info("New refined code is a good repair")
                    self.logger.info(code)
                    cur_score = new_score
                    (temp_dir / f"refine-{i}.rs").write_text(code)
                else:
                    self.logger.info("New refined code is worse")
                    code = original_code

        if repair_steps > 0:
            (temp_dir / "before-repair.rs").write_text(code + "\n// Score: " + str(cur_score).replace("\n", " "))
            repair_temp_dir = temp_dir / "repair"
            repair_temp_dir.mkdir(parents=True, exist_ok=True)

            if self.repair_uniform:
                # Ablation study: repair with uniform strategy
                code = self.refinement.repair_veval_in_one(code, max_attempt=repair_steps, temp_dir=repair_temp_dir, temp=temp)
            else:
                code = self.refinement.repair_veval(code, max_attempt=repair_steps, temp_dir=repair_temp_dir, temp=temp)

            veval = VEval(code, self.logger)
            score = veval.eval_and_get_score()
            if score.is_correct():
                self.logger.info("Verus succeeded after repair!!")
                return code

        (temp_dir / "final.rs").write_text(code + "\n// Score: " + str(score).replace("\n", " "))

        # run houdini
        hdn_code = self.hdn.run(code)[1]
        hdn_veval = VEval(hdn_code, self.logger)
        hdn_score = hdn_veval.eval_and_get_score()
        (temp_dir / "final-hdn.rs").write_text(hdn_code + "\n// Score: " + str(hdn_score).replace("\n", " "))
        if hdn_score.is_correct():
            self.logger.info("Verus succeeded with hdn!!")
            return hdn_code
        elif hdn_score > score:
            self.logger.info("Houdini code is better")
        else:
            self.logger.info("Original code is better")
        return code


    def generate_simple(self, code, func_name=None):
        """
    #This function was a trimmed down version of generate_with_proof_function
    #it is to be used by plug in and hence we are skipping many steps
        """
        temp = 0.5
        answer_num = 3
        attempt = 0
        original_code = code
        best_score_of_all = EvalScore.get_worst_score()
        best_score_of_valid = EvalScore.get_worst_score()
        code_pool = []

        from pathlib import Path
        temp_dir = Path("output-intermediate-temp-" + time.strftime("%Y%m%d-%H%M%S"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        best_code_of_all=original_code
        attempt = 0
        max_attempt = 3
        while attempt < max_attempt:
            # Now use direct_inference.
            codes = self.direct_inference(original_code, temp, answer_num)
            found = False
            for i, cand_code in enumerate(codes):
                cand_code = clean_code(cand_code)
                newcode, _ = self.refinement.debug_type_error(cand_code)
                if newcode:
                    cand_code = newcode

                veval = VEval(cand_code, self.logger)
                score = veval.eval_and_get_score()

                if score.is_correct():
                    self.logger.info("Verus succeeded!!")
                    return cand_code


                # run houdini
                hdn_failures, hdn_code = self.hdn.run(cand_code)
                #hdn_veval = VEval(hdn_code, self.logger)
                #hdn_score = hdn_veval.eval_and_get_score()
                #if hdn_score.is_correct():
                if len(hdn_failures) == 0:
                    self.logger.info("Verus succeeded with hdn!!")
                    return hdn_code

                if score > best_score_of_all:
                    best_score_of_all = score
                    best_code_of_all = cand_code

                is_safe_code_change = code_change_is_safe(original_code, cand_code, self.config.verus_path, self.logger, True, self.config.util_path)
                if is_safe_code_change:
                    self.logger.warning("code change is safe")
                else:
                    self.logger.warning("code change is not safe")
                (temp_dir / f"{attempt}-{i}.rs").write_text(cand_code + "\n// is safe: " + str(is_safe_code_change) + "\n// Score: " + str(score))
                if "verus!" in cand_code and is_safe_code_change:
                    found = True
                else:
                    #self.logger.info(cand_code)
                    continue
                code_pool.append(cand_code)

                if not (score < best_score_of_valid):
                    best_score_of_valid = score
                    code = cand_code
            if found:
                break
            #self.logger.info("regenerate...")
            temp += 0.1    # generate a different one
            attempt += 1
        if best_score_of_valid == EvalScore.get_worst_score():
            code = best_code_of_all
            code_pool = [code]

        #TODO: not doing any refine for now ...
        refine_funcs = self.simple_refine_funcs

        cur_score = best_score_of_valid
        for i, func in enumerate(refine_funcs):
            #self.logger.info("refining with %s" % func.__name__)
            temp = 0
            attempt = 0
            original_code = code

            while attempt < 3:
                code = func(original_code, temp)[0]
                # simple filtering
                code = clean_code(code)
                newcode = self.refinement.debug_type_error(code)[0]
                if newcode:
                    code = newcode
                if not code_change_is_safe(original_code, code, self.config.verus_path, self.logger, True, self.config.util_path):
                    #self.logger.info("Unsafe code change")
                    code = original_code
                if "verus!" in code:
                    break
                
                #self.logger.info("regenerate...")
                temp += 0.2    # generate a different one
                attempt += 1
            
            veval = VEval(code, self.logger)
            new_score = veval.eval_and_get_score()
            if new_score.is_correct():
                self.logger.info("Verus succeeded!!")
                return code
            elif new_score < cur_score:
                self.logger.info("New code is worse")
                code = original_code
            else:
                self.logger.info("New code is better")
                self.logger.info(code)
                cur_score = new_score
                #(temp_dir / f"refine-{i}.rs").write_text(code)

        #repair_temp_dir = temp_dir / "repair"
        #repair_temp_dir.mkdir(parents=True, exist_ok=True)
        #code = self.refinement.repair_veval(code, max_attempt=5, temp_dir=repair_temp_dir)
        #veval = VEval(code, self.logger)
        #score = veval.eval_and_get_score()
        #if score.is_correct():
        #    self.logger.info("Verus succeeded!!")
        #    return code

        #(temp_dir / "final.rs").write_text(code + "\n// Score: " + str(score).replace("\n", " "))

        # run houdini
        hdn_code = self.hdn.run(code)[1]
        hdn_veval = VEval(hdn_code, self.logger)
        hdn_score = hdn_veval.eval_and_get_score()
        if hdn_score.is_correct():
            self.logger.info("Verus succeeded with hdn!!")
            return hdn_code
        elif hdn_score > score:
            self.logger.info("Houdini code is better")
            return hdn_code
        else:
            self.logger.info("Original code is better")
            return code


    #The generate function Shan has been using for her inter-procedural benchmarks. 
    #TODO: to combine with generate_with_hdn later
    def generate(self, code, infer_funcs=[], verbose=True, answer_num=1, error=""):
        """
        generate the first version of proof code
        """
        if len(infer_funcs)==0:
            infer_funcs = self.infer_funcs

        original_code = code

        if proved_by_verus (code, self.config.verus_path):
            return code

        for func in infer_funcs:
            self.logger.info("Inference with %s" % func.__name__)
            temp = 0
            attempt = 0
            #for each inference function, give 3 attempts to generate code
            while attempt < 3:
                #inference always based on current code, could be based on initial version as an alternative
                codes = func(code, temp, answer_num, error)
                found = False
                for cand_code in codes:
                    self.logger.info("raw inference output:" + cand_code) 
                    might_code = re.findall(r"```rust(.*)```|```verus(.*)```", cand_code, flags=re.DOTALL)
                    if might_code:
                        cand_code = might_code[0][0] if might_code[0][0] else might_code[0][1]
                    if "verus!" in cand_code and not check_syntaxerr_inv(cand_code) and code_change_is_safe(code, cand_code, self.config.verus_path, self.logger):
                        if proved_by_verus (cand_code, self.config.verus_path):
                            return cand_code
                        found = True
                        code = self.hdn.merge_code(code, cand_code)
                        if proved_by_verus (code, self.config.verus_path):
                            return code
                if found:
                    break
                else:
                #if this attempt did not generate any valid code, try again
                    self.logger.info("regenerate...")
                    temp += 0.1    # generate a different one
                    attempt += 1

            if found == False:
                self.logger.info("Inference function " + func.__name__ + "didn't generate valid code.")
            #else:
            #    if verbose:
            #        self.logger.info(func.__name__+" produced the following code:")
            #        self.logger.info(code)

        code = remove_redundant_loopinv(code)

        if verbose:
            self.logger.info("Merged inference results:")
            self.logger.info(code)
            self.logger.info("Move on?")
            x = input()
            if "n" in x:
                exit()

        return code


    def run(self, input_file, output_file, args: dict={}):
        baseline = args.get("is_baseline", False)
        repair_steps = args.get("repair", 5)
        merge_cand = args.get("merge", 5)
        temp = args.get("temp", 1.0)
        phase_uniform = args.get("phase_uniform", False)
        disable_ranking = args.get("disable_ranking", False)
        direct_repair = args.get("direct_repair", False)
        disable_one_refinement = args.get("disable_one_refinement", -1)

        if disable_one_refinement >= 0 and disable_one_refinement < len(self.default_refine_funcs):
            self.logger.warning("Disable one refinement function: %s" % self.default_refine_funcs[disable_one_refinement].__name__)
            self.default_refine_funcs = self.refine_funcs[:disable_one_refinement] + self.refine_funcs[disable_one_refinement+1:]

        content = open(input_file).read()
        output_file = Path(output_file)
        output_dir = output_file.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(output_dir) / ("intermediate-" + output_file.stem)
        temp_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Generating proof code" + (" with baseline" if baseline else ""))
        self.logger.info("Temperature: " + str(temp))
        if baseline:
            self.logger.info("Generate with baseline mode")
            code = self.generate_baseline(content)
        elif phase_uniform:
            self.logger.info("Generate with uniform refinement mode")
            self.direct_inference = self.direct_inference_with_refinement
            code = self.generate_with_proof_func(content, with_refine=False, merge_cand=merge_cand, verbose=True, repair_steps=repair_steps, temp_dir=temp_dir, temp=temp, disable_ranking=disable_ranking) 
        elif direct_repair:
            self.logger.info("Generate with direct repair mode")
            code = self.generate_with_proof_func(content, with_inference=False, with_refine=False, merge_cand=merge_cand, verbose=True, repair_steps=repair_steps, temp_dir=temp_dir, temp=temp, disable_ranking=disable_ranking)
        else:
            code = self.generate_with_proof_func(content, with_refine=True, merge_cand=merge_cand, verbose=True, repair_steps=repair_steps, temp_dir=temp_dir, temp=temp, disable_ranking=disable_ranking)

        score, _ = evaluate(code, self.config.verus_path)
        is_safe = code_change_is_safe(content, code, self.config.verus_path, self.logger, debug=False)
        code += "\n// Score: " + str(score)
        code += "\n// Safe: " + str(is_safe)

        with open(output_file, "w") as wf:
            wf.write(code)
        self.logger.info("finished!")

    # This is a simple version for plug-in to use.
    def run_simple (self, input_file, func_name, extract_body = True):
        content = open(input_file).read()
        code = self.generate_simple(content, func_name)

        if extract_body and func_name:
            code = get_func_body(code, func_name, self.config.util_path)

        print(code)

        
##############################################
#The following functions are used for Shan's inter-procedural benchmarks
#maybe they should be moved to a different file later
##############################################
        
#Applies all inference functions in infer_funcs one by one
#With houdini at the end
    def run_new(self, input_file, output_file, infer_funcs=[]):
        content = open(input_file).read()

        score, msg = evaluate(content, self.config.verus_path)
        if score[1] == 0:
            self.logger.info("[run_new] Verus succeeded. No more generation needed.")
            with open(output_file, "w") as wf:
                wf.write(content)
                self.logger.info("[run_new] Done!")
                return

        if len(infer_funcs)==0:
            infer_funcs = self.infer_funcs

        self.logger.info("[run_new] generating proof code...")
        code = self.generate(content, infer_funcs) 

        #TODO: change with parser?
        failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=False)
        if len(failures) == 0:
            self.logger.info("[run_new] Verus succeeded. No more refinement needed.")
            with open(output_file, "w") as wf:
                wf.write(hdn_code)
            self.logger.info("[run_new] Succeed!")
        else:
            #os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w") as wf:
                wf.write(code)
            self.logger.info("finished [run_new]!")

#Inter Proc

    #refine function fname in input_file, with every other function unchanged from input_file and old_file 
    #input_file was one round of inference result from old_file
    #
    #Different from run_refine_newpre, here, 
    #                           we are not starting with a version that is correct intra-procedurally
    #                           other functions have no pre/post conditions
    #                           and we are not supposed to change other functions' pre/post conditions
    #TODO: it is possible that changes to other functions' pre/post conditions are needed ...
    #TODO: I am using direct_require_inference here, but assert2spec in run_refine_newpre
    #return the number of remaining errors

    def run_refine(self, old_file, input_file, output_file, fname):
        old_content = open(old_file).read()
        content = open(input_file).read()

        self.logger.info("[run_refine] checking function ...")

        veval = VEval(code)
        veval.eval()
        failures = veval.get_failures()

        if len(failures) == 0:
            self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
            with open(output_file, "w") as wf:
                wf.write(content)
                self.logger.info("[run_refine] Done!")
                return 0

        #intra-procedural loop invariant and assert refinement
        #In theory, it could change highlight function's spec, but it is unlikely
        #TODO: should we re-generate based on the old_content? something to consider later
        self.logger.info("[run_refine] intra-procedural proof generation and refine")
        code = self.generate(content, [self.direct_inference, self.constantrefine_inference], answer_num=2) 

        #merge with baseline file, so as not to change other function's pre/post conditions
        code = merge_with_highlight(old_content, code, fname)

        #merge with the preliminary inference version generated before run_refine
        #both has only made changes to function fname
        code = self.hdn.merge_code(code, content)

        veval = VEval(code)
        veval.eval()
        failures = veval.get_failures()

        if len(failures) == 0:
            self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
            with open(output_file, "w") as wf:
                wf.write(code)
            self.logger.info("[run_refine] Done!")
            return 0

        #1. use houdini to remove any wrong loop invariant or assert
        #2. if it still does not work, Houdini will remove post conditions that are not satisfied

        self.logger.info("[run_refine] Debugging w/ Houdini")
        
        failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=True)

        if len(failures) == 0:
            self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
            with open(output_file, "w") as wf:
                wf.write(hdn_code)
            self.logger.info("[run_refine] Done!")
            return 0

        #2. if Houdini fails, pre-condition should be strengthened
        #The precondition could fix whatever verification errors, including arithmetic overflow problems
        self.logger.info("[run_refine] Verus failed on Houdini result. Adding function pre-condition ...")
        #Houdini may have removed invariants that could be proved with the new pred-condition added next
        #so, here, I feed the code before houdini
        #TODO: actually, it is possible that we need to strengthen other function's post conditions
        #       but that needs to be very targeted, very careful
        code = self.generate(code, infer_funcs=[self.direct_require_inference])
        #make sure no changes to other functions' spec
        code = merge_with_highlight(content, code, fname)
        
        #Run Houdini again with the added pre-condition
        failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=True)

        if len(failures) == 0:
            self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
            hdn_code = remove_redundant_req (hdn_code, fname, self.config.verus_path)
            with open(output_file, "w") as wf:
                wf.write(hdn_code)
            self.logger.info("[run_refine] Done!")
            return 0

        else:
            self.logger.info("[run_refine] Verus failed. Let's try some more refinement.")
            self.logger.info("[run_refine] Adding more loop invariants based on the new function precondition.")
            code = self.generate(code, [self.direct_inference, self.constantrefine_inference], answer_num=2) 
            code = merge_with_highlight(content, code, fname)
            failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=True)
            if len(failures) == 0:
                self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
                with open(output_file, "w") as wf:
                    wf.write(hdn_code)
                self.logger.info("[run_refine] Done!")
                return 0

        attempt = 0
        #This is for testing purpose only
        with open("test.rs", "w") as wf:
             wf.write(hdn_code)
        self.logger.info("[run_refine] Written the code before aritherror_inference to a test.rs for later reference!")

        while attempt < 3:
            if not "possible arithmetic" in msg.stderr:
                self.logger.info("[run_refine] no arithmetic overflow/underflow error detected.")
                break
            attempt += 1
            #adding loop invariants and assert to fix arithmetic overflow/underflow errors
            code = self.generate(hdn_code, infer_funcs=[self.aritherror_inference], error=msg.stderr+msg.stdout)
            #add function pre/post condition to support the new invariants/assert if needed
            code = self.generate(code, infer_funcs=[self.assert2spec_inference])
            #TODO: in theory, I may also have added function post conditions which merge_with_highlight would NOT work
            code = merge_with_highlight(content, code, fname)
            failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=True)
            if len(failures) == 0:
                self.logger.info("[run_refine] Verus succeeded. No more refinement needed.")
                hdn_code = remove_redundant_req (hdn_code, fname, self.config.verus_path)
                with open(output_file, "w") as wf:
                    wf.write(hdn_code)
                self.logger.info("[run_refine] Done!")
                return 0
        
        with open(output_file, "w") as wf:
            wf.write(hdn_code)
        self.logger.info("[run_refine] Done!")

        #TODO: if the only remaining errors are pre-condition errors, we can leave it to the next round ...
        #TODO: or should I?

        if is_preconderr_only(failures):
            return 0

        return score[1]

    #refine function fname in input_file, with every other function unchanged from input_file 
    #input_file was Verified, but now may need update as some of its callee functions' pre-condition might have changed
    #it returns the number of non-fname's post conditions that have been changed
    #Different from run_refine,
    #           intput_file was verified before its callee's spec change
    def run_refine_newpre(self, input_file, output_file, fname):
        content = open(input_file).read()

        #log how many lines of other functions' spec are added
        added_ensures = []

        self.logger.info("[run_refine_newpre] checking function ...")

        #5 attempts, because not all precondition errors reported by Verus at once
        attempt = 0
        while attempt < 5:
            attempt += 1
            #Every attempt should start from the original input
            code = content
            score, msg = evaluate(code, self.config.verus_path)
            if score[1] == 0:
                break

        #If there are verification failures, it must be due to callee's precondition not satisfied

        #Let's first turn callee's preconditions into assert
            self.logger.info("[run_refine_newpre] Attempt {} ...".format(attempt)) 
            self.logger.info("[run_refine_newpre] Adding assert about violated callee preconditions.")
            code = self.generate(code, infer_funcs = [self.spec2assert_inference], error = msg.stderr + msg.stdout)
        #merge with baseline file, so as not to change other function's pre/post conditions
            code = merge_with_highlight(content, code, fname)

        #Let's try adding loop invariants
        #Using answer==3 here to make sure all the needed are there
        #TODO: sometimes, there is no loop in the program. It is weird to add invoke this ...
            self.logger.info("[run_refine_newpre] Adding loop invariants ...")
        #TODO: could put in more refinement
#        code = self.generate(code,  [self.direct_inference, self.constantrefine_inference, self.nestedlooprefine_inference], verbose=True, answer_nua=3) 
            #TODO: only need the nestedlooprefine if it involves nestedloop
            code = self.generate(code, infer_funcs = [self.assert2inv_inference, self.nestedlooprefine_inference], answer_num=3) 
            code = merge_with_highlight(content, code, fname)

            self.logger.info("[run_refine_newpre] Apply Houdini to the latest generations.")
            failures, hdn_code = self.hdn.run_interproc (code, verbose=True, removPost=True, considerassert=False)
            if len(failures) == 0:
                #We don't immediately overwrite code, as Houdini would remove assert! added by spec2assert, which is still needed for further refinement
                code = hdn_code
                self.logger.info("[run_refine_newpre] Verus succeeded. No more refinement needed.")
                break

        #Let's strengthen the function pre-condition or other function's post-condition
            self.logger.info("[run_refine_newpre] Adding function pre-condition and post-condition if necessary ...")
            code = self.generate(code, infer_funcs = [self.assert2spec_inference])
        
        #Run Houdini again with the added pre-condition
        #since we just added assert, houdini should not remove them. Those are the asserts that have to be satisfied
            self.logger.info("[run_refine_newpre] Apply Houdini to the latest generations.")
            failures, code = self.hdn.run_interproc (code, verbose=True, removPost=True, considerassert=False)
            if len(failures) == 0:
                self.logger.info("[run_refine_newpre] Verus succeeded. No more refinement needed.")
                code = remove_redundant_req (code, fname, self.config.verus_path)

                break
            else:
                #This attempt has failed
                if attempt >= 5:
                    with open(output_file, "w") as wf:
                        wf.write(code)
                    self.logger.info("[run_refine_newpre] Done with 5 attempts. Did not find a correct version.")
                    return added_ensures


        #Now we need to merge carefully, as non-highlight function's post condition may have changed
        correct_unmerged = code
        code = merge_with_highlight(content, code, fname)
        score, msg = evaluate(code, self.config.verus_path)
        if score[1] == 0:
            #didn't need to change non-highlight functions' prorotype to succeed
            self.logger.info("[run_refine_newpre] Found a correct version w/o changes to other functions' spec.")
            with open(output_file, "w") as wf:
                wf.write(code)
            self.logger.info("[run_refine_newpre] Done!")
            return added_ensures
        else:
            self.logger.info("[run_refine_newpre] The correct version requires changes to other functions' spec.")
    
        #Now we need to merge some non-highlight's post conditions in correct_unmerged into code
        #TODO: wish we could do some check for the newensurelines, try and only merge the necessary changes
        code, added_ensures = merge_with_highlight_post(code, correct_unmerged, fname)
        score, msg = evaluate(code, self.config.verus_path)
        if score[1] == 0:
            self.logger.info("[run_refine_newpre] Found a correct version w/ changes to other functions' spec.")
        else:
            self.logger.info("[run_refine_newpre] Warning: something went wrong during merge_with_highlight_post. Verus failed.")
 
        with open(output_file, "w") as wf:
            wf.write(code)
            self.logger.info("[run_refine_newpre] Done!")

        return added_ensures


###############Could be more robust than Python, but not used now #####
    def getfun_from_file(self, code, func_name):
        system = "You are an experienced Rust programmer." 

        instruction = "Your mission is to identify the function named: "
        instruction += func_name
        instruction += ", and print this function out. Response with the Rust code only, do not include any explanation or comment."

        examples = []

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=1, max_tokens=self.config.max_token, temp=0)
