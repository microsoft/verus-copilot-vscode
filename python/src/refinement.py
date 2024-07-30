import os
import time
import re
import numpy as np
from infer import LLM
from bm25 import BM25
from houdini import houdini
from utils import evaluate, error_process, split_code_by_loop, compare_and_choose_by_loop, split_code_by_loop,split_origin_error_by_interval, count_origin_error_by_interval, merge_outputs, choose_best, ERROR_RANGE, get_func_names, proved_by_verus, merge_with_highlight, merge_with_highlight_post, get_aritherror, is_preconderr_only, get_typeerror, fix_one_type_error_in_code, clean_code, code_change_is_safe, get_nonlinear_lines
import openai
from veval import VEval, VerusErrorType, VerusError, VerusErrorLabel
from houdini import houdini

class Refinement:
    def __init__(self, config, logger):
        self.config = config
        self.llm = LLM(config, logger)
        #self.bm25 = BM25(config.corpus_path)
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
Note, please add the assertion directly for the `proof fn` function and DO NOT use proof block.
You can only use the proof block for the `fn` and `pub fn` functions.

The ghost variable looks like this:
```
let ghost ...; // Added by AI
```

Note, please DO NOT modify all other proof blocks that are not related to the error. Just leave them as they are.
"""

    def rag_debug_inference(self, code, error, retrieved, temp=0.8):
        system = self.default_system

        instruction = """Given the unverified code and the error message, your mission is to edit the proof code to fix the errors.
Response requirements: 
You can only modify by edit/add/delete the proof code between the <edit> </edit> tags.
Response with the modified code only, do not include any other code."""

        examplers = []
        for ret in retrieved:
            examplers.append({"query": ret["code_with_edit"] + "\n" + ret["error"], "answer": ret["changed"]})

        prompt = code + "\n" + error
        # prompt += "\nPlease try to analyze the error and fix it. Remember: \nYou can only modify by edit/add/delete the proof code between the <edit> </edit> tags. \nResponse with the modified code only, do not include any other code."

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examplers, prompt, system, answer_num=self.config.refine_answer_num, max_tokens=2048, temp=temp)

    #TODO: should we just replace rag_debug_inference with rag_debug_inference_test? And remove rag from the name
    #This function is moved from generation.py to here
    #TODO: Houdini should be used
    def rag_debug_inference_test(self, code, error, err_range_msg, retrieved, past=None, temp=0.2):
        system = self.default_system

        instruction = "Given the unverified code and the error message, your mission is to edit the proof code to fix the errors.\nResponse requirements:\n"
        instruction += "Response with the verus code only, do not include any explanation.\n"
        instruction += "You should only make changes to existing loop invariants, and you should NOT make any other changes to the program."

        examplers = []
        for ret in retrieved:
            examplers.append({"query": ret["code"] + "\nHere is the error:\n" + ret["error"], "answer": ret["fixed"]})
        if past is not None:
            examplers += past

        if past is None:
            prompt = code + "\nHere is the error " + err_range_msg + ":\n" + error
            past = []
        else:
            past[-1]["answer"] = code
            prompt = "It still cannot be verified due to the following error " + err_range_msg + ":\n" + error

        prompt += """\
