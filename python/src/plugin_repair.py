import sys
import os
import argparse
import logging
import json
from utils import AttrDict
from veval import verus
import openai
import subprocess

def main():
# Parse arguments
    parser = argparse.ArgumentParser(description='Verus Copilot')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--input', default='input.rs', help='Path to input file')
    parser.add_argument('--func', default='', help='the function to fix')
    parser.add_argument('--ftype', default='', help='the type of repair function to call')
    parser.add_argument('--exp', default='', help='the failing expression')
    args = parser.parse_args()

    # Check if config file exists
    if not os.path.isfile(args.config):
        sys.stderr.write('Config file does not exist')
        return

    config = json.load(open(args.config))
    config = AttrDict(config)
    verus.set_verus_path(config.verus_path)

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
        runner.run_simple(args.input, args.func, extract_body = True)
    else:
        from refinement import Refinement
        runner = Refinement(config, logger)
        if args.ftype == "assertfaillemma":
            runner.run(args.input, args.func, args.ftype, extract_body = False, failure_exp = args.exp)
        else:
            runner.run(args.input, args.func, args.ftype, extract_body = True, failure_exp = args.exp)

if __name__ == '__main__':
    main()
