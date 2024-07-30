import sys
import os
import subprocess
import re
import time
import difflib
import json
import tempfile
from veval import VEval, VerusErrorType, VerusError, VerusErrorLabel


ERROR_RANGE = [
    "in the code before the first loop",
    "in the first loop",
    "in the second loop",
    "in the third loop",
    "in the fourth loop",
    "in the fifth loop",
    "in the last loop and code after",
]

class AttrDict(dict):
    def __getattr__(self, name):
        return self[name]

def remove_comment(code):
    """
    remove single-line comments in code
    """
    new_code = ""
    for line in code.split("\n"):
        if line.strip().startswith("//"):
            continue
        new_code += line + "\n"
    return new_code

def formalize_error(code, llm):
    system = "You are an experienced formal language programmer. You are very familiar with Verus, which is a tool for verifying the correctness of code written in Rust."

    instruction = "Your mission is convert the structured Verus error message into natural language which is easy to read. Do not change semantic of the error message. Response with the error only, not including any explanation."

    examples = [
        {
            "query": """\
error: invariant not satisfied before loop
  --> ../data/misc/GPT/sum_one_to_n_3.rs:28:13
   |
28 |             forall |k:int| 0 <= k < n ==> a[k] == k + 1,
   |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
==================================================
error: postcondition not satisfied
  --> ../data/misc/GPT/linearsearch_0.rs:15:1
   |
13 |       ret >=0 ==> forall |i: int| 0 <= i < ret as int ==> #[trigger]nums@[i]!= target,
   |       ------------------------------------------------------------------------------- failed this postcondition
14 |       ret < 0 ==> forall |i: int| 0 <= i < nums@.len() as int ==> #[trigger]nums@[i] != target,
15 | / {
16 | |     let mut i = 0;
17 | |     while i < nums.len()
18 | |     invariant
...  |
35 | |     }
36 | | }
   | |_^ at the end of the function body
==================================================
error: loop invariant not satisfied
  --> ../data/misc/GPT/linearsearch_0.rs:17:11
   |
17 |     while i < nums.len()
   |           ^^^^^^^^^^^^^^ at this loop exit
...
23 |         exists |k: int| 0 <= k < i ==> (#[trigger]nums@[k])!= target,
   |         ------------------------------------------------------------ failed this invariant
""",
            "answer": """\
error: invariant not satisfied before loop
invariant in line 28: forall |k:int| 0 <= k < n ==> a[k] == k + 1,
error: postcondition not satisfied
postcondition in line 13: ret >=0 ==> forall |i: int| 0 <= i < ret as int ==> #[trigger]nums@[i]!= target,
not satisfied at: the end of the function body
error: loop invariant not satisfied
invariant in line 23: exists |k: int| 0 <= k < i ==> (#[trigger]nums@[k])!= target,
not satisfied at this loop exit at line 17: while i < nums.len()
"""
        },
        {
            "query": """\
error: assertion failed
  --> ../data/misc/GPT/sum_odd_1.rs:61:17
   |
61 | /                 is_odd(#[trigger]sums@[k] as int) == is_odd(k as int) &&
62 | |                 sums@[k] == spec_sum(arr@.subrange(0, (k + 1) as int))
   | |______________________________________________________________________^ assertion failed
==================================================
error: precondition not satisfied
  --> ../data/misc/GPT/tail_triangle_3.rs:39:13
   |
18 |         i <= j,
   |         ------ failed precondition
...
39 |             triangle_is_monotonic((idx+1) as nat, n as nat);
   |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
==================================================
error[E0308]: mismatched types
  --> ../data/misc/GPT/conditional_average_2.rs:35:22
   |
35 |             (conds_1[i] && conds_2[i] ==> avgs[i] == (vals_1[i] + vals_2[i]) / 2) &&
   |              --------^-
   |              |       |
   |              |       expected `int`, found `usize`
   |              arguments to this method are incorrect
   |
note: method defined here
  --> /home/shuailu/verus/source/pervasive/std_specs/vec.rs:25:13
   |
25 |     spec fn spec_index(&self, i: int) -> T;
   |             ^^^^^^^^^^""",
            "answer": """\
error: assertion failed
assertion in line 61,62: is_odd(#[trigger]sums@[k] as int) == is_odd(k as int) &&
           sums@[k] == spec_sum(arr@.subrange(0, (k + 1) as int))
error: precondition not satisfied
precondition in line 18: i <= j,
not satisfied at line 39: triangle_is_monotonic((idx+1) as nat, n as nat);
error: mismatched types
expected `int`, found `usize` at line 35: (conds_1[i] && conds_2[i] ==> avgs[i] == (vals_1[i] + vals_2[i]) / 2) &&
arugument to this method are incorrect at line 25: spec fn spec_index(&self, i: int) -> T;
"""
        },
        {
            "query": """\
error: precondition not satisfied
  --> a1704856477757.rs:46:24
   |
46 |             sum.set(0, sum[0] + a[i]);
   |                                 ^^^^
   |
  ::: /home/shuailu/verus/source/pervasive/std_specs/vec.rs:53:14
   |
53 |     requires i < vec.view().len(),
   |              -------------------- failed precondition
==================================================
error: possible arithmetic underflow/overflow
  --> a1704856477757.rs:46:15
   |
46 |             sum.set(0, sum[0] + a[i]);
   |                        ^^^^^^^^^^^^^""",
            "answer": """\
error: precondition not satisfied
precondition in other file at line 53: i < vec.view().len(),
not satisfied at line 46: sum.set(0, sum[0] + a[i]);
error: possible arithmetic underflow/overflow 
at line 46: sum.set(0, sum[0] + a[i]);
"""
        },
    ]

    return llm.infer_llm("gpt-35-turbo", instruction, examples, code, system, answer_num=1, max_tokens=1024, temp=0)[0]