Please analysis the errors from the previous text and it could be helpful for finding the way to fix the following code. Here are some instructions:\n
"""

        consider_afterloop_error = True

        if "mismatched types" in error:
            prompt += "When the error is about `expected type A, found type B' in an expression X, please add the corresponding type casting (e.g., `as A') to corresponding variables that are currently been interpreted as type B.\n"
            consider_afterloop_error = False

        elif "i < vec.view().len()" in error:
            prompt += "When encountering an error about `precondition in other file ... i < vec.view().len(), not satisfied at line X, you should identify all the arrays accessed (e.g., A[k] or A.set(k,..)) on line X and make sure the following three loop invariants ALL exist for EACH array: 1. an invariant about the array length (i.e., A.len() == ...); 2. an invariant about the array index not over bound (e.g., k < A.len()); 3. an invariant about the array index not under bound (e.g., k >= 0). \n" #TODO Shan: we may want to solve this one by itself and leaving the other ones for later
            consider_afterloop_error = False

        else:
            if "invariant not satisfied before loop" in error:
                prompt += "When encountering the invariant not satisfied error before loop, you should check whether the variable or array is used in the current loop. If not, just delete this invariant. If yes, then check whether the value or range of this variable in the loop invariant is consistent with that it was set in the previous code.\n"
                consider_afterloop_error = False
            if "possible arithmetic underflow/overflow" in error:
                prompt += "When encountering the arithmetic underflow/overflow error, you should check 1. You should identify every variable that is read in the loop  (e.g., x[k], y), particularly for array elements like x[k], and add an invariant about the initial value for EACH such variable and array; (e.g., forall |k:int| 0 <= k < x.len() ==> some-property). \n 2. You should identify every array that is read (e.g., x[k]) or written (e.g., x.set(..,..)) in a loop, and add a loop invariant that specifies the bound of the array (e.g., x.len() < ...); Even if an invariant is already specified earlier in the program, please do repeat it in the current loop suitable.\n"
                consider_afterloop_error = False
            if consider_afterloop_error and "invariant not satisfied at end of loop body" in error:
                prompt += "When encountering the invariant not satisfied error, you should only consider the current loop, not the following loops. Try to simulate the loop execution in your mind and find the conflict with the wrong invariant. Write a comment before you write the changed invariant to present why you change it. \n"
            if "not supported" in error:
                prompt += "When encountering the not supported error, the grammar of target line is not supported in Verus. Consider to remove it or change the way to write it.\n"
        
        prompt += "The most important thing is: You should only make changes to existing loop invariants, and you should NOT make any other changes to the program. Response with the complete code, including the unchanged part.\n"

        past.append({"query": prompt, "answer": ""})

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examplers, prompt, system, answer_num=self.config.debug_answer_num, max_tokens=self.config.max_token, temp=temp), past

    def merge_edit(self, code_change, code_with_edit):
        lines = code_with_edit.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("<edit>"):
                break
        indent = lines[i+1][0] * (len(lines[i+1]) - len(lines[i+1].lstrip()))
        if code_change.startswith(indent):
            return re.sub(r"<edit>(.*)</edit>", code_change, code_with_edit, flags=re.DOTALL)
        new_code = ""
        pause = False
        for line in lines:
            if line.startswith("<edit>"):
                new_code += "\n".join([indent + x.strip() for x in code_change.split("\n")]) + "\n"
                pause = True
            elif line.startswith("</edit>"):
                pause = False
            else:
                if not pause:
                    new_code += line + "\n"
            
        return new_code

    def rag_debug(self, code):
        """
        self debug with retrieved code
        """
        score, msg = evaluate(code, self.config.verus_path)
        ret = ""
        code_with_edit = code
        if score[1] > 0:
            self.logger.info("error processing...")
            error = error_process(msg.stderr, self.llm)
            self.logger.info("search for similar code")
            retrieved = self.bm25.search_topk("\n".join(error.splitlines()), k=self.config.n_retrieved)[::-1]
            self.logger.info("generate code")
            changes = self.rag_debug_inference(code, error, retrieved, temp=self.config.refine_temp)
            best_score_single_round = 0
            for code_cg in changes:
                might_code = re.findall(r"```rust(.*)```|```verus(.*)```", code_cg, flags=re.DOTALL)
                if might_code:
                    code_cg = might_code[0][0] if might_code[0][0] else might_code[0][1]
                code_round = self.merge_edit(code_cg, code_with_edit)
                score, _ = evaluate(code_round, self.config.verus_path)
                if (score[1] == 0 and score[0] > 0) or score[0] > best_score_single_round:
                    best_score_single_round = score[0]
                    ret = code_cg
        return ret

#this function is moved from generate.py to here
#TODO: should we replace rag_debug with rag_debug_test? and remove "rag" from the name
#TODO: 1. most of these instructions can be better customized like aritherror_inference in generation.py
#       2. how to integrate this with Houdini needs some thoughts
    def rag_debug_test(self, code, verbose=False, func_name=None):
        """
        self debug with retrieved code
        """
        score, msg = evaluate(code, self.config.verus_path, func_name=func_name)
        ret = code
        if score[1] == 0:
            self.logger.info("Verus has succeeded.")
            return ret

        interval = split_code_by_loop(code)
        ori_error_blocks = split_origin_error_by_interval(msg.stderr, interval)
        for i in range(len(ori_error_blocks)):
            if i == 0 and len(ori_error_blocks) > 1:
                continue     # the first error block is about specification
            code = ret
            interval = split_code_by_loop(code)     # length will not be changed
            error_blocks = split_origin_error_by_interval(msg.stderr, interval)     # length will not be changed
            error_cnt = count_origin_error_by_interval(msg.stderr, interval)        # length will not be changed
            if verbose:
                self.logger.info(error_cnt)
            if error_cnt[i] == 0:
                continue
            err_range_msg = "" if len(error_blocks) == 1 else ERROR_RANGE[i] if i < len(error_blocks)-1 else ERROR_RANGE[-1]
            self.logger.info(f"refine for {err_range_msg}")
            attempt = 0
            best_err_cnt = error_cnt[i] + 1     # prefer to use the changed code even there is no improvement
            score, _ = evaluate(code, self.config.verus_path, func_name=func_name)
            best_score = score[0] - 1   # prefer to use the changed code even there is no improvement
            past = None
            while attempt < self.config.debug_max_attempt:
                self.logger.info("attempt %d, error processing..." % attempt)
                error = error_process(error_blocks[i], self.llm)
                if verbose:
                    self.logger.info(error)
                self.logger.info("search for similar code")
                retrieved = self.bm25.search_topk(error, k=self.config.n_retrieved)[::-1]
                if verbose:
                    for r in retrieved:
                        self.logger.info(r["code"])
                        self.logger.info(r["error"])
                        self.logger.info(r["fixed"])
                self.logger.info("generate code...")
                while len(retrieved) > -1:
                    try:
                        codes, past = self.rag_debug_inference_test(code, error, err_range_msg, retrieved, past, temp=self.config.debug_temp)
                        break
                    except openai.BadRequestError as e:
                        if e.code == "context_length_exceeded":
                            self.logger.info("context length exceeded, try to reduce the number of retrieved code")
                            retrieved = retrieved[1:]
                        else:
                            raise e

                best_err_cnt_round = 100000
                best_score_round = 0
                original_code = code
                for code_round in codes:
                    might_code = re.findall(r"```rust(.*)```|```verus(.*)```", code_round, flags=re.DOTALL)
                    if might_code:
                        code_round = might_code[0][0] if might_code[0][0] else might_code[0][1]
                    if verbose:
                        self.logger.info(code_round)
                    myscore, _ = evaluate(code_round, self.config.verus_path, func_name=func_name)
                    if myscore[1] == 0:
                        self.logger.info("All Done! Verus has succeeded.")
                        return code_round
                    if len(ori_error_blocks) > 1:
                        int1 = split_code_by_loop(original_code)[i]-1
                        int2 = split_code_by_loop(code_round)[i]-1
                    else:
                        int1, int2 = 0, 0
                    code_round_merge = merge_outputs(original_code, code_round, self.config.verus_path, st1=int1, st2=int2)
                    if verbose:
                        self.logger.info("merged code")
                        self.logger.info(code_round_merge)
                    score, msg_round = evaluate(code_round, self.config.verus_path, func_name=func_name)
                    interval_round = split_code_by_loop(code_round)
                    err_cnt = count_origin_error_by_interval(msg_round.stderr, interval_round)[i]
                    # if score[0] > best_score_round or (score[0] == best_score_round and err_cnt < best_err_cnt_round):
                    if err_cnt < best_err_cnt_round:
                        best_err_cnt_round = err_cnt
                        best_score_round = score[0]
                        code = code_round
                    score, msg_round = evaluate(code_round_merge, self.config.verus_path, func_name=func_name)
                    interval_round = split_code_by_loop(code_round_merge)
                    err_cnt = count_origin_error_by_interval(msg_round.stderr, interval_round)[i]
                    # if score[0] > best_score_round or (score[0] == best_score_round and err_cnt < best_err_cnt_round):
                    if err_cnt < best_err_cnt_round:
                        best_err_cnt_round = err_cnt
                        best_score_round = score[0]
                        code = code_round_merge
                if verbose:
                    self.logger.info(code)
                score, msg = evaluate(code, self.config.verus_path, func_name=func_name)
                interval = split_code_by_loop(code)
                error_blocks = split_origin_error_by_interval(msg.stderr, interval)
                error_cnt = count_origin_error_by_interval(msg.stderr, interval)
                err_cnt = error_cnt[i]
                # if score[0] > best_score or (score[0] == best_score and err_cnt < best_err_cnt):
                if err_cnt < best_err_cnt:
                    self.logger.info("better proof code found")
                    best_err_cnt = err_cnt
                    best_score = score[0]
                    ret = code
                    if err_cnt == 0:
                        break
                attempt += 1
        if verbose:
            self.logger.info(ret)
        return ret

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
                newcode = fix_one_type_error_in_code(code, verus_error.trace[0], verbose=False)
                if newcode:
                    code = newcode

        #check if there is any type errors in the code; if so, fix
        while rnd < max_rnd:
            rnd = rnd + 1

            veval = VEval(code, self.logger)
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
                    newcode = fix_one_type_error_in_code(code, cur_failure.trace[0], verbose=False)
                    #when newcode is "", the above function failed to fix any type error
                    if newcode:
                        fixed_typeerr = True
                        code = newcode
          #              self.logger.info("[Fixed Type Error Round {}]".format(rnd))
                        break
                    else:
                        #this type error is unfixable, let's move on to next error
                        #code = self.repair_SeqSyntax_error(code, cur_failure, 1)[0]
                        continue
                if not fixed_typeerr:
                    #not able to fix any type error in this program, no need to try again
                    break

            if not has_typeerr: 
          #      self.logger.info("No more type error.")
                return code, 0

            if not fixed_typeerr:
                self.logger.info("Remaining type errors are unfixable.")
                self.logger.info(cur_failure.trace[0].get_text())
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
            newcode = self.repair_assertion_error_with_lemma_func(newcode, verus_error, 1,                                            ["vec_push", "vec_remove"])[0]
            newcode = clean_code(newcode)
            newcode, _ = self.debug_type_error(newcode)
            if newcode:
                did_special_fix = True
                code = newcode

        if did_special_fix:
            return code
        else:
            return ""
    
    def repair_nonlinear_arith_error(self, code: str, verus_error: VerusError, num=1) -> str:
        """
        This function is used to repair the nonlinear arithmetic error
        """
        system = self.default_system
        instruction = """Your mission is to add assert statements into the given Rust function to help Verus prove non-linear properties.

