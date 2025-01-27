import sys
import os
import argparse
import logging
import json
import tomli
from utils import AttrDict
from veval import verus, VEval
import openai
import subprocess

def main():
# Parse arguments
    parser = argparse.ArgumentParser(description='Verus Copilot')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--input', default='input.rs', help='Path to target Rust file for proof synthesis')
    parser.add_argument('--main_file', default='', help='Path to the file with main function, empty if same as input')
    parser.add_argument('--toml_file', default='', help='Path to toml file, if available')
    parser.add_argument('--func', default='', help='the target function in input file for proof synthesis')
    parser.add_argument('--ftype', default='', help='the type of repair function to call')
    parser.add_argument('--exp', default='', help='the failing expression')
    args = parser.parse_args()

    #Set up the parameters for Verus 
    if args.toml_file:
        #check if there are extra_args in toml file
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

    logging.getLogger("httpx").setLevel(logging.WARNING)
#    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)


    if not args.main_file or args.main_file == args.input:
        #this is a single-file verification
        mainf = ""
        module = ""
        write_file = ""
    else:
        mainf = args.main_file
        relative_path = os.path.relpath(args.input, os.path.dirname(args.main_file))
        module = relative_path.replace('.rs','').replace('/','::').replace('\\','::')
        #For multi-file project, we need to prepare in-place file-edit for verification
        write_file = args.input
        #have a backup for the file we will do in-place change

        #TODO: do we need the backup below?
        #code = open(args.input).read()
        #try:
        #    open(input_file + ".verus_copilot.bak", "w").write(code)
        #except:
        #    pass

    v_param = [mainf, module, extra_args, write_file]

    logger.info(f"Here are your environment setting:")
    logger.info(f"toml: {args.toml_file}\nmainf: {mainf}\nmodule: {module}\nextra_args: {extra_args}\nwrite_file: {write_file}\n")

    if not args.ftype:
        sys.stderr.write('failure type is not specified')
        return 
 
    if args.ftype == "fungen":
        if not args.func:
            sys.stderr.write('function name is not specified')
            return 

        from generation import Generation
        runner = Generation(config, logger, v_param)
        runner.run_simple(args.input, args.func, extract_body = True)
    else:
        from refinement import Refinement
        runner = Refinement(config, logger, v_param)
        if args.ftype == "assertfaillemma":
            runner.run(args.input, args.func, args.ftype, extract_body = False, failure_exp = args.exp)
        else:
            runner.run(args.input, args.func, args.ftype, extract_body = True, failure_exp = args.exp)

if __name__ == '__main__':
    main()