def get_nonlinear_lines(code, logger):
    """
    Get all lines that contain nonlinear arithmetic operations
    """
    code_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="veurs_nonlinear_", suffix=".rs")
    code_f.write(code)
    code_f.close()

    verus_nonlinear_cmd = ["cargo", "run", "--manifest-path", os.path.join(os.path.dirname(__file__), "../utils/lynette/source/Cargo.toml"), "--", "code", "detect-nl", code_f.name]

    m = subprocess.run(verus_nonlinear_cmd, capture_output=True, text=True)
    os.unlink(code_f.name)

    if m.returncode == 0:
        try:
            nl_lines = eval(m.stdout)
            output_lines = []
            code_lines = code.splitlines()
            # TODO(@cyy): the first element of the tuple is the type of the expression(currently limited to "invariant" or "assert")
            for _, (st, ed) in nl_lines:
                text = "\n".join(code_lines[st-1:ed])
                if "nonlinear_arith" not in text:
                    # Only return the lines unlabelled with nonlinear_arith
                    output_lines.append((st, ed, text))
            return output_lines
        except json.JSONDecodeError as e:
            logger.error(f"Error in decoding nonlinear arithmetic operations: {m.stdout}")
            return []
    else:
        return []

def code_change_is_safe(origin, changed, verus_path, logger, target_mode = True, util_path = "../utils"):
    orig_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="llm4v_orig", suffix=".rs")
    orig_f.write(origin)
    orig_f.close()

    changed_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="llm4v_changed", suffix=".rs")
    changed_f.write(changed)
    changed_f.close()

    cargopath = util_path + "/lynette/source/Cargo.toml"

    verus_compare_cmd = ["cargo", "run", "--manifest-path", cargopath, "--",
                        "compare"] + (["-t"] if target_mode else []) + [orig_f.name, changed_f.name]

    m = subprocess.run(verus_compare_cmd, capture_output=True, text=True)
    os.unlink(orig_f.name)
    os.unlink(changed_f.name)

    if m.returncode == 0:
        return True
    elif m.returncode == 1:
        err_m = m.stdout.strip()
        if err_m == "Files are different":
            return False
        else:
            logger.error(f"Error in comparing code changes: {err_m}")
            return False

def get_func_body(code, fname, util_path=None):
    orig_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="veurs_copilot_", suffix=".rs")
    orig_f.write(code)
    orig_f.close()

    cargopath = util_path + "/lynette/source/Cargo.toml"

    lynette_extract_cmd = ["cargo", "run", "--manifest-path", cargopath, "--",
                            "func", "extract", "-b", orig_f.name, fname]
    m = subprocess.run(lynette_extract_cmd, capture_output=True, text=True)
    os.unlink(orig_f.name)

    if m.returncode == 0:
        return m.stdout.strip()
    return ""

def check_changed_code_v2(origin, changed):
    """
    check if any change is made in non-invariant, non-assert, non require/ensure code blocks, if exists then invalid
    """
    diff = list(difflib.ndiff(origin.splitlines(), changed.splitlines()))
    diff = [x for x in diff if not x.startswith("?") and x[1:].strip()]
    safe_lines = []
    # invariant
    safe = False
    use_parentheses = False
    for i, d in enumerate(diff):
        if not safe:
            if (d[1:].strip().startswith("invariant")):
                safe = True
                indent = len(d[1:]) - len(d[1:].lstrip())
                next_indent = len(diff[i+1][1:]) - len(diff[i+1][1:].lstrip())
                if next_indent <= indent:
                    use_parentheses = True
        else:
            new_indent = len(d[1:]) - len(d[1:].lstrip())
            if not use_parentheses and new_indent <= indent:
                safe = False
            if use_parentheses and d[1:].strip() == "{":
                safe = False
        if safe:
            safe_lines.append(i)
    
    # assert
    for i, d in enumerate(diff):
        if d[1:].strip().startswith("assert"):
            safe_lines.append(i)
    
    # require/ensure
    safe = False
    use_parentheses = False
    for i, d in enumerate(diff):
        if safe:
            new_indent = len(d[1:]) - len(d[1:].lstrip())
            if not use_parentheses and new_indent <= indent:
                safe = False
            if use_parentheses and d[1:].strip() == "{":
                safe = False
        # ensures have same indent with requires
        if not safe:
            if (d[1:].strip().startswith("requires") or d[1:].strip().startswith("ensures")):
                safe = True
                indent = len(d[1:]) - len(d[1:].lstrip())
                next_indent = len(diff[i+1][1:]) - len(diff[i+1][1:].lstrip())
                if next_indent <= indent:
                    use_parentheses = True
        if safe:
            safe_lines.append(i)

    # new functions
    safe = False
    for i, d in enumerate(diff):
        if not safe:
            if (d.startswith("-") or d.startswith("+")) and "fn " in d[1:].strip():
                safe = True
                safe_lines.append(i)
        else:
            safe_lines.append(i)
            if (d.startswith("-") or d.startswith("+")) and d[1:].strip() == "}":
                safe = False
    
    for i, d in enumerate(diff):
        if d.startswith("-") or d.startswith("+"):
            if i not in safe_lines:
                return False
    return True


