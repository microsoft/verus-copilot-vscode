import * as vscode from 'vscode'
import { getSyntaxTree } from './syntaxTree'
import { getFnCodeActions } from './code-actions/fn'

export class VerusCopilotCodeActionProvier implements vscode.CodeActionProvider {
    public async provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        _context: vscode.CodeActionContext,
        _token: vscode.CancellationToken
    ): Promise<vscode.CodeAction[]> {
        const syntaxTree = await getSyntaxTree(document)
        const actions = [
            ...getFnCodeActions(document, syntaxTree, range)
        ]
        return actions
    }
}