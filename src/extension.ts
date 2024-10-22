// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import fs from 'node:fs/promises'

import { store } from './store.js';
import { execPython, abortPython } from './invokePython/exec.js'
import { VerusCopilotCodeActionProvier } from './codeActions/provider.js';
import { AACSCheckDocument } from './ui/aacsCheck.js';
import { verusCopilotDocScheme, VerusCopilotDocumentProvider } from './documentProvider.js';
import { applyEdit } from './ui/applyEdit.js';

const registerCommand = (context: vscode.ExtensionContext, commandId: string, func: Function) => {
	const wrapperFunc = async (...args: any[]) => {
		try {
			await func(...args)
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

	context.subscriptions.push(
		vscode.languages.registerCodeActionsProvider(
			{scheme: 'file', language: 'rust'},
			new VerusCopilotCodeActionProvier()
		),
		vscode.workspace.registerTextDocumentContentProvider(
			verusCopilotDocScheme,
			store.docProvider
		)
	)
	registerCommand(context, 'verus-copilot.exec-code-action', async (replaceRange: vscode.Range, fileUri: vscode.Uri, ftype: string, params: object, hasMainFn: boolean) => {
		const code = (await vscode.workspace.openTextDocument(fileUri)).getText()
		const aacsRes = await AACSCheckDocument(code)
		if (aacsRes === false) {
			return
		}

		const res = await execPython(fileUri, ftype, params, hasMainFn)
		await applyEdit(
			fileUri,
			replaceRange,
			res
		)
	})
	registerCommand(context, 'verus-copilot.exec-code-action-suggest-spec', async (replaceRange: vscode.Range, fileUri: vscode.Uri, comments: string, ftype: string, indent: number, hasMainFn: boolean) => {
		const code = (await vscode.workspace.openTextDocument(fileUri)).getText()
		const aacsRes = await AACSCheckDocument(code)
		if (aacsRes === false) {
			return
		}

		const res = await execPython(fileUri, ftype, {}, hasMainFn, comments)
		const resWithIndent = res.split('\n').map(
			line => ' '.repeat(indent) + line
		).join('\n')
		
		await applyEdit(
			fileUri,
			replaceRange,
			resWithIndent
		)
	})
	registerCommand(context, 'verus-copilot.abort-code-action', async () => {
		await abortPython()
	})
}

// This method is called when your extension is deactivated
export function deactivate() {}
