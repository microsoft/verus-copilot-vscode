###################
#This utility file is used to extract dependency for veirfying a specific 
#function in a project. The output usually needs some manual tweak to get 
#compiled/verused, but should be sufficient for LLM's proof synthesis. 
#
#This is the procedure of using this utility file
#1. put #[verifier::spinoff_prover] before the target function to verify
#
#2. run Verus with the --log-all command-line option
#verus <--verify-module xx::xx> <main.rs> ... --log-all
#
#There will be a .verus_log directory. There should be a XYZ.vir file 
#   there named with the target-function-name.
#Note that, --verify-function sometimes does not work in a big project. As long
#as the spinoff_prover macro is used, it should be ok.
#
#3. run utils_rustmerger.py
# specify the original src directory (the place where verus was run above) 
# specify the .vir file generaed above
# you will see the output in a folder share the same prefix as the src dir
#       by default, the directory name will add "tmp" as suffix
#
#4. If you want to compile/verus the resulting file, some adjustment is needed
# * create a place holder main.rs to `use' all the modules
# * class header maybe missing for class methods
# * some trait declaration may be missing
# * adjust the use crate clauses
# * occasionally, the ending parentheses of ensures may be missing
# * there are probably other things that I forgot ...
#
#####################

import os
import re
import argparse
import logging
import json
import sys
from utils import AttrDict
from pathlib import Path
from datetime import datetime


in_dir = ""
out_dir = ""
trait_dict = {}

def main():
    # Parse arguments.
    parser = argparse.ArgumentParser(description='Verus Proof Cleaner')
    parser.add_argument('--inputdir', default='', help='Path to input (src) directory')
    parser.add_argument('--input', default='input.vir', help='Path to input verus log file (.vir)')
    parser.add_argument('--output', default='tmp', help='Suffix to output directory (default:tmp)')
    parser.add_argument('--outputAll', default='', help='A output that combines all files to output')
    args = parser.parse_args()

    get_all_relevant_code(args.inputdir, outputpre = args.output, inputvir = args.input, outputAll=args.outputAll)

    return

    
def get_all_relevant_code(inputdir, outputpre="tmp", inputvir="input.vir", outputAll="", excludefile=""):

    if not os.path.isdir(inputdir):
        sys.stderr.write(f"Input src directory {inputdir} is invalid\n")
        return

    if not os.path.isfile(inputvir):
        sys.stderr.write(f"Input vir file {inputvir} is invalid\n")
        return

    global in_dir
    in_dir = inputdir
    #print(f"Input directory is at {in_dir}")

    # Create an output directory
    global out_dir

    if outputpre:
        out_dir = os.path.join(in_dir, outputpre + datetime.now().strftime("%H-%M-%S"))
        os.mkdir(out_dir)
    else:
        out_dir = ""

    keeplist = get_keeplist(inputvir)

    allOutputStr = ""

    module_dict={}
    for key in keeplist:
        if "\\" in key:
            #TODO: this part is very heuristic
            mod = key.split("\\")[-2]
            smod = key.split("\\")[-1]
            if not mod in module_dict:
                module_dict[mod]=[smod.split(".")[0]]
            else:
                module_dict[mod].append(smod.split(".")[0])

    for file, rans in keeplist.items():
        if not file == excludefile:
            allOutputStr +=extract_a_file(file, rans, module_dict)
        allOutputStr += "\n"

    #TODO
    #This part may not work well as we are guessing mod

    if out_dir:
        for mod, smods in module_dict.items():
        #create mod.rs files
        #pub mod xx;
        #to be put under args.output\<mod>

            content = "\n".join([f"pub mod {smod};" for smod in smods])
        #write down the file
            if os.path.isdir(os.path.join(out_dir, mod)):
                dPath = out_dir + "\\" + mod + "\\mod.rs"
            else:
                dPath = os.path.join(out_dir, "mod.rs")
        #print(f"Create a new file @ {dPath}")
        #print(f"... content is:\n" + content)
            of = open(dPath, "w") 
            of.write(content)
            of.close()

    allextract = "\n".join([line for line in allOutputStr.split("\n") if not line.startswith("use")])

    if outputAll:
        of = open(outputAll, "w")
        of.write(allextract)
        of.close()
        #print(f"All content is written to {outputAll}")

    return allextract