Here are some principles that you have to follow:
Response with the Rust code only, do not include any explanation.
You should only add assertions with non-linear property if necessary in the following ways, and you should not make any other changes to the program.

#### 1. Nonlinear Arithmetic
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

#### 2. Nonlinear Arithmetic Overflow
Verus cannot prove that a non-linear expression does not overflow unless you tell it the range of the expression.
For example, if a non-linear expression x*x*x is used in the program, only tell Verus 0 <= x <= 10 is not enough, we have to write the following statement to help Verus prove no arithmetic overflow for x*x*x:

    assert(0 < x*x*x <= 10 * 10 * 10) by (nonlinear_arith)
        requires
            0 < x,
            x <= 10,
            {}

In this example, the `nonlinear_arith' keyword enables Verus to use its non-linear reasoning, and 
the `requires' statements should include all the variable bound information needed to prove no-arithmetic overflow.

#### Task
Please check the given program, and add nonlinear_arith assertion for the following assertions:
"""
        nl_lines = get_nonlinear_lines(code, self.logger)
        if not nl_lines:
            return []
        for i, (st, ed, text) in enumerate(nl_lines):
            instruction += "{}. Lines {}-{}:\n{}\n".format(i+1, st, ed, text)

        print(instruction)
        examples = []
        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, code, system, answer_num=num, max_tokens=4096, temp=0.5)

    
    def repair_assertion_error(self, code: str, verus_error: VerusError, num=1) -> str:
        nl_repairs = self.repair_nonlinear_arith_error(code, verus_error, num)
        if nl_repairs:
            return nl_repairs

        #Check if this assertion error needs special API treatment
        newcode = self.repair_special_assertion_error(code, verus_error, num)
        if newcode:
            return [newcode]

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

    def repair_invfail_end(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system
        instruction = """Your mission is to fix the invariant not satisfied error at end of the loop for the following code. Basically, you should add the assertion (in proof block) of the failed loop invariant at the end of the loop. DO NOT change the existing proof functions. If you think the failed invariant is incorrect, you can delete/correct it.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        examples = self.get_examples("inv-end")
        query_template = "Failed invariant at end of the loop\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        error_trace = verus_error.trace[0]
        line_info = f"Line {error_trace.lines[0]}-{error_trace.lines[1]}:\n"
        inv_info = line_info + error_trace.get_text() + "\n"
        query = query_template.format(inv_info, code)

        return self.llm.infer_llm(self.config.aoai_debug_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=1.0)

    def repair_arithmetic_flow(self, code: str, verus_error: VerusError, num=1) -> str:
        system = self.default_system

        error_trace = verus_error.trace[0]

