import * as vscode from 'vscode'
import * as lc from "vscode-languageclient/node";

let _client: lc.LanguageClient | null = null

export const getLanguageClient = () => {
    if (_client != null) {
        return _client
    }

    const raConfig = vscode.workspace.getConfiguration('rust-analyzer')
    const path = raConfig.get<string>('server.path')
    if (path == null) {
        throw Error('verus analyzer is not installed')
    }
	
    _client = new lc.LanguageClient(
		'verus-copilot.verus-analyzer.lc',
		{ command: path },
		{
			initializationOptions: vscode.workspace.getConfiguration('rust-analyzer'),
			middleware: {
				workspace: {
					async didChangeWatchedFile(event, next) {
                        if (_client == null) {
                            return
                        }
						if (_client.isRunning()) {
							await next(event);
						}
					},
				}
			}
		}
	)

    return _client
}
