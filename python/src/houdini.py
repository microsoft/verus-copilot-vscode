import os
from utils import evaluate, compress_nl_assertion
import difflib
import tempfile
import subprocess
import sys

class houdini():
    def __init__(self, config):
        self.config = config
        self.verification_path = config.verus_path

    def merge_code(self, code1, code2):
        code1 = "\n".join(code1.split("\n"))
        code2 = "\n".join(code2.split("\n"))
        code1 = code1.replace("\t", "    ")
        code2 = code2.replace("\t", "    ")
        diff = list(difflib.ndiff(code1.splitlines(), code2.splitlines()))

        #Replaced the next two lines with much more complicated merge logic to handle `-` lines
        #as in the inter-procedural version code2 may have changed function prototype
     #   diff = [x for x in diff if x[2:].strip() and not x[2:].strip().startswith("//") and not x.startswith("?")]
     #   code = "\n".join([x[2:] for x in diff])

        newdiff = []
        for i, x in enumerate(diff):
            if not  x[2:].strip().startswith("//") and not x.startswith("?") and not x.startswith("-"):
                newdiff.append(x)
            elif x.startswith("-"):
                toappend = True
                if(x[2:].find(" fn ")!= -1):
                #code2 changed function prototype. should replace instead of merge
                #TODO: how do we know we are getting the right function prototype???
                    print("Diff error at function prototype. Adjusted.")
                    toappend = False

                if i + 1 < len(diff):
                    if(diff[i+1].startswith("+") and x[2:].strip() == diff[i+1][2:].strip()):
                    #this - is immediately followed by a + with only white space difference
                    #it is ok to keep both in case of loop invariants, but not ok to keep both for function prototypes
                        print("Diff error at white spaces. Adjusted.")
                        toappend = False

                if toappend == True:
                    newdiff.append(x)
        code = "\n".join([x[2:] for x in newdiff])
        #print("Merged code:" + code)
        return code

    def merge_invariant(self, code1, code2):
        path1 = ""
        path2 = ""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
            f1.write(code1)
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
            f2.write(code2)
            path2 = f2.name

        merge_cmd = ["cargo", "run", "--manifest-path", os.path.join(os.path.dirname(__file__), "../utils/lynette/source/Cargo.toml"), "--",
                     "code", "merge", "--invariant", path1, path2]

        m = subprocess.run(merge_cmd, capture_output=True, text=True)
        os.unlink(path1)
        os.unlink(path2)

        if m.returncode == 0:
            return m.stdout
        else:
            raise Exception(f"Error in merging invariants:{m.stderr}")

    #the considerassert flag is used to specify if Houdini is allowed to remove assert lines
    def get_error_line(self, error, considerassert=True):
        # if 0 verified, 0 errors, return all the error line, because in that case, there exists syntax error
        # else, get invariant not satisfied error line
        lines = error.split("\n")
        ret = []
        if "0 verified, 0 errors" in error:
            for i,line in enumerate(lines):
                if (line.startswith("error:") or line.startswith("error[E")) and "aborting due to" not in line:
                    try:
                        ret.append(int(lines[i+1].split(":")[1]))
                    except Exception as e:
                        print(error)
                        continue
            return ret
        for i,line in enumerate(lines):
            if line.startswith("error:") and ("invariant not satisfied" in line or "automatically infer triggers" in line):
                try:
                    ret.append(int(lines[i+1].split(":")[1]))
                except Exception as e:
                    print("Exception at processing " + line + "!")
                    print(error)
                    continue
            #assertion failed error line needs special handling, as Houdini may not be allowed to remove assert lines
            elif line.startswith("error:") and "assertion failed" in line and considerassert:
                try:
                    ret.append(int(lines[i+1].split(":")[1]))
                except Exception as e:
                    print("Exception at processing " + line + "!")
                    print(error)
                    continue
            #let's try having Houdini to remove all these errors as well. We could revisit this decision later.
            elif line.startswith("error:") and not ("aborting due to" in line 
                                                or "possible arithmetic" in line
                                                or "precondition not satisfied" in line
                                                or "postcondition not satisfied" in line
                                                or "assertion failed" in line): 
                try:
                    ret.append(int(lines[i+3].split("|")[0]))
                except Exception as e:
                    print("Exception at processing " + line + "!")
                    print(error)
                    continue
            else:
                continue

        #print("The error lines returned to Houdini are: {}".format(ret))
        return ret

    def get_ensure_error_line(self, error):
        # if 0 verified, 0 errors, return all the error line, because in that case, there exists syntax error
        # else, get any function post condition that is not satisfied
        print("Error message is:")
        print(error)
        lines = error.split("\n")
        ret = []
        if "0 verified, 0 errors" in error:
            for i,line in enumerate(lines):
                if (line.startswith("error:") or line.startswith("error[E")) and "aborting due to" not in line:
                    try:
                        ret.append(int(lines[i+1].split(":")[1]))
                    except Exception as e:
                        print(error)
                        continue
            return ret
        for i,line in enumerate(lines):
            if line.startswith("error: postcondition not satisfied"): 
                try:
                    ret.append(int(lines[i+3].split("|")[1]))
                except Exception as e:
                    print(error)
                    continue
        print("Houdini get these ensure-related error lines")
        print(ret)
        return ret

    def run(self, code, verbose=False):
        code = compress_nl_assertion(code)
        for _ in range(100):
            score, msg = evaluate(code, self.verification_path)
            if score[1] == 0:
                break
            lines = self.get_error_line(msg.stderr+msg.stdout)
            if len(lines) == 0:
                # cannot find a correct answer
                break
            code = code.split("\n")
            for line in lines:
