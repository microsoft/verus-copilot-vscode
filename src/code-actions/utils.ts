import * as vscode from 'vscode'
import {SyntaxTreeNode} from '../syntaxTree'

// TODO: recursive limit
const _findNodeRecursive = (cur: SyntaxTreeNode, token: string, res: Array<SyntaxTreeNode>) => {
    if (cur.info.type === token) {
        res.push(cur)
    }
    for (const child of cur.children) {
        _findNodeRecursive(child, token, res)
    }
}

export const findNode = (root: SyntaxTreeNode, token: string) => {
    const res: Array<SyntaxTreeNode> = []
    _findNodeRecursive(root, token, res)

    return res
}

export const findParent = (cur: SyntaxTreeNode, token: string): SyntaxTreeNode | null => {
    if (cur.info.type === token) {
        return cur
    }
    if (cur.parent == null) {
        return null
    }
    return findParent(cur.parent, token)
}

export const getRangeFromNode = (document: vscode.TextDocument, node: SyntaxTreeNode) => {
    return new vscode.Range(
        document.positionAt(node.info.start),
        document.positionAt(node.info.end)
    )
}

export const getTextFromNode = (document: vscode.TextDocument, node: SyntaxTreeNode) => {
    return document.getText(
        getRangeFromNode(document, node)
    )
}

export const parseFnNode = (fnNode: SyntaxTreeNode) => {
    if (fnNode.info.type !== 'FN') {
        throw new Error('parseFnNode: invalid type')
    }

    const bodyNode = fnNode.children.find(x => x.info.type == 'BLOCK_EXPR')
    if (bodyNode == null) {
        throw new Error('parseFnNode: invalid body node')
    }
    const nameNode = fnNode.children.find(x => x.info.type == 'NAME')
    if (nameNode == null) {
        throw new Error('parseFnNode: invalid fn name')
    }
    const identNode = nameNode.children.find(x => x.info.type == 'IDENT')
    if (identNode == null) {
        throw new Error('parseFnNode: invalid fn name')
    }
    const fnName = identNode.info.value
    if (fnName == null) {
        throw new Error('parseFnNode: invalid fn name')
    }

    return {
        fnNode,
        bodyNode,
        fnName,
    }
}

export type ActionInfo = {
    actionTitle: string,
    eventRange: vscode.Range,
    replaceRange: vscode.Range,
    fileUri: vscode.Uri,
    ftype: string,
    params: object,
}

export const genCodeAction = (actionInfo: ActionInfo | null, triggerRange: vscode.Range) => {
    if (actionInfo == null) {
        return null
    }
    const {
        actionTitle,
        eventRange,
        replaceRange,
        fileUri,
        params,
        ftype,
    } = actionInfo

    if (!triggerRange.intersection(eventRange)) {
        return null
    }

    const action = new vscode.CodeAction(
        actionTitle,
        vscode.CodeActionKind.QuickFix,
    )
    action.command = {
        title: actionTitle,
        command: 'verus-copilot.exec-code-action',
        arguments: [
            replaceRange,
            fileUri,
            ftype,
            params,
        ],
    }

    return action
}
