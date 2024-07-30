import * as vscode from 'vscode'
import { findFunctions } from './utils'
import { SyntaxTreeNode } from '../syntaxTree'

export const getFnCodeActions = (document: vscode.TextDocument, root: SyntaxTreeNode, range: vscode.Range) => {
    const fnInfoList = findFunctions(root)
    const res = fnInfoList.map(fn => {
        const fnRange = new vscode.Range(
            document.positionAt(fn.node.info.start),
            document.positionAt(fn.node.info.end)
        )
        const bodyRange = new vscode.Range(
            document.positionAt(fn.body.info.start),
            document.positionAt(fn.body.info.end)
        )

        const nameNode = fn.node.children.find(x => x.info.type == 'NAME')
        if (nameNode == null) return
        const identNode = nameNode.children.find(x => x.info.type == 'IDENT')
        if (identNode == null || identNode.info.value == null || identNode.info.value.length === 0) return
        const fnName = identNode.info.value

        return {
            triggerRange: fnRange,
            replaceRange: bodyRange,
            fileUri: document.uri,
            fnName: fnName,
            ftype: 'fungen'
        }
    }).filter(
        actionInfo => actionInfo != null && range.intersection(actionInfo.triggerRange) != null
    ).map(actionInfo => {
        const action = new vscode.CodeAction(
            'fn: Generate proof using Verus Copilot',
            vscode.CodeActionKind.QuickFix,
        )
        action.command = {
            title: 'fn: Generate proof using Verus Copilot',
            command: 'verus-copilot.exec-code-action',
            arguments: [
                actionInfo?.replaceRange,
                actionInfo?.fileUri,
                actionInfo?.fnName,
                actionInfo?.ftype
            ],
        }

        return action
    })

    return res
}