#This sentence was removed from the prompt. It was needed for function pre-condition inference, I remember
#"If the program does not offer a bound, you can add a constant bound like 10000."

        instruction = "Your mission is to fix the arithmetic underflow/overflow error for the following code. Basically, for each variable involved in the expression `" + error_trace.get_highlights()[0] + "' in line `" + error_trace.get_text().strip() + "' of the program, please add BOTH a lower bound (i.e. x > ...) AND an upper bound (i.e., x < ...) as an assertion or a loop invariant if they are in a loop body. If the variable is a loop index variable, make sure that its lower bound (e.g., its initial value at the beginning of the loop) and upper bound (based on the loop-exit condition) are specified as loop invariants. Do not miss any variable in `" + error_trace.get_highlights()[0] + "', and do NOT add bound information related to any other variables. Please do not change function post-conditions."

        instruction += """
        Response requirements:
        Respond with the verus code only, do not include any explanation.
        You should only add loop invariants, and you should NOT make any other changes to the program.

        Hint for the upper bound:
        1. For the upper bound, you don't always need to find the exact or strict value. Your mission is to find a provable bound for Verus.
        2. If there is a non-linear upper bound, you can use a constant to represent part of the expression (e.g., a * CONSTANT_RELATED_TO_b) to make it linear. However, ensure that at least one variable remains (DO NOT USE A CONSTANT TO REPLACE THE WHOLE NON-LINEAR). This approach makes it easier to prove.
        3. If the upper bound is a loop invariant, please consider using the loop index variable in the upper bound.
        """

        examples = self.get_examples("aritherr")
        query_template = "Arithmetic underflow/overflow \n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        line_info = f"Line {error_trace.lines[0]}-{error_trace.lines[1]}:\n"
        inv_info = line_info + error_trace.get_text() + "\n"
        query = query_template.format(inv_info, code)

        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=1.0)
    
    def repair_mismatched_type(self, code: str, verus_error: VerusError, num=1) -> str:
        new_code, errors = self.debug_type_error(code, verus_error, num)
        if errors == 0 and new_code:
            return [new_code]
        
        codes = self.repair_default(code, verus_error, num)
        for i, new_code in enumerate(codes):
            new_code = clean_code(new_code)
            new_code, _ = self.debug_type_error(new_code)
            codes[i] = new_code
        return codes
   
    def repair_default(self, code: str, verus_error: VerusError, num=1) -> str:
        """
        The default function to repair the code.
        
        TODO(@cyy): This function is not implemented yet.
        """
        system = self.default_system
        instruction = """Your mission is to fix the error for the following code. Basically, you should add/modify/delete the proof blocks, assetions and loop invariants related to the error.

Response with the Rust code only, do not include any explanation."""
        instruction += "\n\n" + self.proof_block_info

        # FIXME: Now I add the `Seq` knowledge by default
        seq_knowledge = "Here is the usage for Seq in Verus you can refer:\n{}\n\n"
        seq_examples = self.get_text_examples("seq")
        seq_knowledge = seq_knowledge.format("\n".join(seq_examples))
        instruction += "\n\n" + seq_knowledge

        examples = self.get_examples("default")
        query_template = "{}\n```\n{}```\n"
        query_template += "\nCode\n```\n{}```\n"
        
        error_text = verus_error.error_text
        if len(verus_error.trace) == 0:
            self.logger.warning("No trace information in the error.")
            return code
        trace = verus_error.trace[0]
        line_info = f"Line {trace.lines[0]}-{trace.lines[1]}:\n"
        error_info = line_info + verus_error.get_text() + "\n"

        query = query_template.format(error_text, error_info, code)
        with open("default-query.txt", "w") as f:
            f.write(instruction + "\n")
            f.write(query)
        
        return self.llm.infer_llm(self.config.aoai_generation_model, instruction, examples, query, system, answer_num=num, max_tokens=4096, temp=0.5)
    
    def repair_remove_lines(self, code: str, verus_error: VerusError, num=1) -> str:
        if verus_error in [VerusErrorType.PreCondFail, VerusErrorType.PostCondFail]:
            return code

        if len(verus_error.trace) == 0:
            self.logger.warning("No trace information in the error.")
            code = self.houdini.run(code)
            return code
        
        trace = verus_error.trace[0]
        code_lines = code.splitlines()
        new_code_lines = code_lines[:trace.lines[0] - 1] + code_lines[trace.lines[1]:]

        return "\n".join(new_code_lines)


    def get_one_failure(self, verus_errors):
        '''
        This function tries to prioritize among a group of Verus errors
        '''

        #type error gets first priority
        for verus_error in verus_errors:
            if verus_error.error == VerusErrorType.MismatchedType:
                return verus_error

        #array-length precondition gets second priority
        for verus_error in verus_errors:
            if verus_error.error == VerusErrorType.PreCondFailVecLen:
                return verus_error

        #arith overflow 3rd priority
        for verus_error in verus_errors:
            if verus_error.error == VerusErrorType.ArithmeticFlow:
                return verus_error

        #default
        return verus_errors[-1]



    def repair_veval(self, code, max_attempt=5, func_name=None, temp_dir=None):
        label_repair_func = {
            VerusErrorType.PreCondFail: self.repair_precond_error,
            VerusErrorType.PostCondFail: self.repair_postcond_error,
            VerusErrorType.InvFailFront: self.repair_invfail_front,
            VerusErrorType.InvFailEnd: self.repair_invfail_end,
            VerusErrorType.AssertFail: self.repair_assertion_error,
            VerusErrorType.ArithmeticFlow: self.repair_arithmetic_flow,
            VerusErrorType.MismatchedType: self.repair_mismatched_type,
            VerusErrorType.PreCondFailVecLen: self.repair_precond_veclen_error,
        }
        failed_repair_func = {
            VerusErrorType.AssertFail: self.repair_assertion_error_with_proof_func,
        }

        #Let's first add loop-isolation to see if it solves all the problem
        if not "loop_isolation(false)" in code:
            from generation import Generation
            mygen = Generation(self.config, self.logger)
            code = mygen.insert_loop_isolation(code)


        print("to start repair")
        #Adjustable Configuration: # of simple fix before switching to more creative ones
        simpleRepair_per_failure = 3
        remove_lines_per_failure = 5
        
        failed_last_time = 0
        attempt = 0
        while attempt < max_attempt:
            attempt += 1

            veval = VEval(code, self.logger)
            veval.eval(func_name=func_name)
            score = veval.get_score()
            if score.is_correct():
                self.logger.info(f"All errors are fixed within {attempt - 1} steps!!!")
                break

            failures = veval.get_failures()
            if len(failures) == 0:
                self.logger.info(code)
                raise Exception("No error found in the code, but the code is still incorrect.")

            cur_failure = self.get_one_failure(failures)
            num_cur_failure = len([f for f in failures if f.error == cur_failure.error])

            if failed_last_time > remove_lines_per_failure:
                new_code = self.repair_remove_lines(code, cur_failure)
                failed_last_time = 1
                if temp_dir:
                    cur_failure_str = cur_failure.error.name
                    err_lines = cur_failure.get_text().splitlines()
                    with open(os.path.join(temp_dir, f"repair-{attempt}-remove-{cur_failure_str}-origin.rs"), "w") as f:
                        f.write(code)
                        f.write("\n\n// ")
                        f.write("\n// ".join(err_lines))
                        f.write("\n\n// " + str(score).replace("\n", "\n// "))
                    with open(os.path.join(temp_dir, f"repair-{attempt}-remove-{cur_failure_str}.rs"), "w") as f:
                        f.write(new_code)
                new_veval = VEval(new_code, self.logger)
                new_veval.eval(func_name=func_name)
                new_score = new_veval.get_score()
                if new_score.is_correct():
                    self.logger.info(f"All errors are fixed within {attempt} steps!!!")
                    return new_code

            num = 5 if failed_last_time > 0  else 3
            if failed_last_time > simpleRepair_per_failure and cur_failure.error in failed_repair_func:
                repair_func = failed_repair_func[cur_failure.error]
                self.logger.info(f"Step {attempt}: {cur_failure.error} (failed last {failed_last_time} time) with num={num}.")
            elif cur_failure.error not in label_repair_func:
                repair_func = self.repair_default
                self.logger.info(f"Step {attempt}: {cur_failure.error} (not supported yet) with num={num}.")
            else:
                repair_func = label_repair_func[cur_failure.error]
                self.logger.info(f"Step {attempt}: {cur_failure.error} with num={num}.")
            self.logger.info(f"  Current score: {score}")

            all_failed = True
            repaired_candidates = repair_func(code, cur_failure, num=num)
            for i, new_code in enumerate(repaired_candidates):
                if not new_code:
                    self.logger.warning("An unrepairable error was encountered.")
                    continue
                new_code = clean_code(new_code)
                new_code = new_code.replace("```", "")

                new_veval = VEval(new_code, self.logger)
                new_veval.eval(func_name=func_name)
                new_score = new_veval.get_score()
                if new_score.compilation_error:
                    new_error = self.get_one_failure(new_veval.get_failures())
                    self.logger.info(f"Fix failed due to compilation error: {new_error.error}.")
                    new_code = self.repair_mismatched_type(new_code, new_error, num=1)[0]
                    new_code = clean_code(new_code)
                    new_code = new_code.replace("```", "")

                if not new_code:
                    self.logger.warning("Empty new code!!")
                    continue

                is_safe_change = code_change_is_safe(code, new_code, self.config.verus_path, self.logger)
                new_veval = VEval(new_code, self.logger)
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
                        f.write("\n// Safe: " + str(is_safe_change))

                if not is_safe_change:
                    self.logger.warning("The repair is not safe.")
                    continue
                all_failed = False

                if new_score.is_correct():
                    self.logger.info(f"All errors are fixed within {attempt} steps!!!")
                    return new_code
                
                #Test: adding a houridni run after each repair, just in case a correct version actually already exists
                hdn_code = self.hdn.run(new_code)[1]
                hdn_veval = VEval(hdn_code, self.logger)
                hdn_score = hdn_veval.eval_and_get_score()
                if hdn_score.is_correct():
                    self.logger.info("Verus succeeded with hdn!!")
                    return hdn_code

                #TODO: it might be worthy to take Houdini version, but let's see ...