#                print("to delete [{}]".format(line))
                code[line-1] = "// // //" + code[line-1]
            code = "\n".join([x for x in code if not x.startswith("// // //")])
        return score, code

    #this Houdini run function was developed to be part of the inter-procedural Houdini
    #If Houdini is able to find a correct version, the correct version is returned
    #           and the score is the correct version's verification result
    #Otherwise, the last version of the Houdini changed code is returend, and the corresponding score
    #
    #considerassert: if false, it cannot be removed by houdini 
    #
    #Return: score, code, msg
    def run_interproc(self, code, verbose=False, removPost=False, considerassert=True):
#        code = compress_nl_assertion(code)
#TODO: we do not consider nl for now
        original_code = code

        #Here, we remove all the incorrect invariants or asserts, assuming function pre-condition is correct
        for _ in range(100):
            score, msg = evaluate(code, self.verification_path)
            if "unexpected closing delimiter" in msg.stderr:
                print("Houdini: something is very wrong with your code. Has to abort.")
                exit()

            if score[1] == 0:
                print("Houdini: found a correct version")
                return score, code, msg

            lines = self.get_error_line(msg.stderr+msg.stdout, considerassert)

            if len(lines) == 0:
                print("Houdini: cannot find a correct version ... will try removing post conditions ...")
                # cannot find a correct answer
                break
            code = code.split("\n")
            for line in lines:
                print("Houdini: going to remove error line:" + code [line-1])
                code[line-1] = "// // //" + code[line-1]
            code = "\n".join([x for x in code if not x.startswith("// // //")])

        #Here, we remove function post-conditions that cannot be satisifed (TODO: should this be done later?)
        score, msg = evaluate(code, self.verification_path)

        if score[1] == 0:
            print("Houdini: found a correct version")
            return score, code, msg

        if score[1] > 0 and removPost:
            #we will try removing function post conditions
            lines = self.get_ensure_error_line(msg.stderr + msg.stdout)

            if len(lines) == 0:
                print("Houdini: no function post-conditio violated. Cannot find a correct version")
                return score, code, msg

            for line in lines:
                print("Houdini: going to remove unsatisfied post conditions:")
                print(code[line-1])
                code[line-1] = "// // //" + code[line-1]
            code = "\n".join([x for x in code if not x.startswith("// // //")])

            #another round of intra-proc houdini, just in case moving post-condition left syntax errors and others
            for _ in range(100):
                score, msg = evaluate(code, self.verification_path)
                if "unexpected closing delimiter" in msg.stderr:
                    print("Houdini: something is very wrong with your code. Has to abort.")
                    exit()

                if score[1] == 0:
                    print("Houdini: found a correct version")
                    return score, code, msg

                lines = self.get_error_line(msg.stderr+msg.stdout)

                if len(lines) == 0:
                    print("Houdini: cannot find a correct version")
                    # cannot find a correct answer
                    return score, code, msg

                code = code.split("\n")
                for line in lines:
                    print("Houdini: going to remove error line:")
                    print(code[line-1])
                    code[line-1] = "// // //" + code[line-1]
                code = "\n".join([x for x in code if not x.startswith("// // //")])
            
            score, msg = evaluate(code, self.verification_path)
            if score[1] == 0:
               print("Houdini: found a correct version")
               return score, code, msg

        return score, code, msg

