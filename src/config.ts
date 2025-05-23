
import * as vscode from 'vscode'
import { isEmpty } from 'lodash'

export const VC_AOAI_URL = 'verus-copilot.aoai.url'
export const VC_AOAI_KEY = 'verus-copilot.aoai.key'
export const VC_AACS_ENABLED = 'verus-copilot.aacs.enabled'
export const VC_AACS_ENDPOINT = 'verus-copilot.aacs.endpoint'
export const VC_AACS_KEY = 'verus-copilot.aacs.key'
export const VA_VERUS_PATH = 'verus-analyzer.verus.verusBinary'
export const VA_SERVER_PATH = 'verus-analyzer.server.path'

export const getVerusAnalyzerConfig = () => {
    return vscode.workspace.getConfiguration('verus-analyzer')
}

export const getVerusCopilotConfig = () => {
    return vscode.workspace.getConfiguration('verus-copilot')
}

export const getVerusAnalyzerServerPath = () => {
    // verus analyzer's config
    let path = getConfigValue<string>(VA_SERVER_PATH)
    if (!isEmpty(path)) {
        return path!
    }
    // verus analyzer default path
    const vaExtension = vscode.extensions.getExtension('verus-lang.verus-analyzer')
    if (vaExtension == null) {
        vscode.window.showErrorMessage('Verus Copilot: verus analyzer extension not found')
        throw new Error('Verus Copilot: verus analyzer extension not found')
    }
    // logic from https://github.com/verus-lang/verus-analyzer/blob/582b0dad6aeb41f121a372064b1b3e1c358211ff/editors/code/src/bootstrap.ts#L58
    const ext = process.platform === "win32" ? ".exe" : "";
    const target_binary = vscode.Uri.joinPath(vaExtension.extensionUri, "server", `verus-analyzer${ext}`)
    return target_binary.fsPath
}

export const getVerusBinaryPath = (): string => {
    // verus analyzer's config
    let path = getConfigValue<string>(VA_VERUS_PATH)
    if (!isEmpty(path)) {
        return path!
    }
    // verus analyzer default path
    const vaExtension = vscode.extensions.getExtension('verus-lang.verus-analyzer')
    if (vaExtension == null) {
        vscode.window.showErrorMessage('Verus Copilot: verus analyzer extension not found')
        throw new Error('Verus Copilot: verus analyzer extension not found')
    }
    // logic from https://github.com/verus-lang/verus-analyzer/blob/582b0dad6aeb41f121a372064b1b3e1c358211ff/editors/code/src/bootstrap.ts#L122
    const target_dir = vscode.Uri.joinPath(vaExtension.extensionUri, "verus");
    const ext = process.platform === "win32" ? ".exe" : "";
    const target_binary = vscode.Uri.joinPath(target_dir, `verus${ext}`);
    return target_binary.fsPath
}

export const getConfigValue = <T>(key: string) => {
    const parts = key.split('.')
    const root = parts[0]
    const subSection = parts.slice(1).join('.')

    return vscode.workspace.getConfiguration(root).get<T>(subSection)
}

export const setConfigValue = <T>(key: string, val: T, configTarget?: vscode.ConfigurationTarget) => {
    const parts = key.split('.')
    const root = parts[0]
    const subSection = parts.slice(1).join('.')

    return vscode.workspace.getConfiguration(root).update(subSection, val, configTarget)
}