def get_keeplist(vir, my_dict={}):
    vir_content = open(vir).read().split("\n\n")

    for flog in vir_content:
        tuples = process_a_vir_block(flog)
        for t in tuples:
            name = t[0]
            ty = t[1]
            path = t[2]

            path = path.replace("\\.\\","\\")
            if path.startswith("."):
                path = path.replace(".\\","", 1)

            s = t[3]
            e = t[4]
            if not path in my_dict:
                my_dict[path] = [(s, e, ty)]
            elif my_dict[path][-1][0] < s:
                my_dict[path].append((s, e, ty))
            elif my_dict[path][-1][0] == s:
                continue
            else:
                #insert this new range in order
                for ind, l in enumerate(my_dict[path]):
                    if l[0] < s:
                        continue
                    elif l[0] == s:
                        ind = -1
                        break
                    else:
                        break
                if ind > -1:
                    my_dict[path].insert(ind, (s, e, ty))
    return my_dict

def process_a_vir_block(block):
    Name = ""
    Type = ""
    Path = ""
    Ran = (0, 0)


    if block.startswith("(trait_impl"):
        file, trait = process_trait_line(block)
        if not file:
            return []
        if not file in trait_dict:
            trait_dict[file] = [trait]
            #an array is returned
            return locate_trait_impl(file, trait)
        else:
            for t in trait_dict[file]:
                if trait == t:
                    return []
            trait_dict[file].append(trait)
            return locate_trait_impl(file, trait)

    firstline = block.split("\n")[0]
    locStrs = re.findall(r'"(.*?\(#.*?\))"', block)
    if len(locStrs) == 0:
        return []

    Path, Start, End = process_loc_str(locStrs[0])
    #Filtering
    if "vstd" in Path or "no location" in Path:
        return []

    #A Datatype Block
    if '" (Datatype :path ' in firstline:
        Type = "D"
        Name = re.findall('Datatype :path ".*?"', firstline)[0]
        Name = re.findall(r'"(.*?)"', Name)[0]
        return [(Name, Type, Path, Start, End)]
        
    #Unknown typed block
    if not firstline.endswith("Function"):
        return []

    #A Function block
    Name = re.findall('Fun :path ".*?"', block)[0]
    Name = re.findall(r'"(.*?)"', Name)[0]

    mode = re.findall(r':mode .*?:', block)[0]
    if "Spec" in mode:
        Type = "S" #Spec
    else:
        Type = "F" #exec/proof
 
    if ":body None" in block:
        #TODO should spec func nobody treated the same as exec and proof?
        #   strictly speaking nobody spec func just needs to add `;' after the head
        #if not Type == "S":
        Type = "H" #exec/proof function header
        #Identify the last line processed by Verus
        _, _, End = process_loc_str(locStrs[-1])
    else:
        BodyPath = re.findall(r'body \(@@ ".*?"',block)[0]
        BodyPath = re.findall(r'"(.*?)"', BodyPath)[0]
        _, _, End = process_loc_str(BodyPath)
    
    return [(Name, Type, Path, Start, End)]


def locate_trait_impl(file, trait):
    if not os.path.isfile(in_dir + "\\" + file):
        print(f"Warning: File {file} does not exist in directory {in_dir}")
        return []
 
    code = open(in_dir + "\\" + file).read()

    result = []

    linenum = 0
    funindent = -1

    Name = trait
    Path = file
    Type = "T"
    Start = 0
    End = 0

    for line in code.split("\n"):
        linenum += 1

        #in the middle of an impl function
        if funindent > -1:
            if not line.strip() == "}":
                #in the middle of an impl function
                continue
            elif (len(line) - len(line.lstrip())) == funindent:
                result.append((Name, Type, Path, Start, linenum))
                funindent = -1
                continue
            else:
                #in the middle of an impl function
                continue

        #not in the middle of an impl function
        if not line.strip().startswith("impl"):
            continue

        #This is a trait implementation, let's check if the type matches
        sline = re.sub("<.*?>", "", line)

        if not trait == sline.split()[1]:
            continue

        #Yes. This is an impl of the trait we want
        if "{" in line and "}" in line:
            result.append((Name, Type, Path, linenum, linenum)); 
        else:
            funindent = len(line) - len(line.lstrip())
            Start = linenum

    return result
    #TODO: should be replaced by a parser based implementation


