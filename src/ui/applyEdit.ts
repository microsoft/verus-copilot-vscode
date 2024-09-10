import * as vscode from 'vscode'

import { store } from '../store.js'


export const applyEdit = async (srcUri: vscode.Uri, replaceRange: vscode.Range, newText: string) => {
    const edit = new vscode.WorkspaceEdit()
    edit.replace(
        srcUri,
        replaceRange,
        newText
    )
    await vscode.workspace.applyEdit(edit)
}

export const applyEditWithDiffEditor = async (srcUri: vscode.Uri, replaceRange: vscode.Range, newText: string) => {
    const srcDoc = await vscode.workspace.openTextDocument(srcUri)
    const srcText = srcDoc.getText()
    const replaceStart = srcDoc.offsetAt(replaceRange.start)
    const replaceEnd = srcDoc.offsetAt(replaceRange.end)
    const dstText = srcText.slice(0, replaceStart) + newText + srcText.slice(replaceEnd)
    const dstUri = store.docProvider!.registerDocument(dstText, 'generated')
    
    await vscode.commands.executeCommand(
        'vscode.diff',
        srcUri,
        dstUri,
        'verus-copilot generated results', {
            viewColumn: vscode.ViewColumn.Beside
        }
    )

    const applyOption = 'Apply Edit'
    const cancelOption = 'Cancel'
    const res = await vscode.window.showInformationMessage(
        'Apply generated result?',
        applyOption,
        cancelOption
    )
    if (res === applyOption) {
        await applyEdit(srcUri, replaceRange, newText)
    }
}