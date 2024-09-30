import * as vscode from 'vscode'

export const applyEdit = async (srcUri: vscode.Uri, replaceRange: vscode.Range, newText: string) => {
    const edit = new vscode.WorkspaceEdit()
    edit.replace(
        srcUri,
        replaceRange,
        newText,
        {needsConfirmation: true, label: 'verus-copilot generated'}
    )
    await vscode.workspace.applyEdit(edit)
}