def process_trait_line(line): 
    #process a trait line like 
    #(trait_impl) "lib!log.layout_v.impl...." "lib!pmem.pmcopy_t.SpecPSized.")
    #We will skip vstd related ones
    #return file, trait-type

    if "vstd" in line or "core" in line or "builtin" in line:
        return "", ""

    content = line.split()

    #something went wrong. A non-traint line is here
    if content[0] != "(trait_impl":
        return "", ""

    #get file path 
    fname = re.search(r'"(.*?)\.impl', content[1])
    fname = fname.group(1)
    if "!" in fname:
        fname = re.sub(".*?!", "", fname)
    fname = "\\".join(fname.split("."))
    if not fname.endswith(".rs"):
        fname = fname + ".rs"

    traittype = content[2].split(".")[-2]

    return fname, traittype


def process_loc_str(loc):
    if not loc:
        return "", 0, 0

    locs = loc.split(":")

    if len(locs) == 1:
        return locs[0], 0, 0
    elif not ":\\" in loc:
        if len(locs) < 4:
            return locs[0], int(locs[1]), int(locs[1])
        else:
            return locs[0], int(locs[1]), int(locs[3])
    else:
        if len(locs) < 5:
            return locs[0]+":"+locs[1], int(locs[2]), int(locs[2])
        else:
            return locs[0]+":"+locs[1], int(locs[2]), int(locs[4])

def need_this_mod (useline, mod_dict={}):
    if "vstd" in useline:
        return True
    if "builtin" in useline:
        return True
    if "traits" in useline:
        return True
    if "deps" in useline:
        return True
    if "std" in useline:
        return True

    if "core" in useline:
        return True

    for mod, smods in mod_dict.items():
        if mod in useline:
            for smod in smods:
                if smod in useline:
                    return True
            #print(f"{useline} will be removed")
            return False


def extract_a_file(file, keepList, mod_dict):
    #print(f"To extract {file}")

    if not os.path.isabs(file):
        sPath = in_dir + "\\" + file
        if not out_dir:
            dPath = out_dir + "\\" + file
        else:
            dPath = ""
    else:
        sPath = file
        if not out_dir:
            dPath = os.path.join(out_dir, os.path.basename(file))
        else:
            dPath = ""

    #print(f"[extract_a_file] from {sPath} to {dPath}")
    #print(f"{len(keepList)} ranges of lines to keep")

    src = open(sPath).read()

    srcLines = src.splitlines()


    #Keep all the dependency TODO
    new_srcLines = [x for x in srcLines if x.startswith("use ") and need_this_mod(x, mod_dict)]

    #Add verus!
    new_srcLines.append("\n")
    if "verus!" in src:
        new_srcLines.append("verus! {\n")


    #Add keeped lines
    for ran in keepList:
        #print(f"Extracting {ran[2]} L{ran[0]}--{ran[1]}")
        if ran[2] == "H" and not srcLines[ran[0]-1].endswith(";"):
            #only proof/spec function header
            #no need for one-line function that ends w ;
            new_srcLines.append("\t#[verifier::external_body]")
        linenum = int(ran[0])
        while linenum < int(ran[1]) + 1:
            new_srcLines.append(srcLines[linenum-1])
            #    srcLines[linenum-1] = srcLines[linenum-1][8:]
            linenum +=1
        if ran[2] == "H" and not new_srcLines[-1].endswith(";"):
            #only proof/spec function header needs this
            #no need for one-line function that ends w ;
            new_srcLines.append("\t{\n\t\tunimplemented!()\n\t}")
        new_srcLines.append("")

    if "verus!" in src:
        new_srcLines.append("}")

    newsrc = "\n".join(new_srcLines)

    #write down the file
    if not dPath:
        os.makedirs(os.path.dirname(dPath), exist_ok=True)
        of = open(dPath, "w") 
        of.write(newsrc)
        of.close()

    return newsrc

if __name__ == '__main__':
    main()