def check_syntaxerr_inv(code):
    """
    Check if the generated invariants have wrong syntax
    """
    codelines = code.split("\n")
    for i, line in enumerate(codelines):
        sline = line.strip()
        if sline.startswith("invariant"):
            if sline.endswith(";"):
                return True
            elif sline.endswith("["):
                return True
            elif codelines[i+1].strip().startswith("["):
                return True
    return False

def split_code_by_loop(code):
    intervals = [1]
    for i, line in enumerate(code.split("\n")):
        if re.match(r"(while|for)(\(| )", line.strip()) and not line.strip().startswith("for all"):
            intervals.append(i+1)
    intervals.append(len(code.split("\n"))+1)
    return intervals

def split_origin_error_by_interval(error, intervals):
    if len(intervals) <= 3:     # less than two loops
        return [error]
    new_error = [""] * (len(intervals)-1)   # before fist loop (mostly spec), first loop, second loop, ..., last loop and after
    cur_error = ""
    idx = -1
    error_lines = error.split("\n")
    for i,line in enumerate(error_lines):
        if line.startswith("error") and "aborting due to" not in line:
            new_error[idx] += cur_error
            cur_error = line + "\n"
            line_num = int(re.findall(r":(\d+):", error_lines[i+1])[0])
            for i, interval in enumerate(intervals):
                if line_num < interval:
                    idx = i - 1
                    break
        else:
            cur_error += line + "\n"
    new_error[idx] += cur_error
    return new_error

def count_origin_error_by_interval(error, intervals):
    if len(intervals) <= 3:     # less than two loops
        cnt = 0
        for line in error.split("\n"):
            if line.startswith("error") and "aborting due to" not in line:
                cnt += 1
        return [cnt]
    error_cnt = [0] * (len(intervals)-1)   # before fist loop (mostly spec), first loop, second loop, ..., last loop and after
    idx = -1
    error_lines = error.split("\n")
    for i,line in enumerate(error_lines):
        if line.startswith("error") and "aborting due to" not in line:
            line_num = int(re.findall(r":(\d+):", error_lines[i+1])[0])
            for i, interval in enumerate(intervals):
                if line_num < interval:
                    idx = i - 1
                    error_cnt[idx] += 1
                    break
    return error_cnt

def compare_and_choose_by_loop(code1, code2, m1, m2):
    int1 = split_code_by_loop(code1)
    int2 = split_code_by_loop(code2)
    if len(int1) != len(int2):
        return code1
    e1 = count_origin_error_by_interval(m1, int1)
    e2 = count_origin_error_by_interval(m2, int2)
    if len(e1) == 1:
        if e1[0] >= e2[0]:
            return code2
        return code1
    code = ""
    for i, (c1, c2) in enumerate(zip(e1, e2)):
        if c1 >= c2:
            st, ed = int2[i], int2[i+1]
            for line_id in range(st, ed):
                code += code2.split("\n")[line_id-1] + "\n"
        else:
            st, ed = int1[i], int1[i+1]
            for line_id in range(st, ed):
                code += code1.split("\n")[line_id-1] + "\n"
    return code

def merge_outputs(code1, code2, verus_path, max_change=5, st1=0, st2=0, prefer=1):
    """
    code1: original code
    code2: changed code
    st: start line of the code, code before this line will not be changed
    prefer: prefer unchanged code (0) or changed code (1)
    """
    remain_code = "\n".join(code1.split("\n")[:st1]) + "\n"
    code1 = "\n".join(code1.split("\n")[st1:])
    code2 = "\n".join(code2.split("\n")[st2:])
    code1 = code1.replace("\t", "    ")
    code2 = code2.replace("\t", "    ")
    diff = list(difflib.ndiff(code1.splitlines(), code2.splitlines()))
    diff = [x for x in diff if x[2:].strip() and not x[2:].strip().startswith("//")]

    # = means if the line is deleted, the next line must be added, vice versa
    for i, d in enumerate(diff):
        if d.startswith("-"):
            if (i+1 < len(diff) and diff[i+1].startswith("?")) or (i+2 < len(diff) and diff[i+1].startswith("+") and diff[i+2].startswith("?")):
                diff[i] = "=" + diff[i][1:]
    diff = [x for x in diff if not x.startswith("?")]
    
    if len([x for x in diff if x.startswith("-") or x.startswith("+")]) > max_change:
        if prefer == 0:
            return remain_code+code1
        else:
            return remain_code+code2

    all_possible_codes = []
    
    def generate_combinations(code_diff, index=0, current_code=[], change_cnt=0, results=[], must_add=False, cant_add=False):
        if index == len(code_diff):
            results.append(("\n".join(current_code), change_cnt))
            return

        line = code_diff[index]

        if line.startswith('-'):
            generate_combinations(code_diff, index + 1, current_code, change_cnt + 1, results)
            generate_combinations(code_diff, index + 1, current_code + [line[2:]], change_cnt, results)
        elif line.startswith('='):
            generate_combinations(code_diff, index + 1, current_code, change_cnt + 1, results, must_add=True)
            generate_combinations(code_diff, index + 1, current_code + [line[2:]], change_cnt, results, cant_add=True)
        elif line.startswith('+'):
            if cant_add:
                generate_combinations(code_diff, index + 1, current_code, change_cnt, results)
            elif must_add:
                generate_combinations(code_diff, index + 1, current_code + [line[2:]], change_cnt + 1, results)
            else:
                generate_combinations(code_diff, index + 1, current_code, change_cnt, results)
                generate_combinations(code_diff, index + 1, current_code + [line[2:]], change_cnt + 1, results)
        else:
            generate_combinations(code_diff, index + 1, current_code + [line[2:]], change_cnt, results)

    generate_combinations(diff, 0, [], 0, all_possible_codes)

    if prefer == 0:
        all_possible_codes = sorted(all_possible_codes, key=lambda x: x[1])
    else:
        all_possible_codes = sorted(all_possible_codes, key=lambda x: -x[1])

    best_score = (-1, 100)
    for code,_ in all_possible_codes:
        #score, _ = evaluate(remain_code+code, verus_path)
        eval = VEval(remain_code + code)
        eval.eval()
        score = (eval.get_verified(), eval.get_errors())
        if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
            best_score = score
            best_code = remain_code+code
    return best_code


