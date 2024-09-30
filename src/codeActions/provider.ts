import * as vscode from 'vscode'
import { getSyntaxTree } from './syntaxTree.js'
import {
    getFungenActions,
    getPostcondfailActions,
    getAssertfaillemmaActions,
    getInvariantfailActions,
    getSuggestspecActions,
} from './actions.js'

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
        const actions = [
            ...getFungenActions(document, syntaxTree, range),
            ...getPostcondfailActions(document, syntaxTree, range),
            ...getAssertfaillemmaActions(document, syntaxTree, range),
            ...getInvariantfailActions(document, syntaxTree, range),
            ...getSuggestspecActions(document, syntaxTree, range),
        ]
        return actions
    }
}