import * as vscode from 'vscode'
import got from 'got'
import { isEmpty } from 'lodash'
import { AzureCliCredential } from '@azure/identity'
import { getConfigValue, getVerusCopilotConfig, VC_AACS_ENABLED, VC_AACS_ENDPOINT, VC_AACS_KEY } from '../config.js'

const sendRequest = async ( code: string, endpoint: string, key?: string): Promise<boolean> => {
    const headers: any = {}
    if (key != null) {
        headers['Ocp-Apim-Subscription-Key'] = key
    } else {
        const cred = new AzureCliCredential()
        const token = (await cred.getToken('https://cognitiveservices.azure.com/.default')).token
        headers['Authorization'] = 'Bearer ' + token
    }

    const url = new URL(endpoint)
    url.pathname += url.pathname.endsWith('/') ? '' : '/'
    url.pathname += 'contentsafety/text:shieldPrompt'
    url.searchParams.set('api-version', '2024-09-01')
    const res: any = await got.get(url, {
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
        return true
    }

    const aacsEndpoint = getConfigValue<string>(VC_AACS_ENDPOINT)
    const aacsKey = getConfigValue<string>(VC_AACS_KEY)

    if (isEmpty(aacsEndpoint)) {
        const userSettingOption = 'Open User Settings'
        const disableOption = 'Disable AACS'
        const res = await vscode.window.showInformationMessage(
            'Please specify your Azure AI Content Safety endpoint.',
            userSettingOption,
            disableOption
        )
        if (res === userSettingOption) {
            await vscode.commands.executeCommand('workbench.action.openWorkspaceSettings', {
                revealSetting: { key: VC_AACS_ENDPOINT }
            })
            return false
        } else if (res === disableOption) {
            const config = getVerusCopilotConfig()
            config.update(VC_AACS_ENABLED, false, vscode.ConfigurationTarget.WorkspaceFolder)
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

        return false
    } else {
        return true
    }
}