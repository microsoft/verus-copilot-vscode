import * as vscode from 'vscode'
import { randomUUID } from 'node:crypto'

export const verusCopilotDocScheme = 'verus-copilot'

export class VerusCopilotDocumentProvider implements vscode.TextDocumentContentProvider {

  private _onDidChange = new vscode.EventEmitter<vscode.Uri>()
  private _cache: {[key: string]: string} = {}

  constructor() {}

  get onDidChange() {
    return this._onDidChange.event
  }

  registerDocument(docText: string, filename: string, extra_query?: string) {
    if (extra_query == null) {
      extra_query = ''
    }
    const id = randomUUID()
    const uri = vscode.Uri.from({
      scheme: verusCopilotDocScheme,
      authority: id,
      path: '/' + filename,
      query: extra_query
    })
    this._cache[uri.toString()] = docText

    return uri
  }

  provideTextDocumentContent(uri: vscode.Uri) {
    return this._cache[uri.toString()]
  }

  showDocument(docText: string, filename: string) {
    const uri = this.registerDocument(docText, filename)
    vscode.window.showTextDocument(
      uri,
      {
        preserveFocus: true,
        viewColumn: vscode.ViewColumn.Beside
      }
    )
    return uri
  }
}
