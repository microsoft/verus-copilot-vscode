import * as vscode from 'vscode'
import { getSyntaxTree } from './syntaxTree.js'
import {
    getFungenActions,
    getPostcondfailActions,
    getAssertfaillemmaActions,
    getAssertreqActions,
    getAsserttriggerActions,
    getAssertimplyActions,
    getInvariantfailActions,
    getSuggestspecActions,
} from './actions.js'
import { findMainFn } from './utils.js'

export class VerusCopilotCodeActionProvier implements vscode.CodeActionProvider {
    public async provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        _context: vscode.CodeActionContext,
        _token: vscode.CancellationToken
    ): Promise<vscode.CodeAction[]> {

        // try using selection range if applicable
        const editor = vscode.window.activeTextEditor
        if (editor != null) {
            const selection = editor.selection
            if (selection != null) {
                range = new vscode.Range(
                    selection.start.line,
                    selection.start.character,
                    selection.end.line,
                    selection.end.character
                )
            }
        }

        const syntaxTree = await getSyntaxTree(document)

        const hasMainFn = (findMainFn(syntaxTree) != null)
        const actions = [
            ...getFungenActions(document, syntaxTree, range, hasMainFn),
            ...getPostcondfailActions(document, syntaxTree, range, hasMainFn),
            ...getAssertfaillemmaActions(document, syntaxTree, range, hasMainFn),
            ...getAssertreqActions(document, syntaxTree, range, hasMainFn),
            ...getAsserttriggerActions(document, syntaxTree, range, hasMainFn),
            ...getAssertimplyActions(document, syntaxTree, range, hasMainFn),
            ...getInvariantfailActions(document, syntaxTree, range, hasMainFn),
            ...getSuggestspecActions(document, syntaxTree, range, hasMainFn),
        ]
        return actions
    }
}