def evaluate(code, verus_path, func_name=None):
    fn = "a" + str(int(time.time()*1000)) + ".rs"
    with open(fn, "w") as f:
        f.write(code)
    commands = [verus_path, fn]
    if func_name:
        commands += ["--verify-function", func_name, "--verify-root"]
    m = subprocess.run(commands, capture_output=True, text=True)
    temp = 0
    chunks = m.stderr.split("\n\n")
    for ch in chunks:
        if ch.startswith("error") and "aborting due to" not in ch:
            temp += 1
    try:
        score = re.findall(r"(\d+) verified, (\d+) errors", m.stdout)[0]
    except IndexError as e:
        score = (0, max(1, temp))
    if score[0] == '0' and score[1] == '0':
        score = (0, temp)
    score = (int(score[0]), max(int(score[1]), temp))
    os.remove(fn)
    return score, m

def proved_by_verus (code, verus_path):
    #TODO: is this correct?
    score, msg = evaluate(code, verus_path)
    if score[1] == 0:
        print("Verus succeeded!!")
        return True
    else:
        return False

def error_process(error, llm):
    chunks = error.split("\n\n")
    new_error = ""
    endline = "\n"
    for ch in chunks:
        if ch.startswith("error") and "aborting due to" not in ch:
            new_error += ch + "\n" + "="*50 + "\n"
        elif ch.startswith("verification results"):
            endline += ch
    
    new_error = formalize_error(new_error, llm)
    new_error += endline
    return new_error

def choose_best(codes, verus_path):
    best_score = (-1, 100)
    for code in codes:
        score, _ = evaluate(code, verus_path)
        if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
            best_score = score
            best_code = code
    return best_code


def compress_nl_assertion(code):
    lines = code.split("\n")
    inside = False
    tmp_line = ""
    new_code = ""
    for line in lines:
        if not inside:
            if line.strip().startswith("assert") and "by" in line and "nonlinear_arith" in line:
                inside = True
                tmp_line += line
            else:
                new_code += line + "\n"
        else:
            if "{}" in line:
                tmp_line += " " + line.strip() + "\n"
                inside = False
                new_code += tmp_line
                tmp_line = ""
            else:
                tmp_line += " " + line.strip()
    return new_code



#get detailed information about one arithmetic over/underflow error from input
def get_aritherror(error):
    errorlines = error.split("\n")

    linenum = -1
    linestr = ""
    lineexp = ""

    for i, eline in enumerate(errorlines):
        if "possible arithmetic" in eline:
            #to refine errorlines[i+3] based on ^s in errorlines[i+4]
            targetline = errorlines[i+3]
            referline = errorlines[i+4]
            j = targetline.find('|')
            if j < 0:
                print("Fatal error: did not find | in the arithmetic overflow error line:")
                print(targetline)
                exit()

            linenum = targetline.split('|')[0].rstrip()
            linestr = targetline[j+1:].strip()

            j +=1
            mylist = []
            while j < len(referline) and j < len(targetline):
                if referline[j] == '^':
                    mylist.append(targetline[j])
                j += 1

            lineexp = ''.join(mylist)
            break

    return linenum, linestr, lineexp

def is_preconderr_only (error):
    errorlines = error.split("\n")
    total_err = 0
    total_perr = 0
    other_err = 0
    
    for i, line in enumerate(errorlines):
        if "error: aborting due to previous error" in line:
            continue
        elif "error: precondition not satisfied" in line:
            total_perr += 1
        elif "error: " in line:
            other_err += 1
        elif "verification results::" in line:
            total_err = int(line.split(",")[1].lstrip().split(" ")[0])

    print ("There are {} pre-condition errors among {} total errors.".format(total_perr, total_err))

    if total_perr == total_err:
        return True
    elif other_err == 0:
        return True
    else:
        return False
    
##Utility functions for inter-procedural inference

def split_code_by_func(code, oprefix, tofile=False):
    intervalstart=[]
    intervalend=[]
    names=[]
    ofiles=[]
    totalline = len(code.split("\n"))
    findex = 0
    for i, line in enumerate(code.split("\n")):
        if line.strip().startswith("fn ") or line.strip().startswith("pub fn "):
            #getting this function's code
            fcode = line
            #get starting line number
            intervalstart.append(i)

            #get function name
            tmp = re.sub(r'\(.+','', line)
            name = re.sub(r'.+fn ','',tmp)
            names.append(name)

            #get function ending line number
            ident = len(line) - len(line.lstrip())
            j = i + 1
            foundend = False
            while j < totalline: 
                jline = code.split("\n")[j]
                fcode = fcode + "\n" + jline
                jident = len(jline) - len(jline.lstrip())
                if jident == ident and jline.strip().startswith("}"):
                    intervalend.append(j)
                    foundend = True
                    break
                j = j + 1
            if foundend == False:
                print("Warning: did not find a matching end of function"+name)
                intervalend.append(totalline)
            if tofile == True:
                output_file = oprefix + "_{}_".format(findex) + name + "_.rs"                
                ofiles.append(output_file)
                with open(output_file, "w") as wf:
                    wf.write(fcode)
            findex += 1
    return intervalstart, intervalend, ofiles

