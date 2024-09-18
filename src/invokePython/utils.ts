import path from 'node:path'
import { URL } from 'node:url'
import { isEmpty } from 'lodash'

import { store } from '../store.js'
import {
    getConfigValue,
    RUST_ANALYZER_CHECK_ON_SAVE_COMMAND,
    VC_AOAI_KEY,
    VC_AOAI_URL,
    VC_VERUS_PATH
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
    corpus_path: '',

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
    const aoaiUrlStr = getConfigValue(VC_AOAI_URL)
    const aoaiKey = getConfigValue(VC_AOAI_KEY)
    if (isEmpty(aoaiUrlStr)) {
        throw new Error('Verus Copilot: Azure OpenAI url and key need to be specified in settings')
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

const getVerusPath = (): string => {
    let path = getConfigValue<string>(VC_VERUS_PATH)
    if (!isEmpty(path)) {
        return path!
    }

    const path_list = getConfigValue<string[]>(RUST_ANALYZER_CHECK_ON_SAVE_COMMAND)
    if (!isEmpty(path_list)) {
        return path_list![0]
    }

    throw new Error('Verus Copilot: Verus binary path need to be specified in settings')
}

export const genPythonExecConfig = () => {
    const res = {
        ...defaultConfig
    }
    // TODO: support custom temperature from vscode settings
    // paths
    const pythonRoot = getPythonRoot()
    res.verus_path = getVerusPath()
    res.example_path = path.join(pythonRoot, 'examples')
    res.lemma_path = path.join(pythonRoot, 'lemmas')
    res.util_path = path.join(pythonRoot, 'utils')
    res.corpus_path = path.join(pythonRoot, 'corpus', 'corpus.jsonl')
    // oai
    const aoaiConfig = getAOAIConfig()

    return {
        ...res,
        ...aoaiConfig
    }
}