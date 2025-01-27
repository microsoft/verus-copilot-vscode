import sys
import os
import subprocess
import re
import time
import difflib
import json
import tempfile
from veval import VEval, VerusErrorType, VerusError, VerusErrorLabel
from lynette import lynette


class AttrDict(dict):
    def __getattr__(self, name):
        return self[name]

def code_change_is_safe(origin, changed, verus_path, logger, target_mode = True, util_path = "../utils", inter=False, debug=False):
    if debug:
        logger.warning("Debug mode is on, skip code change checking")
        return True

    orig_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="llm4v_orig", suffix=".rs")
    orig_f.write(origin)
    orig_f.close()

    changed_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="llm4v_changed", suffix=".rs")
    changed_f.write(changed)
    changed_f.close()

    cargopath = util_path + "/lynette/source/Cargo.toml"

    opts = []
    if inter:
        opts = ["--asserts-anno"]
    elif target_mode:
        opts = ["-t"]

    verus_compare_cmd = ["cargo", "run", "--manifest-path", cargopath, "--",
                        "compare"] + opts + [orig_f.name, changed_f.name]

    m = subprocess.run(verus_compare_cmd, capture_output=True, text=True)
    # os.unlink(orig_f.name)
    # os.unlink(changed_f.name)

    if m.returncode == 0:
        return True
    elif m.returncode == 1:
        err_m = m.stdout.strip()
        if err_m == "Files are different":
            return False
        else:
            logger.error(f"Error in comparing code changes")
            return False
    else:
        err_m = m.stderr.strip()
        if "unwrap()" in err_m:
            logger.error(f"Error in comparing code changes")
            return False

    return None

def get_func_body(code, fname, util_path=None):
    orig_f = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="veurs_copilot_", suffix=".rs")
    orig_f.write(code)
    orig_f.close()

    cargopath = util_path + "/lynette/source/Cargo.toml"

    lynette_extract_cmd = ["cargo", "run", "--manifest-path", cargopath, "--",
                            "func", "extract", "-b", "-f", fname, orig_f.name]

    m = subprocess.run(lynette_extract_cmd, capture_output=True, text=True)
    os.unlink(orig_f.name)

    if m.returncode == 0:
        return m.stdout.strip()
    return ""

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

def load_jsonl(filename):
    with open(filename, "r") as f:
        return [json.loads(line) for line in f]

def dump_jsonl(data, filename):
    with open(filename, "w") as f:
        for line in data:
            json.dump(line, f)
            f.write("\n")

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

#this function uses veval's ErrTrace type, which allows
#the skip of get_typeerror
def fix_one_type_error_in_code(code, err_trace, verbose=False):
    #note that linenum, cstart, cend indices all start from 0
    err_label = err_trace.strlabel
    if err_label is None or not "`" in err_label:
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

def clean_code(code):
    might_code = re.findall(r"```rust(.*)```|```verus(.*)```", code, flags=re.DOTALL)
    if might_code:
        code = might_code[0][0] if might_code[0][0] else might_code[0][1]
    

    codeLines = code.split("\n")

    lines = []
    for line in codeLines:
        if line.strip() == "```":
            continue

        #this is ad-hoc, but somehow GPT often generates ```use ... on first line
        if line.startswith("```"):
            line = line[3:]

        if line.startswith("Context:"): 
            sys.stderr.write("Found context code ... Will remove them.\n")
            break

        lines.append(line)
    code = "\n".join(lines)
    return code
