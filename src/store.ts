import * as vscode from 'vscode'
import { VerusCopilotDocumentProvider } from './documentProvider.js'

type StoreStruct = {
    context?: vscode.ExtensionContext,
    outputChannel?: vscode.LogOutputChannel,
    docProvider?: VerusCopilotDocumentProvider,
}

export const store: StoreStruct = {}
