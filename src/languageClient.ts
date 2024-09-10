import * as lc from "vscode-languageclient/node.js"
import { getRustAnalyzerConfig, getConfigValue, RUST_ANALYZER_SERVER_PATH } from './config.js'

let _client: lc.LanguageClient | null = null

export const getLanguageClient = () => {
    if (_client != null) {
        return _client
    }

    const path = getConfigValue<string>(RUST_ANALYZER_SERVER_PATH)
    if (path == null) {
        throw Error('verus analyzer is not installed')
    }
	
    _client = new lc.LanguageClient(
		'verus-copilot.verus-analyzer.lc',
		{ command: path },
		{
			initializationOptions: getRustAnalyzerConfig(),
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
