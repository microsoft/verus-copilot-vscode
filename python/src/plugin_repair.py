import sys
import os
import argparse
import logging
import json
import tomli
from utils import AttrDict
#import time
#import re
#import numpy as np
from infer import LLM
from houdini import houdini
from utils import fix_one_type_error_in_code, clean_code
import openai
from veval import verus, VEval, VerusErrorType, VerusError, VerusErrorLabel
import subprocess
from utils import get_func_body

class Refinement:
    def __init__(self, config, logger):
        self.config = config
        self.llm = LLM(config, logger)
        self.logger = logger
        self.hdn = houdini(config)
        self.default_system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."
        self.proof_block_info = """The proof block looks like this:
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

Note, please DO NOT modify all other proof blocks that are not related to the error. Just leave them as they are.
"""

    def debug_type_error(self, code: str,  write_file: str = "", triplet=None, verus_error: VerusError = None, num = 1) -> str:
        """
        self debug to fix type error
        """


        rnd = 0
        max_rnd = 10

        if verus_error:
            #fix the reported one
            if (verus_error.error != VerusErrorType.MismatchedType):
                print("Warning: a non type error is passed to debug_type_error")
            else:
                newcode = fix_one_type_error_in_code(code, verus_error.trace[0])
                if newcode:
                    code = newcode

        #check if there is any type errors in the code; if so, fix
        while rnd < max_rnd:
            rnd = rnd + 1

            veval = VEval(code, write_file, triplet, self.logger)
            veval.eval()
            failures = veval.get_failures()
            if len(failures) == 0:
                self.logger.info(f"Verus has succeeded.")
                return code, 0

            has_typeerr = False
            fixed_typeerr = False
            for cur_failure in failures: 
                if cur_failure.error == VerusErrorType.MismatchedType:
#            if "[E0308]" in msg.stderr:
#                type_error = get_typeerror(msg.stderr)
#                lnum, cs, ce, tp, l = type_error
#                if type_error is None:
#                    self.logger.info("Error when extracting type error.")
#                    self.logger.info(msg.stderr)
#                    with open("type-error.log", "a") as f:
#                        f.write(code + "\n\n\n" + msg.stderr)
#                    return code, score[1]
#                code = fix_one_type_error_in_code(code, lnum, cs, ce, tp, l)
                    has_typeerr = True
                    newcode = fix_one_type_error_in_code(code, cur_failure.trace[0])
                    #when newcode is "", the above function failed to fix any type error
                    if newcode:
                        fixed_typeerr = True
                        code = newcode
                        self.logger.info("[Fixed Type Error Round {}]".format(rnd))
                        break
                    else:
                        #this type error is unfixable, let's move on to next error
                        #code = self.repair_SeqSyntax_error(code, cur_failure, 1)[0]
                        continue
                if not fixed_typeerr:
                    #not able to fix any type error in this program, no need to try again
                    break

            if not has_typeerr: 
#                self.logger.info("No more type error.")
                return code, len(failures)

            if not fixed_typeerr:
#                self.logger.info("Remaining type errors are unfixable.")
                return "", len(failures)

        return code, len(failures)
    
    def get_examples(self, example_dir_name):
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, f"input-{example_dir_name}"))):
            if f.endswith(".rs") and f.startswith("ex"):
                input_file = os.path.join(self.config.example_path, f"input-{example_dir_name}", f)
                output_file = os.path.join(self.config.example_path, f"output-{example_dir_name}", f)
                input_content = open(input_file).read()
                output_content = open(output_file).read()
                examples.append({"query": input_content, "answer": output_content})
        with open(f"example-{example_dir_name}.txt", "w") as f:
            for example in examples:
                f.write("Query:\n" + example["query"])
                f.write("\n\nAnswer:\n" + example["answer"])
                f.write("\n\n")
        return examples
    
    def get_text_examples(self, example_dir_name):
        examples = []
        for f in sorted(os.listdir(os.path.join(self.config.example_path, example_dir_name))):
            if f.endswith(".rs") and f.startswith("ex"):
                input_file = os.path.join(self.config.example_path, example_dir_name, f)
                input_content = open(input_file).read()
                examples.append(input_content)
        return examples