#        elif hdn_score > score:
#            self.logger.info("Houdini code is better")
#            return hdn_code
#        else:
#            self.logger.info("Original code is better")
#            return code


                new_num_cur_failure = len([f for f in new_veval.get_failures() if f.error == cur_failure.error])
                if new_num_cur_failure < num_cur_failure and new_score.is_good_repair(score):
                    code = new_code
                    self.logger.info(f"Step {attempt}: {cur_failure.error} is fixed.")
                    failed_last_time = -1
                    break
                if new_num_cur_failure == num_cur_failure and new_score > score:
                    code = new_code
                    self.logger.info(f"Step {attempt}: {cur_failure.error} is partically fixed.")
                    failed_last_time = max(-1, failed_last_time - 1)
                    break
            failed_last_time += 1
            if all_failed and failed_last_time >= remove_lines_per_failure:
                self.logger.info("All repair attempts failed due to empty results.")
                break
        return code
    

    def run(self, input_file, output_file, func_name=None):
        content = open(input_file).read()
        code = self.run_code(content)

        with open(output_file, "w") as wf:
            wf.write(code)
    
    def run_code(self, code, func_name=None):
        self.logger.info("self debugging...")
#        code, score = self.debug_type_error(code, func_name=func_name)

        from pathlib import Path
        temp_dir = Path("output-intermediate-temp-" + time.strftime("%Y%m%d-%H%M%S"))
        temp_dir.mkdir(parents=True, exist_ok=True)

#        if score > 0:
#           code = self.rag_debug_test(code, func_name=func_name)
        code = self.repair_veval(code, max_attempt = 10, func_name=func_name, temp_dir=temp_dir)

        self.logger.info("finished!")
        return code
