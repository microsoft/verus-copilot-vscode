import * as vscode from 'vscode'
import got from 'got'
import { isEmpty } from 'lodash'
import { AzureCliCredential } from '@azure/identity'
import { store } from '../store.js'
import { getConfigValue, setConfigValue, VC_AACS_ENABLED, VC_AACS_ENDPOINT, VC_AACS_KEY } from '../config.js'

const sendRequest = async ( code: string, endpoint: string, key?: string): Promise<boolean> => {
    store.outputChannel!.show(true)
    const headers: any = {}
    if (!isEmpty(key)) {
        headers['Ocp-Apim-Subscription-Key'] = key
        store.outputChannel!.info('AACS: using provided key')
    } else {
        const cred = new AzureCliCredential()
        const token = (await cred.getToken('https://cognitiveservices.azure.com/.default')).token
        headers['Authorization'] = 'Bearer ' + token
        store.outputChannel!.info('AACS: using token from Azure CLI')
    }
    const url = new URL(endpoint)
    url.pathname += url.pathname.endsWith('/') ? '' : '/'
    url.pathname += 'contentsafety/text:shieldPrompt'
    url.searchParams.set('api-version', '2024-09-01')
    const res: any = await got.post(url, {
        headers,
        json: {
            'userPrompt': '',
            'documents': [
                code
            ]
        }
    }).json()

    return res['documentsAnalysis'][0]['attackDetected']!
}

export const AACSCheckDocument = async (code: string) => {
    let aacsEnabled = getConfigValue(VC_AACS_ENABLED)
    if (aacsEnabled == null) {
        aacsEnabled = true
    }
    if (!aacsEnabled) {
        store.outputChannel!.info('AACS: disabled in user settings, skipped.')
        return true
    }

    const aacsEndpoint = getConfigValue<string>(VC_AACS_ENDPOINT)
    const aacsKey = getConfigValue<string>(VC_AACS_KEY)

    if (isEmpty(aacsEndpoint)) {
        const aacaRedirectOption = 'About AACS'
        const userSettingOption = 'Open User Settings'
        const disableOption = 'Disable AACS'
        const res = await vscode.window.showErrorMessage(
            'We recommend using Azure AI Content Safety to prevent potential prompt jailbreak attacks. Please specify your AACS endpoint in "verus-copilot.aacs" section of vscode settings.',
            aacaRedirectOption,
            userSettingOption,
            disableOption
        )
        if (res === aacaRedirectOption) {
            vscode.env.openExternal(vscode.Uri.parse('https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection'))
        } else if (res === userSettingOption) {
            await vscode.commands.executeCommand('workbench.action.openWorkspaceSettings', {
                revealSetting: { key: VC_AACS_ENDPOINT }
            })
            return false
        } else if (res === disableOption) {
            await setConfigValue(VC_AACS_ENABLED, false, vscode.ConfigurationTarget.WorkspaceFolder)
            store.outputChannel!.info('AACS: disabled in user settings, skipped.')
            return true
        } else {
            return false
        }
    }

    // execute aacs request
    const attackDetected = await sendRequest(code, aacsEndpoint!, aacsKey)
    if (attackDetected) {
        const option = 'About Prompt Shields'
        const res = await vscode.window.showWarningMessage(
            'Document jailbreak detected! Please refer to Azure AI Content Safety Prompt Shields for more information.',
            option,
        )
        if (res === option) {
            vscode.env.openExternal(vscode.Uri.parse('https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection'))
        }

        store.outputChannel!.info('AACS: attack detected, blocked.')
        return false
    } else {
        store.outputChannel!.info('AACS: passed.')
        return true
    }
}