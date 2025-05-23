import path from 'node:path'
import { URL } from 'node:url'
import { isEmpty } from 'lodash'

import { store } from '../store.js'
import {
    getConfigValue,
    getVerusBinaryPath,
    VC_AOAI_KEY,
    VC_AOAI_URL
} from '../config.js'

const defaultConfig = {
    // aoai
    aoai_api_base: [],
    aoai_api_key: [],
    aoai_generation_model: "",
    aoai_debug_model: "",
    aoai_api_version: "2023-12-01-preview",
    aoai_max_retries: 5,

    // path
    verus_path: '',
    example_path: '',
    lemma_path: '',
    util_path: '',

    debug_max_attempt: 5,
    debug_answer_num: 1,
    refine_answer_num: 1,
    debug_temp: 0.5,
    refine_temp: 0.7,
    max_token: 2048,
    n_retrieved: 0
}

export const getPythonRoot = () => {
    return path.join(store.context!.extensionPath, 'python')
}

const getAOAIConfig = () => {
    const aoaiUrlStr = getConfigValue<string>(VC_AOAI_URL)
    const aoaiKey = getConfigValue(VC_AOAI_KEY)
    if (isEmpty(aoaiUrlStr)) {
        throw new Error('Verus Copilot: Azure OpenAI url and key need to be specified in settings')
    }
    if (!aoaiUrlStr!.startsWith('https://')) {
        throw new Error('Verus Copilot: Invalid Azure OpenAI Url')
    }
    const aoaiUrl = new URL(aoaiUrlStr!)
    const base = `https://${aoaiUrl.host}`
    const apiVersion = aoaiUrl.searchParams.get('api-version') || "2023-12-01-preview"

    // get deployment id
    if (!aoaiUrl.pathname.startsWith('/openai/deployments/')) {
        throw new Error('Verus Copilot: Can not find deployment id in Azure OpenAI url')
    }
    const pathParts = aoaiUrl.pathname.split('/')
    if (pathParts.length < 4) {
        throw new Error('Verus Copilot: Can not find deployment id in Azure OpenAI url')
    }
    const deploymentId = pathParts[3]

    return {
        aoai_api_base: [base],
        aoai_api_key: isEmpty(aoaiKey) ? [] : [aoaiKey],
        aoai_generation_model: deploymentId,
        aoai_debug_model: deploymentId,
        aoai_api_version: apiVersion,
        aoai_max_retries: 5,
    }
}

export const genPythonExecConfig = () => {
    const res = {
        ...defaultConfig
    }
    // TODO: support custom temperature from vscode settings
    // paths
    const pythonRoot = getPythonRoot()
    res.verus_path = getVerusBinaryPath()
    res.example_path = path.join(pythonRoot, 'examples')
    res.lemma_path = path.join(pythonRoot, 'lemmas')
    res.util_path = path.join(pythonRoot, 'utils')
    // oai
    const aoaiConfig = getAOAIConfig()

    return {
        ...res,
        ...aoaiConfig
    }
}
