import sys
import os
import argparse
import logging
import json
from utils import AttrDict
from infer import LLM
from houdini import houdini
from utils import fix_one_type_error_in_code, clean_code
from utils_rustmerger import get_all_relevant_code
import openai
from veval import verus, VEval, VerusErrorType, VerusError, VerusErrorLabel
import subprocess
from utils import get_func_body

class Refinement:
    def __init__(self, config, logger, v_param = None):
        self.config = config
        self.llm = LLM(config, logger)
        self.logger = logger
        self.hdn = houdini(config, v_param)

        #Needed for multi-file projects
        self.veval_param = v_param

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

    def debug_type_error(self, code: str, verus_error: VerusError = None, num = 1) -> str:
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

            veval = VEval(code, self.veval_param, self.logger)
            veval.eval()
            failures = veval.get_failures()
            if len(failures) == 0:
                self.logger.info(f"Verus succeeded!!")
                return code, 0

            has_typeerr = False
            fixed_typeerr = False
            for cur_failure in failures: 
                if cur_failure.error == VerusErrorType.MismatchedType:
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

    def repair_mismatched_type(self, code: str, verus_error: VerusError, num=1, temp=1.0) -> str:
        del temp # unused
        new_code, errors = self.debug_type_error(code, verus_error, num)
        if errors == 0 and new_code:
            return [new_code]
        
        codes = self.repair_default(code, verus_error, num)
        for i, new_code in enumerate(codes):
            new_code = clean_code(new_code)
            new_code, _ = self.debug_type_error(new_code)
            codes[i] = new_code
        return codes


    def repair_unexpected_proof_block(self, code: str, verus_error: VerusError, num=1) -> str:
        #We can simply remove the enclosing proof{ and }; no need to use LLM
        if (verus_error.error != VerusErrorType.UnxProofBlock):
            self.logger.warning("a non unexpected-proof-block error is passed to repair_unexpected_proof_block")
        else:
            #problematic proof block line number ranges
            err_trace = verus_error.trace[0]
            line_start = err_trace.get_lines()[0]
            line_end = err_trace.get_lines()[1]

            self.logger.info(f"Fixing an unexpected proof block error Line {line_start} -- {line_end} in the original file")

            #check if the first and last lines are indeed proof { and }
            codes = code.split("\n")
            line_start_str = codes[line_start-1]
            line_end_str = codes[line_end-1]
            if ''.join(line_start_str.split()) != "proof{":
                self.logger.warning(f"Line {line_start}: {line_start_str} cannot be handled. Fix attempt failed.")
                return []
            elif not line_end_str.lstrip().startswith("}"):
                self.logger.warning(f"Line {line_end}: {line_end_str} cannot be handled. Fix attempt failed.")
                return []

            #Let's just remove the enclosing proof block

            del codes[line_start - 1]
            #since line_start is already deleted, so we should do -2 now
            del codes[line_end - 2]

            newcode = "\n".join(codes)
            self.logger.info("UnxProofBlock error fixed.")
            #print(newcode)

            if newcode:
                return [newcode]
            else:
                return []



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

        examples = ""
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"
        query = query_template.format(assertion_info, code)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.2)
    
 
    def repair_assertion_error_with_proof_func(self, code: str, verus_error: VerusError, num=1) -> str:

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

