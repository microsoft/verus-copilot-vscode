import * as vscode from 'vscode';
import * as lc from "vscode-languageclient/node.js"
import util from 'node:util'
import crypto from 'node:crypto'

import { getLanguageClient } from '../languageClient.js'

const getSyntaxTreeViaCommand = async (document: vscode.TextDocument) => {
    if (vscode.window.activeTextEditor == null || vscode.window.activeTextEditor.document !== document) {
        await vscode.window.showTextDocument(document).then(() => util.promisify(setTimeout)(50))
    }

    const uri = "verus-analyzer-syntax-tree://syntaxtree/tree.rast"
    const syntaxTreeDocument = await vscode.workspace.openTextDocument(vscode.Uri.parse(uri));
    const res = syntaxTreeDocument.getText()
    return res
}

const syntaxRequest = new lc.RequestType<any, string, void>("verus-analyzer/syntaxTree")
const getSyntaxTreeViaLSP = async (document?: vscode.TextDocument) => {
    const client = getLanguageClient()
    if (document == null) {
        const editor = vscode.window.activeTextEditor
        if (editor == null) {
            throw new Error('Verus Copilot: No active text editor')
        }
        if (editor.document.languageId != 'rust' || editor.document.uri.scheme != 'file' ) {
            throw new Error('Verus Copilot: Active editor is not in rust lanugage')
        }

        document = editor.document
    }
    const res = await client.sendRequest(syntaxRequest, {textDocument: {
        uri : document.uri.toString()
    }})
    return res
}

export type SyntaxTreeNodeInfo = {
    indent: number;
    type: string;
    start: number;
    end: number;
    value: string | undefined;
}
export type SyntaxTreeNode = {
    info: SyntaxTreeNodeInfo;
    parent?: SyntaxTreeNode;
    children: Array<SyntaxTreeNode>
}
const re = /^(\s*)([^@]*)@(\d*)..(\d*)( "(.*)")?$/
const parseSyntaxTree = async (str: string) => {
    let stack: Array<SyntaxTreeNode> = []
    for (const line of str.split('\n')) {
        if (line === '') {
            continue
        }

        const matches = line.match(re)
        if (matches == null) {
            throw new Error('Verus Copilot: Invalid syntax tree')
        }
        const indent = matches[1].length
        const type = matches[2]
        const start = parseInt(matches[3])
        const end = parseInt(matches[4])
        const value = matches[6]

        const info: SyntaxTreeNodeInfo = {indent, type, start, end, value}
        const node: SyntaxTreeNode = {
            info,
            children: []
        }

        if (stack.length === 0) {
            stack.push(node)
        } else {
            while (stack.length > 0) {
                const last = stack[stack.length - 1]
                if (last.info.indent < node.info.indent) {
                    last.children.push(node)
                    node.parent = last
                    stack.push(node)
                    break
                }

                stack.pop()
            }

            if (stack.length === 0) {
                throw new Error('Verus Copilot: Error while building syntax tree')
            }
        }
    }

    const root = stack[0]
    if (root.info.type != 'SOURCE_FILE') {
        throw new Error('Verus Copilot: Invalid syntax tree')
    }

    return root
}

// TODO: LRU cache
let cacheHash: string | null = null
let cacheSyntaxTree: SyntaxTreeNode | null = null

export const getSyntaxTree = async (document: vscode.TextDocument) => {
    const docText = document.getText()
    const docHash = crypto.hash('sha1', docText)
    if (docHash === cacheHash) {
        return cacheSyntaxTree!
    }

    const raw = await getSyntaxTreeViaLSP(document)
    // const raw = await getSyntaxTreeViaCommand(document)
    const syntaxTree = await parseSyntaxTree(raw)

    if (syntaxTree.info.end !== docText.length) {
        // clear cache if syntax tree is invalid
        cacheHash = null
    } else {
        cacheHash = docHash
        cacheSyntaxTree = syntaxTree    
    }
    
    return syntaxTree
}
