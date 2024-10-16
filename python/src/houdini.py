import os
from utils import compress_nl_assertion
import tempfile
import subprocess
import sys
from lynette import lynette
from veval import VEval, VerusErrorType, VerusError

class houdini():
    def __init__(self, config):
        self.config = config
        self.verification_path = config.verus_path

    def merge_invariant(self, code1, code2):
        with tempfile.NamedTemporaryFile(mode='w', prefix="merge_inv_orig", suffix=".rs") as f1, \
             tempfile.NamedTemporaryFile(mode='w', prefix="merge_new_inv", suffix=".rs") as f2:
            f1.write(code1)
            f1.flush()
            f2.write(code2)
            f2.flush()

            path1 = f1.name
            path2 = f2.name

            m = lynette.code_merge_invariant(path1, path2)

        if m.returncode == 0:
            return m.stdout
        else:
            raise Exception(f"Error in merging invariants:{m.stderr}")

    #the input is a list of Veval list[VerusError]
    def get_error_line(self, failures: list[VerusError], considerassert=True):
        ret = []
        for f in failures:
            #if we don't want Houdini to remove assert, we skip assert errors
            if considerassert and f.error == VerusErrorType.AssertFail:
                ret.append(f.trace[0].lines[0]) 
            elif f.error == VerusErrorType.InvFailEnd or f.error == VerusErrorType.InvFailFront:
                ret.append(f.trace[0].lines[0])
            else:
                continue
        return ret

    def run(self, code, write_file="", triplet=None, verbose=False):
        code = compress_nl_assertion(code)
        for _ in range(100):
            veval = VEval(code, write_file, triplet)
            veval.eval()
            failures = veval.get_failures()

            if len(failures) == 0:
                break
 
            lines = self.get_error_line(failures)

            if len(lines) == 0:
                # cannot find a correct answer
                break
            code = code.split("\n")
            for line in lines:
                if line == 0:
                    continue
                code[line-1] = "// // //" + code[line-1]
            code = "\n".join([x for x in code if not x.startswith("// // //")])
        return failures, code