#If Q is a spec function, please add two asserts: the first one should directly assert Q, and the second one should inline part of Q that is relevant to the proof of P and put that in an assert. Make sure to instantiate function parameters properly during the inlining, and do NOT change the spec function content otherwise.

    def repair_assertion_error_with_prepost(self, code: str, verus_error: VerusError, num=1, temp=1.0) -> str:

        system = self.default_system
        instruction = """Your mission is to fix the assertion error for the following code by leveraging function pre-conditions (i.e., the requires clause). 
        Here are the steps you should take.
        Step 1. If the failing assert does not have a proof block associated with it, please append it with a proof block in the form of ``assert(...) by {}''.
        Step 2. Check which part of the function pre-condition in the `requires' clause (e.g., Q) can help prove this failed assert(P). Then, please add an assert(Q) to the assert(P) by {..} block. Please ONLY include the relevant part of the pre-condition here.

You can refer to the CODE CONTEXT session to see the content of related code. But, do NOT include the Context in your response.

Response with the Rust code only, do not include any explanation."""

        examples = self.get_examples("assert-postpre")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"

        query = query_template.format(assertion_info, code)

        with open("assert-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=temp)


        #Step 2. Decide the quantifier instantiation value V: what value `k' needs to take in the quantifier assert, so that the corresponding implication can prove the failed assert. V could be a constant value or a variable expression involved in the failed assert.
    def repair_assertion_error_with_trigger(self, code: str, verus_error: VerusError, num=1, temp=1.0) -> str:
        #This is particularly designed to help resolve trigger mismatch

        system = self.default_system

        examples = self.get_examples("assert-trigger")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"

        instruction = f"""Your mission is to help the verifier prove the failed assert statement. Here are the steps you should take:
        Step 1. Check the forall assert (i.e., assert on `forall |k| ...' ) that is inside the proof block of the failed assert. Identify its trigger expression that is right after the #[trigger] tag in it.
        The verifier has to see such an trigger expression to know how to instantiate the forall-assert. The lack of such an expressio is likely the reason for the assert failure.
        Step 2. Add to the proof block an assert statement that contains the trigger expression. Carefully select what variable to use in E, so that this new assert is relavent to the failed assert.

Please write down how you conduct these 3 steps in comments.
Response with the Rust code only, do not include any explanation."""


        query = query_template.format(assertion_info, code)

        with open("assert-trigger-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=temp)

    def repair_assertion_error_with_imply(self, code: str, verus_error: VerusError, num=1, temp=1.0) -> str:


        codelines = code.split("\n")
        assertstmt = verus_error.trace[0].get_text()
        assertline = verus_error.trace[0].lines[0]
#        sys.stderr.write(re.sub(r"assert(.*)==>(.*);", r"assert \1 imply \2 by {\nassert(\2);\n}", error_trace.get_text()))

        import re
        indent = re.search(r"(.*)assert.*", assertstmt).group(1)

        needLLM=False

        if assertstmt.rstrip().endswith(";"): 
            imply_pattern = r"assert.*==>(.*)\);"
        elif assertstmt.rstrip().endswith(")"):
            imply_pattern = r"assert.*==>(.*)\)"
        elif assertstmt.rstrip().endswith("by") or assertstmt.rstrip().endswith("{"):
            imply_pattern = r"assert.*==>(.*)\)\s*by"
        else:
            needLLM=True

        if not needLLM:
            implied = re.search(imply_pattern, assertstmt).group(1)
            notriggerImplied = re.sub(r"#\s*\[trigger\]","",implied.lstrip())
            presumption = re.search(r"assert\s*\(\s*forall\s*(.*)==>.*", assertstmt).group(1)

            newassert_template1 = "{}assert forall {} implies {}"
            newassert_template2 = "{}\tassert({});"

            newcodelines = []
            toappend=False
            for index, code in enumerate(codelines):
                if index == assertline - 1:
                    if assertstmt.strip().endswith("{"):
                        newcodelines.append(newassert_template1.format(indent, presumption, implied) + " by {")
                        newcodelines.append(newassert_template2.format(indent,notriggerImplied))
                    elif assertstmt.strip().endswith(";"):
                        newcodelines.append(newassert_template1.format(indent, presumption, implied) + " by")
                        newcodelines.append(indent+"{")
                        newcodelines.append(newassert_template2.format(indent,notriggerImplied))
                        newcodelines.append(indent+"};")
                    elif assertstmt.strip().endswith("by"):
                        newcodelines.append(newassert_template1.format(indent, presumption, implied) + " by")
                        toappend=True
                    elif assertstmt.strip().endswith(")"):
                        newcodelines.append(newassert_template1.format(indent, presumption, implied))
                        toappend=True

                elif index == assertline:
                    newcodelines.append(code)
                    if toappend==True:
                        newcodelines.append(newassert_template2.format(indent,notriggerImplied))
                else:
                    newcodelines.append(code)

            return ["\n".join(newcodelines)]


        #now we go to the LLM way
        system = self.default_system
        instruction = """Your mission is to rewrite this forall-assert using imply. In general, assert(forall <condition> ==> <implication>) can be rewritten as `assert forall <condition> implies <implication> by { assert(implication);}. If the failing assert does not contain any forall, there is nothing you need to do. 

Response with the Rust code only, do not include any explanation."""

        examples = self.get_examples("assert-imply")
        query_template = "Failed assertion\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"

        error_trace = verus_error.trace[0]
        assertion_info = error_trace.get_text() + "\n"

        query = query_template.format(assertion_info, code)

        with open("assert-imply-query.txt", "w") as f:
            f.write(query)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=temp)


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

        instruction = "Your mission is to help Verus prove the array access in the expression `" + error_code.strip() + "' is always in bound --- this expression is on Line {}".format(error_line) + " of the following program. Basically, you should identify all the arrays accessed (e.g., A[k] or A.set(k,..)) in this expression `" + error_code.strip() + "' and add the following loop invariants for EACH array: 1. an invariant that specify the array length (i.e., A.len() == ...); 2. an invariant about the array index not under bound (e.g., k >= 0). \n" 

        instruction += """
        Response requirements:
        Respond with the verus code only, do not include any explanation.
        Respond with the whole program, not just the invariants you added.
        You should only add loop invariants, and you should NOT make any other changes to the program.
        You should NOT change function's pre condition or post conditions.
        """

        examples = []
        query = code

        with open("precond-query.txt", "w") as f:
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)
    
    def repair_postcond_error(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
#        instruction = """Your mission is to fix the post-condition not satisfied error for the following code. Basically, you should add the proof blocks related to the post-condition at the exit point, or modify the existing loop invariants to make them work for the post-condition. Response with the Rust code only, do not include any explanation."""
        instruction = f"""Your mission is to fix the post-condition not satisfied error for the following code. Please follow the following steps: 

Step 1. Add a proof block at or just before a function exit point where the post-condition failure occurred.
Step 2. In this proof block, for each failed post-condition clause, add a corresponding assert.
Step 3. If the asserted post-condition clause relies on variables that are not yet defined, please define them right before the assert.

Note that, the function's ensure block may contain many post-conditions and some post-conditions may caontain many conjunction clauses. Do NOT assert all of them. You should only assert the ones that have failed. 

Response with the Rust code only, do not include any explanation."""

        instruction += "\n\n" + self.proof_block_info
#        examples = self.get_examples("postcond")
        examples = self.get_examples("postcond-expand")

        query_template = "Failed post-condition\n```\n{}```\n"
        query_template += "Failed location\n```\n{}```\n"
        query_template += "\nCode\n```{}```\n"

        location_trace, postcond_trace = verus_error.trace[0], verus_error.trace[1]
        if location_trace.label == VerusErrorLabel.FailedThisPostCond:
            location_trace, postcond_trace = postcond_trace, location_trace

        post_cond_info = ""
        for t in verus_error.expand_trace:
            post_cond_info += f"Line {t.lines[0]}-{t.lines[1]}:\n"
            post_cond_info += t.get_text() + "\n"
       
        location_info = f"Line {location_trace.lines[0]}-{location_trace.lines[1]}:\n"
        location_info += location_trace.get_text() + "\n"

        query = query_template.format(post_cond_info, location_info, code)

        #sys.stderr.write(f"The LLM query is the following: \n {query}\n")

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

    #TODO: we could split this into two commands: add proof block at the end of the loop; or modify loop invariant
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

        system = self.default_system
        instruction = "Your mission is to append the input comment with Verus-style specification. If the input comment talks about precondition, please append the comment with Verus-style `requires'; if the input comment talks about postcondition, please append the comment with Verus-style `ensures'. Please respect the original comment style: do not change a comment block enclosed by /* .. */ to be preceeded by //, and vice versa. Remember that you should not call any excutable function in requires/ensures clause."

        examples = self.get_examples("comment2spec")

        query_template = "\nComments to append:\n```\n{}```\n"
        query = query_template.format(code)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)


    def repair_veval(self, input_file, max_attempt=1, func_name=None, failure_type=None, temp_dir=None):

        code = open(input_file).read()

        f2VerusErrorType = {
                "precondfail": VerusErrorType.PreCondFail,
                "postcondfail": VerusErrorType.PostCondFail,
                "invfailfront": VerusErrorType.InvFailFront,
                "invfailend": VerusErrorType.InvFailEnd,
                "invariantfail": VerusErrorType.InvFailFront,
                "assertfail": VerusErrorType.AssertFail,
                "assertreq": VerusErrorType.AssertFail,
                "asserttrigger": VerusErrorType.AssertFail,
                "assertimply": VerusErrorType.AssertFail,
                "assertfaillemma": VerusErrorType.AssertFail,
                "arithmeticflow": VerusErrorType.ArithmeticFlow,
                "mismatchedtype": VerusErrorType.MismatchedType,
                "veclen": VerusErrorType.PreCondFailVecLen,
        }
        f2RepairFunc = {
                "precondfail": self.repair_precond_error,
                "postcondfail": self.repair_postcond_error,
                "invfailfront":  self.repair_invfail_front,
                "invfailend": self.repair_invfail_end,
                "invariantfail": self.repair_invfail_front,
                "assertfail":  self.repair_assertion_error,
                "assertreq": self.repair_assertion_error_with_prepost,
                "asserttrigger": self.repair_assertion_error_with_trigger,
                "assertimply": self.repair_assertion_error_with_imply,
                "assertfaillemma": self.repair_assertion_error_with_proof_func,
                "arithmeticflow":  self.repair_arithmetic_flow,
                "mismatchedtype":  self.repair_mismatched_type,
                "veclen":  self.repair_precond_veclen_error,
        }
 
