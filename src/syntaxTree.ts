import * as vscode from 'vscode';
import * as lc from "vscode-languageclient/node";
import util from 'node:util'

import { getLanguageClient } from './languageClient';

const getSyntaxTreeViaCommand = async (document: vscode.TextDocument) => {
    if (vscode.window.activeTextEditor == null || vscode.window.activeTextEditor.document != document) {
        await vscode.window.showTextDocument(document).then(() => util.promisify(setTimeout)(50))
    }

    const uri = "rust-analyzer-syntax-tree://syntaxtree/tree.rast"
    const syntaxTreeDocument = await vscode.workspace.openTextDocument(vscode.Uri.parse(uri));
    const res = syntaxTreeDocument.getText()
    return res
}

const syntaxRequest = new lc.RequestType<any, string, void>("rust-analyzer/syntaxTree")
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
let cacheDocument: vscode.TextDocument | null = null
let cacheSyntaxTree: SyntaxTreeNode | null = null

export const registerSyntaxTreeDisposable = (ctx: vscode.ExtensionContext) => {
    ctx.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(e => {
            if (cacheDocument != null && e.document.uri.toString() === cacheDocument.uri.toString()) {
                cacheDocument = null
                cacheSyntaxTree = null
            }
        })
    )
}
export const getSyntaxTree = async (document: vscode.TextDocument) => {
    if (cacheDocument != null && document.uri.toString() === cacheDocument.uri.toString()) {
        return cacheSyntaxTree!
    }

    // const raw = await getSyntaxTreeViaLSP(document)
    const raw = await getSyntaxTreeViaCommand(document)
    const syntaxTree = await parseSyntaxTree(raw)

    cacheDocument = document
    cacheSyntaxTree = syntaxTree
    
    return syntaxTree
}