def get_indentstr(indent):
    i = 0
    istr = ""
    while i < indent:
        istr += " "
        i += 1
    return istr

def highlight_code_by_func(code, oprefix, tofile=False):
    intervalstart=[]
    intervalend=[]
    names=[]
    ofiles=[]
    code = code.replace("\t", "    ")
    totalline = len(code.split("\n"))
    findex = 0

    for i, line in enumerate(code.split("\n")):
        if line.strip().startswith("fn ") or line.strip().startswith("pub fn "):
            #getting this function's code
            fcode = line
            #get starting line number
            intervalstart.append(i)

            #get function name
            tmp = re.sub(r'\(.+','', line)
            name = re.sub(r'.+fn ','',tmp)
            names.append(name)

            #get function ending line number
            ident = len(line) - len(line.lstrip())
            j = i + 1
            foundend = False
            while j < totalline: 
                jline = code.split("\n")[j]
                fcode = fcode + "\n" + jline
                jident = len(jline) - len(jline.lstrip())
                if jident == ident and jline.strip().startswith("}"):
                    intervalend.append(j)
                    foundend = True
                    break
                j = j + 1
            if foundend == False:
                print("Warning: did not find a matching end of function"+name)
                intervalend.append(totalline)
            findex += 1


    for i, fname in enumerate(names):
        #generate the highlighted file just for function fname
        print("Generating a file highlighting function " + fname + " (L{} --- L{})".format(intervalstart[i]+1, intervalend[i]+1))

        newcode =""
        mystart = intervalstart[i]
        myend = intervalend[i]
        currentident = -1
        insidef = False
        unimplemented = False
        currentfunc = ""

        for k, oldline in enumerate(code.split("\n")):

            if oldline.strip().startswith("fn ") or oldline.strip().startswith("pub fn "):
                if(insidef == True):
                    print("Fatal error: did not find the finish bracket for function " + currentfunc)
                tmp = re.sub(r'\(.+','', oldline)
                tmpname = re.sub(r'.+fn ','',tmp)
                currentfunc = tmpname

            if k<= myend and k >= mystart:
                #in the function to be highlighted
            #    print("...L{} in highlighted function ...".format(k))
                newcode += "\n" + oldline
            elif oldline.strip().startswith("fn ") or oldline.strip().startswith("pub fn "):
                #entering a function that is not to be highlighted
#                print("...in a non-highlighted function " + tmpname + "...")
                currentident = len(oldline) - len(oldline.lstrip())
#                print(".....indentation {}".format(currentident))
                newcode += "\n" + get_indentstr(currentident) + "#[verifier::external_body]"
                newcode += "\n" + oldline
                insidef = True
                if re.search(r"{", oldline):
#                    print("found { in the same line as function name for " + currentfunc)
                    unimplemented = True
                    newcode += "\n" + get_indentstr(currentident+4) + "unimplemented!()"
            elif insidef == True:
                myindent = len(oldline) - len(oldline.lstrip())
                if (currentident == myindent) and oldline.lstrip().startswith("{"):  
                    newcode += "\n" + oldline
                    unimplemented = True
                    newcode += "\n" + get_indentstr(currentident+4) + "unimplemented!()"
#                    print("found { in different line from f name for " + currentfunc)
                elif unimplemented == False:
#                    print("in function head block waiting for bracket with indent {}".format(currentident))
#                    print("indent {}".format(myindent) + "..." + oldline)
                    newcode += "\n" + oldline
                elif (currentident == myindent) and oldline.lstrip().startswith("}"):
#                    print("found } for " + currentfunc)
                    newcode += "\n" + oldline
                    insidef = False
                    if (unimplemented == False):
                        print("Fatal error: did not find starting bracket for function: " + currentfunc)
                    unimplemented = False
            else:
                newcode += "\n" + oldline

        if tofile == True:
            output_file = oprefix + "_{}_".format(i) + fname + "_.rs"                
            ofiles.append(output_file)
            with open(output_file, "w") as wf:
                wf.write(newcode)
            print("... into file " + output_file)

    return ofiles, names

def merge_with_highlight(codeA, codeB, hfunc):
    #merge codeB's hfunc into codeA, keep everything else unchanged


    codeA = codeA.replace("\t", "    ")
    codeB = codeB.replace("\t", "    ")
    
    #get codeB's hfunc into hfcode
    hstart, hend = get_fun_range(codeB, hfunc)
    bi = hstart
    hfcode = ""
    while bi <= hend:
        hfcode += codeB.split("\n")[bi] 
        hfcode += "\n"
        bi += 1

    #replace hfunc's implementation in codeA with hfcode
    hstartA, hendA = get_fun_range(codeA, hfunc)

    if hstartA >= hendA :
        print("Fatal Error")

    ai= 0
    merged = ""
    codeAlines = codeA.split("\n")
    codeBlines = codeB.split("\n")

    #just in case ...
    if codeAlines[hstartA-1].strip() == "#[verifier::external_body]" and not codeBlines[hstart-1].strip() == "#[verifier::external_body]": 
        print("[Warning] A verifier external body " + hfunc + " will become non external body")
        hstartA = hstartA - 1

    while ai < len(codeAlines):
        if ai == hstartA :
            merged += hfcode
        elif ai <= hstartA or ai > hendA :
            merged += codeAlines[ai]
            merged += "\n"
        ai += 1
    return merged