#        label_repair_func = {
#            VerusErrorType.PreCondFail: self.repair_precond_error,
#            VerusErrorType.PostCondFail: self.repair_postcond_error,
#            VerusErrorType.InvFailFront: self.repair_invfail_front,
#            VerusErrorType.InvFailEnd: self.repair_invfail_end,
#            VerusErrorType.AssertFail: self.repair_assertion_error,
#            VerusErrorType.ArithmeticFlow: self.repair_arithmetic_flow,
#            VerusErrorType.MismatchedType: self.debug_type_error,
#            VerusErrorType.PreCondFailVecLen: self.repair_precond_veclen_error,
#        }
#        failed_repair_func = {
#            VerusErrorType.AssertFail: self.repair_assertion_error_with_proof_func,
#        }

        failure_type_to_fix = f2VerusErrorType[failure_type]
        fixed_one_error = False

        veval = VEval(code, self.veval_param, self.logger)

    #For multi-file project, we need to run verus-logger here to get a compact view of the project
        if self.veval_param[0] and (failure_type == "asserttrigger" or failure_type == "assertreq"):
            verusLogDir = os.path.join(os.path.dirname(self.veval_param[0]), ".verus-log")
            expand = False
        elif failure_type == "postcondfail":
            verusLogDir = ""
            expand = True
        else:
            verusLogDir = ""
            expand = False

        veval.eval(func_name = func_name, expand = expand, log = verusLogDir)

        #extract related file content 
        context = ""
        if verusLogDir:
            vfile = ""
            for file in os.listdir(verusLogDir):
                if func_name in file and ".vir" in file:
                    self.logger.info(f"Found Verus log file {file}")
                    vfile = os.path.join(verusLogDir, file)
                    break

            context = get_all_relevant_code(os.path.dirname(self.veval_param[0]), 
                                             outputpre="", inputvir=vfile, outputAll="",
                                            excludefile=input_file)
            #self.logger.info(f"This part of the code base is relevant to this function's verification:\n {context}")
            self.logger.info(f"Extracted {len(context)}-char related code")


        score = veval.get_score()

        if score.is_correct(): 
            self.logger.info("Your program is already correctly verified. No change needed.")
            return

        attempt = 0
        #TODO: 1. do we need max_attempt > 1 in plugin? 2. input could already be correct

        failures = veval.get_failures()
        cur_failures = [f for f in failures if f.error == failure_type_to_fix]
        num_cur_failure = len(cur_failures)
        if num_cur_failure == 0:
            if not failure_type == "invariantfail":
                self.logger.warning(f"Verus did not find errors of the specified type {failure_type_to_fix}\n")
                self.logger.warning(f"Verus reports {len(failures)} errors in total.")
                return code
            else:
                #let's search for InvFailEnd
                failure_type_to_fix = VerusErrorType.InvFailEnd
                cur_failures = [f for f in failures if f.error == failure_type_to_fix]
                num_cur_failure = len(cur_failures)
                if num_cur_failure == 0:
                    sys.stderr.write("Verus did not find errors of the speciifed type {failure_type_to_fix}\n")
                    return code

        cur_failure = cur_failures[0]
        repair_func = f2RepairFunc[failure_type]

        while attempt < max_attempt:
            #Debug
            self.logger.info(f"Fix attempt {attempt+1} for {failure_type_to_fix}")

            attempt += 1

            num = 5 if attempt > 1  else 3

            #TODO: should be made conditional
            if context:
                code_context = code + "\n```\n\nContext:\n```\n" + context 
            else:
                code_context = code

            repaired_candidates = repair_func(code_context, cur_failure, num=num)

            for i, new_code in enumerate(repaired_candidates):

                self.logger.info(f"Processing repair-{attempt}-{i} ...")

                #sys.stderr.write(new_code)

                #if not new_code:
                #    sys.stderr.write("An unrepairable error was encountered. Will give up remaining repair attempt.")
                #    return code
                new_code = clean_code(new_code)

                new_veval = VEval(new_code, self.veval_param, self.logger)
                new_veval.eval(func_name=func_name)
                new_score = new_veval.get_score()

                #We check if there are compilation errors in the generated code
                if new_score.compilation_error:
                    new_error = new_veval.get_failures()[0]
                    self.logger.info(f"Patch candidate has compilation error: {new_error.error}.")

                    if new_error.error == VerusErrorType.MismatchedType:
                        new_codes = self.repair_mismatched_type(new_code, new_error, num=1)
                    elif new_error.error == VerusErrorType.UnxProofBlock: 
                        new_codes = self.repair_unexpected_proof_block(new_code, new_error, num=1)
                    else:
                        self.logger.warning("Cannot handle this type of compilation error yet")
                        new_codes = []

                    if len(new_codes) > 0:
                        new_code = clean_code(new_codes[0])
                        new_code = new_code.replace("```", "")

                        if not new_code:
                            self.logger.warning("Empty new code!!")
                            continue

                        new_veval = VEval(new_code, self.veval_param, self.logger)
                        new_veval.eval(func_name=func_name)
                        new_score = new_veval.get_score()
                        #self.logger.info(f"Compilation error: {new_error.error} fixed.")

                        #TODO: what if there is another fixable compilation error in this new code??

                    else:
                        self.logger.warning("Attempt to fix compilation error failed")


                if not new_code:
                    sys.stderr.write("An unrepairable error was encountered. Will give up remaining repair attempt.")
                    continue

                if new_code == code:
                    #in plugin, it is really not a good idea to not make any change
                    self.logger.info("The patch candidate is the same as the original code")
                    continue


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
                

                #Decide whether to accept this repair
                #The criteria vary based on the repair function
                #TODO: this should be a function
                new_num_cur_failure = len([f for f in new_veval.get_failures() if f.error == cur_failure.error])
                if failure_type == "assertreq" or failure_type == "assertimply":
                    if new_num_cur_failure == num_cur_failure:
                    #meant to increase proof clarity, not meant to decrease num of veri errors
                        code = new_code
                        sys.stderr.write(f"Step {attempt}: {cur_failure.error} is helped with.")
                        fixed_one_error = True
                        break

                if new_num_cur_failure < num_cur_failure and new_score.is_good_repair(score):
                    code = new_code
                    sys.stderr.write(f"Step {attempt}: {cur_failure.error} is fixed.")
                    fixed_one_error = True
                    break

                #TODO: may be too time consuming to run
                #self.logger.info("Attempting Houdini algorithm")
                #hdn_failures, hdn_code = self.hdn.run(new_code)
                #if len(hdn_failures) == 0:
                #    sys.stderr.write("Verus succeeded with hdn!!")
                #    return hdn_code

                self.logger.info("This patch is not accepted")
                #self.logger.info(get_func_body(new_code, func_name, self.config.util_path))

            #TODO: not sure about this
            if fixed_one_error:
                break
        return code
    

    def run(self, input_file, func_name=None, failure_type=None, extract_body=False, failure_exp=None, context = ""):

        if failure_type == "suggestspec":
            #This is not really a repair
            #to generate spec based on comment
            code = open(input_file).read()
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
            if not code:
                self.logger.warning("Failed to suggest verus spec. Please try again.")
                return
        else:
            if not func_name:
                sys.stderr.write('function name is not specified')
                return 

            code = self.repair_veval(input_file, max_attempt = 2, func_name=func_name, failure_type=failure_type)

            if extract_body and func_name:
                code = get_func_body(code, func_name, self.config.util_path)

        print(code, end="")
