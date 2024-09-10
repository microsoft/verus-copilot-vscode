
import * as vscode from 'vscode'

export const RUST_ANALYZER_CHECK_ON_SAVE_COMMAND = 'rust-analyzer.checkOnSave.overrideCommand'
export const RUST_ANALYZER_SERVER_PATH = 'rust-analyzer.server.path'
export const VC_VERUS_PATH = 'verus-copilot.verusPath'
export const VC_AOAI_URL = 'verus-copilot.aoai.url'
export const VC_AOAI_KEY = 'verus-copilot.aoai.key'
export const VC_AACS_ENABLED = 'verus-copilot.aacs.enabled'
export const VC_AACS_ENDPOINT = 'verus-copilot.aacs.endpoint'
export const VC_AACS_KEY = 'verus-copilot.aacs.key'

export const getRustAnalyzerConfig = () => {
    return vscode.workspace.getConfiguration('rust-analyzer')
}

export const getVerusCopilotConfig = () => {
    return vscode.workspace.getConfiguration('verus-copilot')
}

export const getConfigValue = <T>(key: string) => {
    const parts = key.split('.')
    const root = parts[0]
    const subSection = parts.slice(1).join('.')

    return vscode.workspace.getConfiguration(root).get<T>(subSection)
}


