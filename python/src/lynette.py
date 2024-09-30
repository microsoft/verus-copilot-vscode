import sys
import os
import subprocess

class Lynette:
    meta_command = ["cargo", "run", "--manifest-path=../utils/lynette/source/Cargo.toml", "--"]
    env = os.environ.copy()
    env["RUSTFLAGS"] = "-Awarnings"

    # Run a command
    # @command: a list of lynette commands arguemnts, e.g. ["compare", "foo.rs", "bar.rs"]
    # @return: a CompletedProcess object(returned by subprocess.run(...))
    def run(self, command):
        command = self.meta_command + command
        return subprocess.run(command, env=self.env, capture_output=True, text=True)

    def code_unimpl(self, file):
        return self.run(["code", "unimpl", file])

    def func_add(self, file1, file2, replace=False, funcs=[]):
        return self.run(["func", "add", file1, file2, "--replace" if replace else ""] +
                        ["--funcs"] + funcs if funcs else [])

    def code_merge(self, file1, file2, merge_mode):
        pass

    def code_merge_all(self, file1, file2):
        return self.run(["code", "merge", "--all", file1, file2])

    def code_merge_invariant(self, file1, file2):
        return self.run(["code", "merge", "--invariants", file1, file2])

    def code_detect_nonlinear(self, file):
        return self.run(["code", "detect-nl", file])

lynette = Lynette()