#TODO test: this function is not working well. 
    def repair_SeqSyntax_error(self, code: str, verus_error: VerusError, num=1) -> str:

        system = self.default_system
        print("in seq syntax error fixing")

        error_trace = verus_error.trace[0]
        errline = error_trace.get_text().strip() 
        errlinenum = error_trace.lines[0]

        instruction = "This code contains a syntax error on line {}".format(errlinenum) + "in the expression ` " + errline + "'. Your mission is to rewrite this expression `" + errline + "' to fix the syntax error. Please make sure to change that wrong expression and do not change any other part of the code. Response with the Rust code only, do not include any explanation. Please use a comment to explain what changes you have made to fix this syntax error."

        seq_knowledge = "Here is the usage for Seq in Verus you can refer:\n```\n{}\n```\n"
        seq_examples = self.get_text_examples("seq")
        seq_knowledge = seq_knowledge.format("\n".join(seq_examples))
        instruction += "\n\n" + seq_knowledge

        examples = []
        query_template = "Incorrect line \n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        query = query_template.format(errline, code)

        with open("seqsyntax-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)


    def repair_special_assertion_error(self, code: str, verus_error:VerusError, num=1) -> str:
        """
        Some assertions contain certain data structure / APIs that have a routine solution
        It is a bit ad-hoc now. Will refine later.
        """
        assertion_info = verus_error.trace[0].get_text()

        from generation import Generation
        mygen = Generation(self.config, self.logger)

        newcode = ""
        did_special_fix = False


        #TODO: I am currently conducting these special fixes sequentially
        
        if ".filter(" in assertion_info and not "reveal(Seq::filter)" in code:
            instruction = """Please add `reveal(Seq::filter);' right before the failed assert line. This will help Verus understand the filter function."""
            examples = []
            query_template = "Failed assertion\n```\n{}```\n"
            query_template += "\nCode\n```\n{}```\n"
            query = query_template.format(assertion_info, code)
            output = self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, self.default_system, answer_num=num, max_tokens=4096, temp=0.5)[0]
            newcode = clean_code(output)
            newcode, _ = self.debug_type_error(newcode)
            if newcode:
                did_special_fix = True
                code = newcode

        if ".take(" in assertion_info:
            newcode = mygen.insert_lemma_func(code, ["seq_take_ascend", "seq_take_all"])
            newcode = self.repair_assertion_error_with_lemma_func(newcode, verus_error, 1, 
                                                     ["seq_take_ascend", "seq_take_all"])[0]
            newcode = clean_code(newcode)
            newcode, _ = self.debug_type_error(newcode)
            if newcode:
                did_special_fix = True
                code = newcode

        if ".contains(" in assertion_info:
            newcode = mygen.insert_lemma_func(code, ["vec_push", "vec_remove"])
            newcode = self.repair_assertion_error_with_lemma_func(newcode, verus_error, 1,                                            
                                                                  ["vec_push", "vec_remove"])[0]
            newcode = clean_code(newcode)
            newcode, _ = self.debug_type_error(newcode)
            if newcode:
                did_special_fix = True
                code = newcode

        if did_special_fix:
            return code
        else:
            return ""


    
    def repair_assertion_error(self, code: str, verus_error: VerusError, num=1) -> str:

        #Note: the following special_assertion_fix is moved from repair_assertion_error to repair_assertion_error_with_proof_function
        #      because in plug-in, it requires whole file replacement
        #newcode = self.repair_special_assertion_error(code, verus_error, num)
        #if newcode:
        #    return [newcode]


        #Normal route of assertion fixing
        system = self.default_system
        instruction = """Your mission is to fix the assertion error for the following code. Basically, you should either introduce the necessary proof blocks before the location where the assertion fails, or, if the assertion is within a loop, you may need to add appropriate loop invariants to ensure the assertion holds true.

Response with the Rust code only, do not include any explanation."""

        # seq_knowledge = "Here is the usage for Seq in Verus you can refer:\n```\n{}\n```\n"
        # seq_examples = self.get_text_examples("seq")
        # seq_knowledge = seq_knowledge.format("\n".join(seq_examples))
        # instruction += "\n\n" + seq_knowledge

        examples = self.get_examples("assert")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"


        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"

        query = query_template.format(assertion_info, code)

        with open("assert-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    def repair_assertion_error_with_lemma_func(self, code: str, verus_error: VerusError, num=1, lemmas=[]) -> str:
        """
        Here, we potentially know what lemma functions to use.
        And, no need to implement new proof functions
        """

        suggested_lemma = ",".join(lemmas)

        system = self.default_system
        instruction = "Your mission is to fix the assertion error for the following code by using existing lemma functions" + suggested_lemma + "\n"

        instruction += "Please read the comment right before lemma function" + suggested_lemma + " and add invocation to the suggested lemma functions at the right place accordingly to help prove the assertion. \n You should NOT add any new proof function. \n Response with the Rust code only, do not include any explanation."

        examples = self.get_examples("assert-seqtake")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"
        query = query_template.format(assertion_info, code)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.2)
    
 
    def repair_assertion_error_with_proof_func(self, code: str, verus_error: VerusError, num=1) -> str:

        #Note: the following special_assertion_fix is moved from repair_assertion_error to repair_assertion_error_with_proof_function
        #      because in plug-in, it requires whole file replacement

        newcode = self.repair_special_assertion_error(code, verus_error, num)
        if newcode:
            return [newcode]

        system = self.default_system
        instruction = """Your mission is to fix the assertion error for the following code by creating the helper proof functions.
        
        Basically, you should determine what proof functions are needed to prove the current failed assertion, based on the related invariants already had. Then generate them and their invocations in the code just before the assertion.

Response with the Rust code only, do not include any explanation."""

        examples = self.get_examples("proof-func-middle")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"
        query = query_template.format(assertion_info, code)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=1.0)
    
    def repair_precond_error(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
        instruction = """Your mission is to fix the precondition not satisfied error for the following code. Basically, you should add the proof blocks related to the pre-condition check just before the invocation of the function. Note, DO NOT change the proof function whose pre-condition is not satisfied. You can use the pre-conditions of the current function, invariants of the current loop, and the pre-conditions of the called functions to fix the error.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        examples = self.get_examples("precond")
        query_template = "Failed pre-condition\n```\n{}```\n"
        query_template += "Failed location\n```\n{}```\n"
        query_template += "\nCode\n```{}```\n"

        precond_trace, location_trace = verus_error.trace[0], verus_error.trace[1]
        if location_trace.label == VerusErrorLabel.FailedThisPreCond:
            precond_trace, location_trace = location_trace, precond_trace

        pre_cond_info = precond_trace.get_text() + "\n"
        location_info = f"LIne {location_trace.lines[0]}-{location_trace.lines[1]}:\n"
        location_info += location_trace.get_text() + "\n"
        query = query_template.format(pre_cond_info, location_info, code)

        with open("precond-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    #a special type of precondition error: vec len
    def repair_precond_veclen_error(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system

        error_line = verus_error.trace[1].lines[0]
        error_code = verus_error.trace[1].get_text().strip()

        instruction = "Your mission is to help Verus prove the array access in the expression `" + error_code.strip() + "' is always in bound --- this expression is on Line {}".format(error_line) + " of the following program. Basically, you should identify all the arrays accessed (e.g., A[k] or A.set(k,..)) in this expression `" + error_code.strip() + "' and add the following loop invariants for EACH array: 1. an invariant that specify the array length (i.e., A.len() == ...); 2. an invariant about the array index not under bound (e.g., k >= 0). \n" #TODO Shan: we could leverage the highlight to make the target array more explicit
        #2. an invariant about the array index not over bound (e.g., k <= A.len()); 

        instruction += """
        Response requirements:
        Respond with the verus code only, do not include any explanation.
        Respond with the whole program, not just the invariants you added.
        You should only add loop invariants, and you should NOT make any other changes to the program.
        You should NOT change function's pre condition or post conditions.
        """
        #prompt += "The most important thing is: You should only make changes to existing loop invariants, and you should NOT make any other changes to the program. Response with the complete code, including the unchanged part.\n"


        examples = []
#        query_template = "Failed pre-condition\n```\n{}```\n"
#        query_template += "Failed location\n```\n{}```\n"
#        query_template += "\nCode\n```{}```\n"

#        precond_trace, location_trace = verus_error.trace[0], verus_error.trace[1]
#        if location_trace.label == VerusErrorLabel.FailedThisPreCond:
#            precond_trace, location_trace = location_trace, precond_trace

#        pre_cond_info = precond_trace.get_text() + "\n"
#        location_info = f"LIne {location_trace.lines[0]}-{location_trace.lines[1]}:\n"
#        location_info += location_trace.get_text() + "\n"
#        query = query_template.format(pre_cond_info, location_info, code)
        query = code

        with open("precond-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)
    
    def repair_postcond_error(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
        instruction = """Your mission is to fix the post-condition not satisfied error for the following code. Basically, you should add the proof blocks related to the post-condition at the exit point, or modify the existing loop invariants to make them work for the post-condition.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info
        examples = self.get_examples("postcond")
        query_template = "Failed post-condition\n```\n{}```\n"
        query_template += "Failed location\n```\n{}```\n"
        query_template += "\nCode\n```{}```\n"

        location_trace, postcond_trace = verus_error.trace[0], verus_error.trace[1]
        if location_trace.label == VerusErrorLabel.FailedThisPostCond:
            location_trace, postcond_trace = postcond_trace, location_trace
        
        post_cond_info = f"Line {postcond_trace.lines[0]}-{postcond_trace.lines[1]}:\n"
        post_cond_info += postcond_trace.get_text() + "\n"
        location_info = f"Line {location_trace.lines[0]}-{location_trace.lines[1]}:\n"
        location_info += location_trace.get_text() + "\n"
        query = query_template.format(post_cond_info, location_info, code)

        with open("postcond-query.txt", "w") as f:
            f.write(query)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    def repair_invfail_front(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
        instruction = """Your mission is to fix the invariant not satisfied error before the loop for the following code. Basically, you should add proof blocks related to the loop invariant check before the loop (not inside the loop body), or fix/delete the incorrect loop invariants.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        examples = self.get_examples("inv-front")
        query_template = "Failed invariant before the loop\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        error_trace = verus_error.trace[0]
        line_info = f"Line {error_trace.lines[0]}-{error_trace.lines[1]}:\n"
        inv_info = line_info + error_trace.get_text() + "\n"
        query = query_template.format(inv_info, code)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    #TODO: I wonder if we should split this into two commands: add proof block at the end of the loop; or modify loop invariant
    #so that we give users more control
    def repair_invfail_end(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
        instruction = """Your mission is to fix the invariant not satisfied error at end of the loop for the following code. Basically, you should add the proof blocks related to the loop invariants at the end of the loop, or modify the existing loop invariants to make them correct. DO NOT change the existing proof functions.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        examples = self.get_examples("inv-end")
        query_template = "Failed invariant at end of the loop\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        error_trace = verus_error.trace[0]
        line_info = f"Line {error_trace.lines[0]}-{error_trace.lines[1]}:\n"
        inv_info = line_info + error_trace.get_text() + "\n"
        query = query_template.format(inv_info, code)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    def repair_arithmetic_flow(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system

        error_trace = verus_error.trace[0]

#This sentence was removed from the prompt. It was needed for function pre-condition inference, I remember
#"If the program does not offer a bound, you can add a constant bound like 10000."

        instruction = "Your mission is to fix the arithmetic underflow/overflow error for the following code. Basically, for each variable involved in the expression `" + error_trace.get_highlights()[0] + "' in line `" + error_trace.get_text().strip() + "' of the program, please add BOTH a lower bound (i.e. x > ...) AND an upper bound (i.e., x < ...) as a loop invariant. If the variable is a loop index variable, make sure that its lower bound (e.g., its initial value at the beginning of the loop) and upper bound (based on the loop-exit condition) are specified as loop invariants. Do not miss any variable in `" + error_trace.get_highlights()[0] + "', and do NOT add bound information related to any other variables. Please do not change function post-conditions." 

        instruction += """
        Response requirements:
        Respond with the verus code only, do not include any explanation.
        You should only add loop invariants, and you should NOT make any other changes to the program.
        """

        examples = self.get_examples("aritherr")
        query_template = "Arithmetic underflow/overflow \n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        line_info = f"Line {error_trace.lines[0]}-{error_trace.lines[1]}:\n"
        inv_info = line_info + error_trace.get_text() + "\n"
        query = query_template.format(inv_info, code)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)
   
    def repair_default(self, code: str, verus_error: VerusError, num=1) -> str:
        """
        The default function to repair the code.
        
        TODO(@cyy): This function is not implemented yet.
        """
        system = self.default_system
        instruction = """Your mission is to fix the error for the following code. Basically, you should add/modify/delete the proof blocks, assetions and loop invariants related to the error.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        examples = self.get_examples("default")
        query_template = "{}\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        error_text = verus_error.error_text
        if len(verus_error.trace) == 0:
            self.logger.warning("No trace information in the error.")
            return code
        trace = verus_error.trace[0]
        line_info = f"Line {trace.lines[0]}-{trace.lines[1]}:\n"
        error_info = line_info + trace.get_text() + "\n"

        query = query_template.format(error_text, error_info, code)
        with open("default-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)

    def suggest_spec(self, code: str, num=1) -> str:

        #Normal route of assertion fixing
        system = self.default_system
        instruction = "Your mission is to append the input comment with Verus-style specification. If the input comment talks about precondition, please append the comment with Verus-style `requires'; if the input comment talks about postcondition, please append the comment with Verus-style `ensures'. Remember that you should not call any excutable function in requires/ensures clause."

        examples = self.get_examples("comment2spec")

        query_template = "\nComments to append:\n```\n{}```\n"
        query = query_template.format(code)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)


    def repair_veval(self, code, write_file="", max_attempt=1, func_name=None, failure_type=None, temp_dir=None, triplet=None):

        f2VerusErrorType = {
                "precondfail": VerusErrorType.PreCondFail,
                "postcondfail": VerusErrorType.PostCondFail,
                "invfailfront": VerusErrorType.InvFailFront,
                "invfailend": VerusErrorType.InvFailEnd,
                "invariantfail": VerusErrorType.InvFailFront,
                "assertfail": VerusErrorType.AssertFail,
                "assertfaillemma": VerusErrorType.AssertFail,
                "arithmeticflow": VerusErrorType.ArithmeticFlow,
                "mismatchedtype": VerusErrorType.MismatchedType,
                "veclen": VerusErrorType.PreCondFailVecLen,
        }
        label_repair_func = {
            VerusErrorType.PreCondFail: self.repair_precond_error,
            VerusErrorType.PostCondFail: self.repair_postcond_error,
            VerusErrorType.InvFailFront: self.repair_invfail_front,
            VerusErrorType.InvFailEnd: self.repair_invfail_end,
            VerusErrorType.AssertFail: self.repair_assertion_error,
            VerusErrorType.ArithmeticFlow: self.repair_arithmetic_flow,
            VerusErrorType.MismatchedType: self.debug_type_error,
            VerusErrorType.PreCondFailVecLen: self.repair_precond_veclen_error,
        }
        failed_repair_func = {
            VerusErrorType.AssertFail: self.repair_assertion_error_with_proof_func,
        }

        failure_type_to_fix = f2VerusErrorType[failure_type]

        failed_last_time = 0

        fixed_one_error = False

        attempt = 0
        while attempt < max_attempt:
            attempt += 1

            veval = VEval(code, write_file, triplet, self.logger)
            veval.eval(func_name=func_name)
        
            score = veval.get_score()
            #if score.is_correct():
            #    sys.stderr.write(f"All errors are fixed within {attempt - 1} steps!!!")
            #    return code

            failures = veval.get_failures()
            if len(failures) == 0:
                sys.stderr.write("No error found in the code, but the code is still incorrect.")
                return code

            cur_failures = [f for f in failures if f.error == failure_type_to_fix]
            num_cur_failure = len(cur_failures)
            if num_cur_failure == 0:
                if not failure_type == "invariantfail":
                    sys.stderr.write("Verus did not find errors of the speciifed type")
                    return code
                else:
                    #let's search for InvFailEnd
                    failure_type_to_fix = VerusErrorType.InvFailEnd
                    cur_failures = [f for f in failures if f.error == failure_type_to_fix]
                    num_cur_failure = len(cur_failures)
                    if num_cur_failure == 0:
                        sys.stderr.write("Verus did not find errors of the speciifed type")
                        return code

            cur_failure = cur_failures[0]

            repair_func = label_repair_func[cur_failure.error]
            if failure_type == "assertfaillemma":
                repair_func = self.repair_assertion_error_with_proof_func

            num = 5 if failed_last_time > 0  else 3
            repaired_candidates = repair_func(code, cur_failure, num=num)
            for i, new_code in enumerate(repaired_candidates):
                if not new_code:
                    sys.stderr.write("An unrepairable error was encountered. Will give up remaining repair attempt.")
                    return code
                new_code = clean_code(new_code)
                new_code, _ = self.debug_type_error(new_code, write_file, triplet)
                if not new_code:
                    sys.stderr.write("An unrepairable error was encountered. Will give up remaining repair attempt.")
                    return code

                #TODO: is this comparison taking time?
                if new_code == code:
                    #in plugin, it is really not a good idea to not make any change
                    break

                sys.stderr.write("Generated candidate:"+new_code)

                new_veval = VEval(new_code, write_file, triplet, self.logger)
                new_veval.eval(func_name=func_name)
                new_score = new_veval.get_score()

                if temp_dir:
                    cur_failure_str = cur_failure.error.name
                    err_lines = cur_failure.get_text().splitlines()
                    with open(os.path.join(temp_dir, f"repair-{attempt}-{i}-{cur_failure_str}.rs"), "w") as f:
                        f.write(new_code)
                        f.write("\n\n// ")
                        f.write("\n// ".join(err_lines))
                        f.write("\n\n// " + str(new_score).replace("\n", "\n// "))

                if new_score.is_correct():
                    sys.stderr.write(f"All errors are fixed within {attempt} steps!!!")
                    return new_code
                
                #Test: adding a houridni run after each repair, just in case a correct version actually already exists
                hdn_code = self.hdn.run(new_code, write_file, triplet)[1]
                hdn_veval = VEval(hdn_code, write_file, triplet, self.logger)
                hdn_score = hdn_veval.eval_and_get_score()
                if hdn_score.is_correct():
                    sys.stderr.write("Verus succeeded with hdn!!")
                    return hdn_code

                new_num_cur_failure = len([f for f in new_veval.get_failures() if f.error == cur_failure.error])
                if new_num_cur_failure < num_cur_failure and new_score.is_good_repair(score):
                    code = new_code
                    sys.stderr.write(f"Step {attempt}: {cur_failure.error} is fixed.")
                    fixed_one_error = True
                    failed_last_time = 0
                    break
            failed_last_time += 1
            #TODO: not sure about this
            if fixed_one_error:
                break
        return code
    

    def run(self, input_file, main_file, func_name=None, failure_type=None, extract_body=False, failure_exp=None, extra_args=""):
        if main_file == '' or input_file == main_file:
            target_file = input_file
            submodule = None
        else:
            target_file = main_file
            relative_path = os.path.relpath(input_file, os.path.dirname(main_file))
            submodule = relative_path.replace('.rs', '').replace('/', '::')
        triplet = [target_file, submodule, extra_args]
        code = open(input_file).read()
        # backup
        try:
            open(input_file + ".bak", "w").write(code)
        except:
            pass

        if failure_type == "suggestspec":
            #This is not really a repair
            #to generate spec based on comment
            codelines = code.split("\n")
            if codelines[0].lstrip().startswith("//"):
                linecomment = True
            else:
                linecomment = False

            cand = self.suggest_spec(code)[0]

            import re
            newcodelines = []
            for l in cand.split("\n"):
                #if LLM added some symbol lines or empty lines, we should skip
                if linecomment and l.lstrip().startswith("//"):
                    newcodelines.append(l)
                elif not linecomment:
                    if l.lstrip().startswith("/*") or l.lstrip().startswith("*/") or re.match(r'\w', l.lstrip()):
                        newcodelines.append(l)

            code = "\n".join(newcodelines)
        else:
            if not func_name:
                sys.stderr.write('function name is not specified')
                print(code, end="")
                return 

            #it is very hard to decide what should be max_attempt
            code = self.repair_veval(code, input_file, max_attempt=2, func_name=func_name, failure_type=failure_type, triplet=triplet)

            if extract_body and func_name:
                code = get_func_body(code, func_name, self.config.util_path)

        print(code, end="")

#        with open(output_file, "w") as wf:
#            wf.write(code)
#        return code


def main():
# Parse arguments
    parser = argparse.ArgumentParser(description='Verus Copilot')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--input', default='input.rs', help='Path to target file, can be same as main file')
    parser.add_argument('--main_file', default='', help='Path to main file with main function, empty if same as input')
    parser.add_argument('--toml_file', default='', help='Path to toml file')
    parser.add_argument('--func', default='', help='the function to fix')
    parser.add_argument('--ftype', default='', help='the type of repair function to call')
    parser.add_argument('--exp', default='', help='the failing expression')
    args = parser.parse_args()

    if args.toml_file:
        cargo_toml = tomli.loads(open(args.toml_file).read())
        extra_args = cargo_toml['package']['metadata']['verus']['ide']['extra_args']
    else:
        extra_args = ""


    # Check if config file exists
    if not os.path.isfile(args.config):
        sys.stderr.write('Config file does not exist')
        return

    config = json.load(open(args.config))
    config = AttrDict(config)
    verus.set_verus_path(config.verus_path)

    #TODO: is logger needed at all?
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(__name__)

    if not args.ftype:
        sys.stderr.write('failure type is not specified')
        return 

    if args.ftype == "fungen":
        if not args.func:
            sys.stderr.write('function name is not specified')
            return 

        from generation import Generation
        runner = Generation(config, logger)
        runner.run_simple(args.input, args.main_file, args.func, extract_body = True, extra_args = extra_args)
    else:
        runner = Refinement(config, logger)
        if args.ftype == "assertfaillemma":
            runner.run(args.input, args.main_file, args.func, args.ftype, extract_body = False, failure_exp = args.exp, extra_args = extra_args)
        else:
            runner.run(args.input, args.main_file, args.func, args.ftype, extract_body = True, failure_exp = args.exp, extra_args = extra_args)

if __name__ == '__main__':
    main()