#merge hfunc and any function's new post-condition in codeB into codeA
#return merged code and line numbers (in returned code) of those added post conditions
def merge_with_highlight_post(codeA, codeB, hfunc):
    codeA = codeA.replace("\t", "    ")
    codeB = codeB.replace("\t", "    ")
    merge1 = merge_with_highlight(codeA, codeB, hfunc)
    diff = list(difflib.ndiff(merge1.splitlines(), codeB.splitlines()))
#   print("Here are the changed pre/post conditions of non-highlight functions:")
#    print("\n".join(diff))
    newdiff = []
    newpostlines = []
    inensure = False
    infunchead = False
    findent = 0
    newi =0
    for i, x in enumerate(diff):
        myindent = len(x[2:]) - len(x[2:].lstrip())
        if x.find(" fn ") != -1:
            findent = myindent
            infunchead = True
            if x.endswith("{"):
                 infunchead = False
                 inensure = False
        elif x.find("{")!=-1 and myindent == findent:
            inensure = False
            infunchead = False
        elif x.find("ensures")!=-1 and infunchead:
            inensure = True

        if x.startswith("?"): 
            continue
        elif x.startswith("-"):
            #I would keep every line of code in the old version
            newdiff.append(x)
        elif x.startswith("+"): 
            #Only take the new post condition
            if inensure:
                newpostlines.append(newi)
                newdiff.append(x)
            else:
                continue
        else:
            newdiff.append(x)

        newi +=1

    return "\n".join([x[2:] for x in newdiff]), newpostlines

def get_fun_range_inner(code, hfunc):

    totalline = len(code.split("\n"))

    inhf = False
    foundend = False
    startl = -1
    endl = -1

    for i, line in enumerate(code.split("\n")):
        if line.strip().startswith("fn ") or line.strip().startswith("pub fn "):
            #getting this function's code
            fcode = line

            #get function name
            tmp = re.sub(r'\(.+','', line)
            nametmp = re.sub(r'.+fn ','',tmp)
            name = re.sub(r'fn ','', nametmp)
            #print("find function "+name + " while looking for function " + hfunc)

            if name == hfunc:
               startl = i 
               #print(hfunc + "starts at L {}".format(startl+1)) 
               ident = len(line) - len (line.lstrip())
               inhf = True

        elif inhf == True:
            dent = len(line) - len(line.lstrip())
            if dent == ident and line.strip().startswitch("{"):
                startl = i

            if dent == ident and line.strip().startswith("}"):
                endl = i
                foundend = True
                #print(hfunc + "ends at L {}".format(endl+1)) 
                break

    if foundend == False or inhf == False:
         print("Warning: did not find (a matching end of) function "+hfunc)

    return startl, endl


def get_fun_range(code, hfunc):

    totalline = len(code.split("\n"))

    inhf = False
    foundend = False
    startl = -1
    endl = -1

    for i, line in enumerate(code.split("\n")):
        if line.strip().startswith("fn ") or line.strip().startswith("pub fn "):
            #getting this function's code
            fcode = line

            #get function name
            tmp = re.sub(r'\(.+','', line)
            nametmp = re.sub(r'.+fn ','',tmp)
            name = re.sub(r'fn ','', nametmp)
            #print("find function "+name + " while looking for function " + hfunc)

            if name == hfunc:
               startl = i 
               #print(hfunc + "starts at L {}".format(startl+1)) 
               ident = len(line) - len (line.lstrip())
               inhf = True

        elif inhf == True:
            dent = len(line) - len(line.lstrip())
            #print(dent)
            if dent == ident and line.strip().startswith("}"):
                endl = i
                foundend = True
                #print(hfunc + "ends at L {}".format(endl+1)) 
                break

    if foundend == False or inhf == False:
         print("Warning: did not find (a matching end of) function "+hfunc)

    return startl, endl

def get_func_names(code):
    names = []
    for i, line in enumerate(code.split("\n")):
        if line.strip().startswith("fn ") or line.strip().startswith("pub fn "):
            #get function name
            tmp = re.sub(r'\(.+','', line)
            name = re.sub(r'.+fn ','',tmp)
            names.append(name)
            print("L{}: ".format(i+1) + name )
    return names

def remove_redundant_loopinv(code):
    """
    remove redundant loop invariants in code
    """
    new_code = ""
    invariants = False
    invariantlist = []
    for line in code.split("\n"):
        remove = False
        if invariants:
            if line.strip().startswith("{"):
                invariants = False
            else:
                thisinv = re.sub(r'//.*','', line).strip()
                for inv in invariantlist:
                    if thisinv == inv:
                        remove = True
                if not remove:
                    invariantlist.append(thisinv)
        else:
            if line.strip().startswith("invariant"):
                invariantlist = []
                invariants = True
        if not remove:
            new_code += line + "\n"
    return new_code

def remove_redundant_req(code, fname, verus_path):
    """
    remove redundant pre-conditions of function fname
    """

    if not proved_by_verus (code, verus_path):
        print("[remove_redundant_req] Error: this input code is not proved yet")
        return code
     
    new_code = ""
    requires = False
    infunction = False
    done = False
    invariantlist = []
    codelines = code.split("\n")
    totlines = len(codelines)
    for i, line in enumerate(codelines):
        remove = False

        if done:
            new_code += line + "\n"
            continue

        if requires:
            if "{" in line or "ensures" in line:
                #not all { means the end of requires, but I don't handle more complicated cases now
                done = True
            else:
                #Let's try remove this line and see if it still works
                j = i + 1
                tmp = new_code
                while j < totlines:
                    tmp += codelines[j] + "\n"
                    j = j + 1
                if proved_by_verus (tmp, verus_path):
                    print("[remove_redundant_req] Found a redundant require line:")
                    print(line)
                    remove = True

        elif infunction:
            if line.strip().startswith("requires"):
                requires = True
        else:
            #look for target function
            if "fn" in line and fname in line:
                infunction = True

        if not remove:
            new_code += line + "\n"
    return new_code


