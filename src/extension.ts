// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import fs from 'node:fs/promises'

import { store } from './store.js';
import { registerSyntaxTreeDisposable } from './codeActions/syntaxTree.js';
import { execPython, abortPython } from './invokePython/exec.js'
import { VerusCopilotCodeActionProvier } from './codeActions/provider.js';
import { AACSCheckDocument } from './ui/aacsCheck.js';
import { VerusCopilotDocumentProvider } from './documentProvider.js';

const registerCommand = (context: vscode.ExtensionContext, commandId: string, func: Function) => {
	const wrapperFunc = async () => {
		try {
			await func()
		} catch(e) {
			const message = (e instanceof Error) ? e.message : e
			vscode.window.showErrorMessage('Verus Copilot: ' + message, {
				modal: true
			})
		}
	}
	context.subscriptions.push(
		vscode.commands.registerCommand(
			commandId,
			wrapperFunc,
		)
	)
}

export function activate(context: vscode.ExtensionContext) {
	store.context = context
	store.outputChannel = vscode.window.createOutputChannel('Verus Copilot', {log: true})
	store.docProvider = new VerusCopilotDocumentProvider()
	
	registerSyntaxTreeDisposable(context)
	context.subscriptions.push(
		vscode.languages.registerCodeActionsProvider(
			{scheme: 'file', language: 'rust'},
			new VerusCopilotCodeActionProvier()
		)
	)
	registerCommand(context, 'verus-copilot.exec-code-action', async (replaceRange: vscode.Range, fileUri: vscode.Uri, ftype: string, params: object) => {
		const code = await fs.readFile(fileUri.fsPath, 'utf8')
		const aacsRes = await AACSCheckDocument(code)
		if (aacsRes === false) {
			return
		}

		const res = await execPython(fileUri, ftype, params)
		const edit = new vscode.WorkspaceEdit()
		edit.replace(
			fileUri,
			replaceRange,
			res
		)
		await vscode.workspace.applyEdit(edit)
	})
	registerCommand(context, 'verus-copilot.exec-code-action-suggest-spec', async (replaceRange: vscode.Range, fileUri: vscode.Uri, source: string, ftype: string, indent: number) => {
		const code = await fs.readFile(fileUri.fsPath, 'utf8')
		const aacsRes = await AACSCheckDocument(code)
		if (aacsRes === false) {
			return
		}

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
	})
	registerCommand(context, 'verus-copilot.abort-code-action', async () => {
		await abortPython()
	})
}

// This method is called when your extension is deactivated
export function deactivate() {}
