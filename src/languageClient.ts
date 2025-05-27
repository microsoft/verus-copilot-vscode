import * as vscode from 'vscode'
import * as lc from "vscode-languageclient/node.js"
import { getVerusAnalyzerServerPath, getVerusAnalyzerConfig } from './config.js'

let _client: lc.LanguageClient | null = null
let _prevPath: string | null = null
let _messageSent = false

export const getLanguageClient = () => {
    const path = getVerusAnalyzerServerPath()
	if (_client != null && _client.state !== lc.State.Stopped) {
		if (path === _prevPath) {
			return _client
		} else {
			_client.dispose()
			_client = null
		}
	}

	if (path == null || path === _prevPath) {
		if (!_messageSent) {
			vscode.window.showErrorMessage('Verus Copilot: Can not connect to verus analyzer')
			_messageSent = true
		}
		throw new Error('Failed to get language client.')
	} else {
		// path changed, reset message flag
		_messageSent = false
	}

	_prevPath = path
    _client = new lc.LanguageClient(
		'verus-copilot.verus-analyzer.lc',
		{ command: path },
		{
			documentSelector: [{ scheme: "file", language: "rust" }],
			initializationOptions: getVerusAnalyzerConfig(),
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