#extract information about pre-condition violation errors
#TODO: if error involves caller or callee not in code file, it will break
def process_precondition_error(error, code):

    err_callnnum=[]
    err_call=[]
    err_prefun=[]
    err_precond=[]

    codelines = code.split("\n")
    errlines = error.split("\n")
    for i, line in enumerate(errlines):
        if line == "error: precondition not satisfied":
            #this is either the invocation line or precondition line
            if "precondition" in errlines[i+4]:
                preline = errlines[i+3]
                callline = errlines[i+6]
                vline = errlines[i+7]
            else:
                preline = errlines[i+6]
                callline = errlines[i+3]
                vline = errlines[i+4]

            j = callline.find('|')
            if j < 0:
                print("Fatal error: did not find | in the precondition error line:")
                print(callline)
                exit()
            err_callnnum.append(callline.split('|')[0].strip())
            tmpcall = callline[j+1:].strip()
            #This is the line where callee's precondition is not satisfied
            err_call.append(tmpcall)
            #Now, we want to get the callee's name
            j = vline.find('^')
            tmpcall = callline[j:]
            err_fname=tmpcall.split('(')[0].strip()
            #if the call is obj.f, we want to just get f
            if err_fname.find('.') >= 0:
                err_fname = err_fname.split('.')[1]

            j = preline.find('|')
            if j < 0:
                print("Fatal error: did not find | in the precondition error line:")
                print(preline)
                exit()
            err_precond.append(preline[j+1:].strip())
            err_prefuncln = preline.split('|')[0].strip()

            err_prefunlist=[]
            codeindex=int(err_prefuncln)-1
            codeindexend=0
            while codeindex >=0:
                if "requires" in codelines[codeindex]:
                    codeindexend = codeindex
                if err_fname in codelines[codeindex] and "fn" in codelines[codeindex]:
                    break
                codeindex = codeindex-1
            if codeindexend == 0:
                print("Error: did not find key word `requies'")
                codeindexend = int(err_prefuncln)

            while codeindex < codeindexend:
                err_prefunlist.append(codelines[codeindex].strip())
                codeindex = codeindex+1
            err_prefun.append(" ".join(err_prefunlist))

    return err_callnnum, err_call, err_prefun, err_precond


def same_code_verus (code1, code2, verus_path):
    """
    Check if two code snippets return the same Verus err results
    """
    _, msg1 = evaluate(code1, verus_path)
    _, msg2 = evaluate(code2, verus_path)
    err1 = msg1.stderr + msg1.stdout
    err2 = msg2.stderr + msg2.stdout
    return err1 == err2


def remove_unnecessary_assert(code):
    """
    Any assert whose existence does not affect Verus proof result will be removed
    """
    #TO Be Implemented
    return


def load_jsonl(filename):
    with open(filename, "r") as f:
        return [json.loads(line) for line in f]

def dump_jsonl(data, filename):
    with open(filename, "w") as f:
        for line in data:
            json.dump(line, f)
            f.write("\n")


def get_unexpected_error(code, verus_path, expects):
    _, msg = evaluate(code, verus_path)
    chunks = msg.stderr.split("\n\n")
    error = ""
    for ch in chunks:
        add = False
        for x in ch.split("\n"):
            if not add and x.startswith("error"):
                for ex in expects:
                    if ex in x:
                        break
                else:
                    add = True
            if add:
                error += x + "\n"
        # error_line = [x for x in ch.split("\n") if x.startswith("error")]
        # if not error_line:
        #     continue
        # error_line = error_line[0]
        # for ex in expects:
        #     if ex in error_line:
        #         break
        # else:
        #     error += ch + "\n\n"
    return error
 

def fix_one_type_error(oldline, cstart, cend, newtype):
    #cstart: the starting index of the problematic expression
    #cend: the ending index of the problematic expression

    prefix = oldline[:cstart]
    mid = oldline[cstart:cend+1]
    suffix = oldline[cend+1:]

    oldtype_pos = mid.rfind(" as ")

    if oldtype_pos > -1:
        if " " in mid[oldtype_pos+4:].strip():
            #there was not a cast type for the whole expression
            #instead it is something like x as int - 1
            oldtype_pos = -1

    if oldtype_pos == -1:
        #the old expression does not have "as oldtype"
        if re.match(r"^\(*\)$", mid.strip()):
            #already in parentheses
            newmid = mid + " as " + newtype
        #####some times code is written like j-1 and hence needs ()
        #elif mid.strip().find(" ") == -1:
            #mid is one variable, no need for parentheses
        #    newmid = mid + " as " + newtype
        else:
            newmid = "( " + mid + " ) as " + newtype
    else:
        #replace the old as type
        newmid = mid[:oldtype_pos] + " as " + newtype

    return prefix+newmid+suffix

