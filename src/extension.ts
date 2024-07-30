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
		vscode.commands.registerCommand('verus-copilot.exec-code-action', async (replaceRange: vscode.Range, fileUri: vscode.Uri, fnName: string, ftype: string) => {
			const res = await execPython(fileUri, fnName, ftype)
			const edit = new vscode.WorkspaceEdit()
			edit.replace(
				fileUri,
				replaceRange,
				res
			)
			await vscode.workspace.applyEdit(edit)
		}),
	)
}

// This method is called when your extension is deactivated
export function deactivate() {}
