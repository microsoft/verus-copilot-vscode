import * as vscode from 'vscode'
import { findNode, parseFnNode, getRangeFromNode, findParent, genCodeAction, getTextFromNode, getPositionFromSyntaxTreeOffset } from './utils.js'
import { SyntaxTreeNode } from './syntaxTree.js'

export const getFungenActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
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
                },
                hasMainFn,
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

export const getPostcondfailActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
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
                },
                hasMainFn,
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


export const getAssertfaillemmaActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
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
                },
                hasMainFn
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

export const getAssertreqActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
    const res = findNode(
        root,
        'ASSERT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] assert: leverage function pre-conditions',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'assertreq',
                params: {
                    func: fnName
                },
                hasMainFn
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


export const getAsserttriggerActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
    const res = findNode(
        root,
        'ASSERT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] assert: fix trigger mismatch',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'asserttrigger',
                params: {
                    func: fnName
                },
                hasMainFn
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

export const getAssertimplyActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
    const res = findNode(
        root,
        'ASSERT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] assert: rewrite forall with imply',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'assertimply',
                params: {
                    func: fnName
                },
                hasMainFn
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


export const getInvariantfailActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
    const res = findNode(
        root,
        'INVARIANT_KW'
    ).map(node => {
        try {
            const fnNode = findParent(node, 'FN')
            if (fnNode == null) {
                return null
            }
            const {bodyNode, fnName} = parseFnNode(fnNode)
            return {
                actionTitle: '[Verus Copilot] invariant: repair failing invariants',
                eventRange: getRangeFromNode(document, node),
                replaceRange: getRangeFromNode(document, bodyNode),
                fileUri: document.uri,
                ftype: 'invariantfail',
                params: {
                    func: fnName,
                },
                hasMainFn
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

const _getGroupRange = (document: vscode.TextDocument, group: SyntaxTreeNode[]) => {
    return new vscode.Range(
        getPositionFromSyntaxTreeOffset(document, group[0].info.start),
        getPositionFromSyntaxTreeOffset(document, group[group.length - 1].info.end)
    )
}

export const getSuggestspecActions = (document: vscode.TextDocument, root: SyntaxTreeNode, triggerRange: vscode.Range, hasMainFn: boolean) => {
    const comments = findNode(root, 'COMMENT')
    // merge comments
    const commentGroups = []
    let curCommentGroup = []
    let prevRange = null
    for (const node of comments) {
        if (curCommentGroup.length === 0) {
            curCommentGroup.push(node)
            prevRange = getRangeFromNode(document, node)
            continue
        }

        const prevNode = curCommentGroup[curCommentGroup.length - 1]
        const curRange = getRangeFromNode(document, node)
        if (!_isSiblingComment(prevNode, prevRange!, node, curRange)) {
            commentGroups.push({
                nodes: curCommentGroup,
                range: _getGroupRange(document, curCommentGroup)
            })
            curCommentGroup = []
        }
        curCommentGroup.push(node)
        prevRange = curRange
    }
    if (curCommentGroup.length > 0) {
        commentGroups.push({
            nodes: curCommentGroup,
            range: _getGroupRange(document, curCommentGroup)
        })
    }
    // select comment group
    const targetGroups = commentGroups.filter(
        group => group.range.intersection(triggerRange)?.isEmpty
    )
    if (targetGroups.length !== 1) {
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
            hasMainFn,
        ],
    }
    return [action]
}