#This function is deprecated, no longer maintained
def fix_one_type_error_in_code(code, linenum, cstart, cend, newtype, badexpr, verbose=True):
    #note that linenum, cstart, cend indices all start from 0

    newlines = []
    for i, line in enumerate(code.split("\n")):
        if i != linenum:
            newlines.append(line)
        else:
            if not badexpr in line:
                print("Fatal error: `" + badexpr + "' does not exist in " + line)
                exit()
            if badexpr != line[cstart:cend+1]:
                print("Fatal error. Expected expression is `" + badexpr + "'; Get expression `" + line[cstart:cend+1])

            newline = fix_one_type_error(line, cstart, cend, newtype)

            if verbose == True:
                print("[fix_one_type_error_in_code] changed the type of `" 
                      + line[cstart:cend+1] + "'"
                        + "as `" + newline.strip() + "'")
            newlines.append(newline)

    return "\n".join(newlines) + "\n"

#this function uses veval's ErrTrace type, which allows
#the skip of get_typeerror
def fix_one_type_error_in_code(code, err_trace, verbose=True):
    #note that linenum, cstart, cend indices all start from 0
    err_label = err_trace.strlabel
    if err_label is None:
        sys.stderr.write("Fatal error: err_trace does not have a label")
        sys.stderr.write(code)
        return code
    newtype = err_label.split('`')[1]

    err_lnum = err_trace.get_lines()[0]
    linenum = err_lnum-1

    line = err_trace.get_text()
    cstart = err_trace.text[0].hl_start - 1
    cend = err_trace.text[0].hl_end - 2
    err_exp = line[cstart:cend+1]

    newlines = []
    for i, line in enumerate(code.split("\n")):
        if i != linenum:
            newlines.append(line)
        else:
            if not err_exp in line:
                sys.stderr.write("Fatal error: `" + err_exp + "' does not exist in " + line)
                exit()
            if err_exp != line[cstart:cend+1]:
                sys.stderr.write("Fatal error. Expected expression is `" + err_exp + "'; Get expression `" + line[cstart:cend+1])

            newline = fix_one_type_error(line, cstart, cend, newtype)

            #Sometimes, we may encounter non-fixable type error
            #for example if one expects ..i or [i] to be int, ..i as int or [i] as int will return the same type error
            #so, we return "" to warn the caller
            #otherwise, the caller may hang
            if line == newline:
                return ""

            if verbose == True:
                sys.stderr.write("[fix_one_type_error_in_code] changed the type of `" 
                      + line[cstart:cend+1] + "'"
                        + "as `" + newline.strip() + "'")
            newlines.append(newline)

    return "\n".join(newlines) + "\n"

#    return fix_one_type_error_in_code(code, err_lnum-1, err_cstart-1, err_cend-2, err_newtype, err_exp)



#get detailed information about one type error from error message
#TODO: this function can be replaced later when json format error is available
#Note: all index number starts from 0
#Return: linenum, col_start, col_end, expected type, linestr
def get_typeerror(error, verbose=True):

    if not "[E0308]" in error:
        print("Fatal error: function get_typeerror is invoked to process non-type error.")
        return None

    errorlines = error.split("\n")

    linenum = -1
    linestr = ""

    for i, eline in enumerate(errorlines):
        if "[E0308]" in eline:
            #to refine errorlines[i+3] based on ^s in errorlines[i+4]
            #the line showing the original program code with type errors
            targetline = errorlines[i+3]
            #the line with - and ^ indicating where the errors are
            referline  = errorlines[i+4]

            j = targetline.find('|')
            if j < 0:
                print("Fatal error: did not find | in the type error line:")
                print(targetline)
                return None

            linenum = targetline.split('|')[0].rstrip()
            linestr = targetline[j+1:].strip()

            #search for the line that explains the type error
            expline_idx = i+4
            while not "expected `" in errorlines[expline_idx]:
                expline_idx += 1
                if expline_idx > i + 10:
                    #I doubt the explanation line will appear so late
                    print("Fatal error: did not find expected type in the type error message about")
                    print(targetline)
                    return None

            #the line that explains what type is expected and what is found instead
            expline = errorlines[expline_idx]
            e = expline.find("expected `")
            newtype = expline[e:].split("`")[1]

            if expline_idx != i+4:
                #explanation is not the same as the reference line
                col_end = e
                while col_end + 1 < len(referline) and referline[e] == referline[col_end+1]:
                    col_end = col_end + 1
                col_start = e
                while col_start > 0 and referline[col_end] == referline[col_start - 1]:
                    col_start = col_start -1
            else:
                #explanation is in the same line as the reference line
                #the line is like: - expected `int` or ^ expected `int`
                col_end = e - 2
                col_start = col_end
                while col_start > 0 and referline[col_end] == referline[col_start - 1] :
                    col_start = col_start -1

            badexpr = targetline[col_start:col_end+1] 

            if verbose:
                print("[get_typeerror] `"+ badexpr
#                    + "' in col {} -- {} "
                      + "` in `" + targetline[j+1:].strip() + "`" 
                      + " of Line {} should has type ".format(col_start - (j+1), col_end - (j+1), linenum)
                    + newtype)
            break

    #Needs to minus j+1, because the error message prepend the code line with line number and '|'
    return int(linenum) - 1, col_start - (j+2), col_end - (j+2), newtype, badexpr

def clean_code(code):
    might_code = re.findall(r"```rust(.*)```|```verus(.*)```", code, flags=re.DOTALL)
    if might_code:
        code = might_code[0][0] if might_code[0][0] else might_code[0][1]
    
    lines = []
    for line in code.split("\n"):
        if line.strip() == "```":
            continue

        #this is ad-hoc, but somehow GPT often generates ```use ... on first line
        if line.startswith("```"):
            line = line[3:]
 
        lines.append(line)
    code = "\n".join(lines)
    return code
