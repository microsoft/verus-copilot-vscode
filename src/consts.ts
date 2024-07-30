import * as vscode from 'vscode'

export let context: vscode.ExtensionContext

export const initConsts = (ctx: vscode.ExtensionContext) => {
    context = ctx
}
