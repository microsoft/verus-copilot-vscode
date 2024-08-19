// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';

import { initConsts } from './consts';
import { registerSyntaxTreeDisposable } from './syntaxTree';
import { execPython } from './pythonRunner'
import { VerusCopilotCodeActionProvier } from './codeActionProvider';

export function activate(context: vscode.ExtensionContext) {
	initConsts(context)
	registerSyntaxTreeDisposable(context)
	context.subscriptions.push(
		vscode.languages.registerCodeActionsProvider(
			{scheme: 'file', language: 'rust'},
			new VerusCopilotCodeActionProvier()
		),
		vscode.commands.registerCommand('verus-copilot.exec-code-action', async (replaceRange: vscode.Range, fileUri: vscode.Uri, ftype: string, params: object) => {
			const res = await execPython(fileUri, ftype, params)
			const edit = new vscode.WorkspaceEdit()
			edit.replace(
				fileUri,
				replaceRange,
				res
			)
			await vscode.workspace.applyEdit(edit)
		}),
		vscode.commands.registerCommand('verus-copilot.exec-code-action-suggest-spec', async (replaceRange: vscode.Range, fileUri: vscode.Uri, source: string, ftype: string, indent: number) => {
			const res = await execPython(source, ftype, {})
			const resWithIndent = res.split('\n').map(
				line => ' '.repeat(indent) + line
			).join('\n')
			const edit = new vscode.WorkspaceEdit()
			edit.replace(
				fileUri,
				replaceRange,
				resWithIndent,
			)
			await vscode.workspace.applyEdit(edit)
		}),
	)
}

// This method is called when your extension is deactivated
export function deactivate() {}
