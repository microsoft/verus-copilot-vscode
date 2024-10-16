import os
import re
import json
import time
from pathlib import Path
from infer import LLM
from houdini import houdini
from refinement import Refinement
from veval import VEval, EvalScore
from utils import code_change_is_safe, clean_code, get_func_body 

class Generation:
    def __init__(self, config, logger, phase1_examples=["3", "6", "7"]):
        self.config = config
        self.llm = LLM(config, logger)
        self.logger = logger
        self.refine_funcs = [
            self.arraylen_inference,
            self.condlooprefine_inference,
            self.arrayrefine_inference,
            self.constantrefine_inference,
                ]
        self.simple_refine_funcs = [
            self.constantrefine_inference,
        ]
        self.hdn = houdini(config)
        self.phase1_examples = phase1_examples
        self.refinement = Refinement(config, logger)

        #self.logger.warning("Generation initialized with phase1_examples: %s", self.phase1_examples)

    ################################################################################
    #We offer two options for proof inference from scratch
    #direct_inference or the more sophisticated direct_inference_with_refinement
    #they can be followed by invocation of refine agents (optional)
    #################################################################################
    def direct_inference(self, code, temp=0, answer_num=1, error=""):
        system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

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
        """Check whether the code contains the usage of Seq/Vec and add the Seq knowledge to the instruction."""
        _possible_usage = ["Seq", "Vec", "array", "nums"]
        for usage in _possible_usage:
            if usage in code:
                _seq_examples = self.refinement.get_text_examples("seq")
                seq_knowledge = "Here is the usage for Seq in Verus you can refer:\n```\n{}\n```\n".format("\n".join(_seq_examples))
                instruction += "\n\n" + seq_knowledge
                break

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

        self.logger.info("Using the more sophisticated version of inference ...")

        # Integrate the Seq knowledge if needed
        """Check whether the code contains the usage of Seq/Vec and add the Seq knowledge to the instruction."""
        _possible_usage = ["Seq", "Vec", "array", "nums"]
        for usage in _possible_usage:
            if usage in code:
                _seq_examples = self.refinement.get_text_examples("seq")
                seq_knowledge = "Here is the usage for Seq in Verus you can refer:\n```\n{}\n```\n".format("\n".join(_seq_examples))
                instruction += "\n\n" + seq_knowledge
                break

        examples = []

        for f in sorted(os.listdir(os.path.join(self.config.example_path, "input"))):
            if f.endswith(".rs") and f[2] in self.phase1_examples:
                input_file = os.path.join(self.config.example_path, "input", f)
                output_file = os.path.join(self.config.example_path, "output", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, code, system, answer_num=answer_num, max_tokens=self.config.max_token, temp=temp)


    ##########################################################################
    #####Here are some optional refine functions##############################
    ##########################################################################

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


    ###########################################################
    #####Some utility functions################################
    ######TODO: they probably should be moved to utils#########
    ###########################################################
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
    

    #########################################################
    ###########The main generation function##################
    
    def generate_simple(self, code, write_file="", triplet=None):
        """
    #This function is intended to be called from vscode plugin and hence should be kept simple#
        """
        temp = 0.5
        answer_num = 3
        attempt = 0
        original_code = code
        best_score_of_all = EvalScore.get_worst_score()
        best_score_of_valid = EvalScore.get_worst_score()
        code_pool = []

        # from pathlib import Path
        # temp_dir = Path("output-intermediate-temp-" + time.strftime("%Y%m%d-%H%M%S"))
        # temp_dir.mkdir(parents=True, exist_ok=True)

        best_code_of_all=original_code
        attempt = 0
        max_attempt = 3

        #Two options of inference
        #Option 1:
        inference_func = self.direct_inference_with_refinement
        refine_funcs = []
        #Option 2:
        #inference_func = self.direct_inference
        #refine_funcs = self.simple_refine_funcs

        while attempt < max_attempt:
            # Two options of direct_inference.
            codes = inference_func(original_code, temp, answer_num)
            #codes = self.direct_inference(original_code, temp, answer_num)
            found = False
            for i, cand_code in enumerate(codes):
                cand_code = clean_code(cand_code)
                newcode, _ = self.refinement.debug_type_error(cand_code, write_file, triplet)
                if newcode:
                    cand_code = newcode

                veval = VEval(cand_code, write_file, triplet, self.logger)
                score = veval.eval_and_get_score()

                if score.is_correct():
                    self.logger.info("Verus succeeded!!")
                    return cand_code

                # run houdini
                hdn_failures, hdn_code = self.hdn.run(cand_code, write_file, triplet)
                if len(hdn_failures) == 0:
                    self.logger.info("Verus succeeded with help from houdini algorithm!!")
                    return hdn_code

                if score > best_score_of_all:
                    best_score_of_all = score
                    best_code_of_all = cand_code

                is_safe_code_change = code_change_is_safe(original_code, cand_code, self.config.verus_path, self.logger, True, self.config.util_path)
                if not is_safe_code_change:
                    self.logger.warning("LLM proposed proof is not safe")
                # (temp_dir / f"{attempt}-{i}.rs").write_text(cand_code + "\n// is safe: " + str(is_safe_code_change) + "\n// Score: " + str(score))
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
            
            veval = VEval(code, write_file, triplet, self.logger)
            new_score = veval.eval_and_get_score()
            if new_score.is_correct():
                self.logger.info("Verus succeeded!!")
                return code
            elif new_score < cur_score:
                self.logger.info(f"Refine function {func.__name__} is not helpful")
                code = original_code
            else:
                self.logger.info(f"Refine function {func.__name__} is helpful")
                self.logger.info(code)
                cur_score = new_score
        
        # run houdini
        hdn_code = self.hdn.run(code, write_file, triplet)[1]
        hdn_veval = VEval(hdn_code, write_file, triplet, self.logger)
        hdn_score = hdn_veval.eval_and_get_score()
        if hdn_score.is_correct():
            self.logger.info("Verus succeeded with hdn!!")
            return hdn_code
        elif hdn_score > score:
            self.logger.info("Houdini algorithm helped, but failed to get a perfect proof")
            return hdn_code
        else:
            self.logger.info("Houdini algorithm did not help")
            return code


    # This is a simple version for plug-in to use.
    def run_simple(self, input_file, main_file, func_name, extract_body = True, extra_args = ""):
        if main_file == '' or input_file == main_file:
            target_file = input_file
            submodule = None
        else:
            target_file = main_file
            relative_path = os.path.relpath(input_file, os.path.dirname(main_file))
            submodule = relative_path.replace('.rs', '').replace('/', '::')
        triplet = [target_file, submodule, extra_args]
        content = open(input_file).read()
        # backup
        try:
            open(input_file + ".verus_copilot.bak", "w").write(content)
        except:
            pass
        code = self.generate_simple(content, input_file, triplet)
        self.logger.info(f"Finished code generation. Extracting the code inside function {func_name}.")

        if extract_body and func_name:
            code = get_func_body(code, func_name, self.config.util_path)

        print(code, end='')
