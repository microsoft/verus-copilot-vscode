import * as vscode from 'vscode'
import { findNode, parseFnNode, getRangeFromNode, findParent, genCodeAction, getTextFromNode } from './utils'
import { SyntaxTreeNode } from '../syntaxTree'

export const getFungenActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range) => {
    const res = findNode(root, 'FN').map(fnNode => {
        try {
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] fn: generate proof',
                eventRange: getRangeFromNode(document, fnNode),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'fungen',
                params: {
                    func: fnName
                }
            }
        } catch {
            return null
        }
    }).map(
        actionInfo => genCodeAction(actionInfo, triggerRange)
    ).filter(
        (x): x is vscode.CodeAction => x != null
    )

    if (res.length > 1) {
        return []
    }

    return res
}

export const getPostcondfailActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range) => {
    const res = findNode(
        root,
        'ENSURES_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] ensure: fix postcondition failures',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'postcondfail',
                params: {
                    func: fnName
                }
            }
        } catch {
            return null
        }
    }).map(
        actionInfo => genCodeAction(actionInfo, triggerRange)
    ).filter(
        (x): x is vscode.CodeAction => x != null
    )

    if (res.length > 1) {
        return []
    }

    return res
}


export const getAssertfaillemmaActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range) => {
    const res = findNode(
        root,
        'ASSERT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] assert: add lemmas',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, root),
                fileUri: document.uri,
                ftype: 'assertfaillemma',
                params: {
                    func: fnName
                }
            }
        } catch {
            return null
        }
    }).map(
        actionInfo => genCodeAction(actionInfo, triggerRange)
    ).filter(
        (x): x is vscode.CodeAction => x != null
    )

    if (res.length > 1) {
        return []
    }

    return res
}

export const getInvariantfailActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range) => {
    const res = findNode(
        root,
        'INVARIANT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] invariant: repair failing invariants',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, root),
                fileUri: document.uri,
                ftype: 'invariantfail',
                params: {
                    func: fnName,
                }
            }
        } catch {
            return null
        }
    }).map(
        actionInfo => genCodeAction(actionInfo, triggerRange)
    ).filter(
        (x): x is vscode.CodeAction => x != null
    )

    if (res.length > 1) {
        return []
    }

    return res
}

const _isSiblingComment = (prevNode: SyntaxTreeNode, prevRange: vscode.Range, curNode: SyntaxTreeNode, curRange: vscode.Range): boolean => {
    if (prevNode.info.indent !== curNode.info.indent) {
        return false
    }
    if (prevRange.end.line !== curRange.start.line - 1) {
        return false
    }

    return true
}

export const getSuggestspecActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range) => {
    const comments = findNode(root, 'COMMENT')
    // merge comments
    const commentGroups = []
    let group = []
    let prevRange = null
    const _getGroupRange = (group: SyntaxTreeNode[]) => {
        return new vscode.Range(
            document.positionAt(group[0].info.start),
            document.positionAt(group[group.length - 1].info.end)
        )
    }
    for (const node of comments) {
        if (group.length === 0) {
            group.push(node)
            prevRange = getRangeFromNode(document, node)
            continue
        }

        const prevNode = group[group.length - 1]
        const curRange = getRangeFromNode(document, node)
        if (!_isSiblingComment(prevNode, prevRange!, node, curRange)) {
            commentGroups.push({
                nodes: group,
                range: _getGroupRange(group)
            })
            group = []
        }
        group.push(node)
        prevRange = curRange
    }
    if (group.length > 0) {
        commentGroups.push({
            nodes: group,
            range: _getGroupRange(group)
        })
    }
    const targetGroups = commentGroups.filter(
        group => group.range.intersection(triggerRange)?.isEmpty
    )
    if (targetGroups.length > 1) {
        return []
    }
    const text = targetGroups[0].nodes.map(node => getTextFromNode(document, node)).join('\n')
    if (!text.includes('condition')) {
        return []
    }

    const actionTitle = '[Verus Copilot] comments: convert to verus spec'
    const action = new vscode.CodeAction(
        actionTitle,
        vscode.CodeActionKind.QuickFix,
    )
    action.command = {
        title: actionTitle,
        command: 'verus-copilot.exec-code-action-suggest-spec',
        arguments: [
            targetGroups[0].range,
            document.uri,
            text,
            'suggestspec',
            targetGroups[0].nodes[0].info.indent,
        ],
    }
    return [action]
}
