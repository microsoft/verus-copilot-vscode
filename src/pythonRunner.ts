import * as vscode from 'vscode'
import path from 'node:path'
import os from 'node:os'
import fs from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { URL } from 'node:url'
import { PythonExtension } from '@vscode/python-extension'

import { context } from './consts'

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

const getPythonRoot = () => {
    return path.join(context?.extensionPath, 'python')
}

const getAOAIConfig = () => {
    const config = vscode.workspace.getConfiguration('verus-copilot')
    const aoaiUrlStr = config.get<string>('aoai.url')
    const aoaiKey = config.get<string>('aoai.key')
    if (aoaiUrlStr == null || aoaiUrlStr === '') {
        throw new Error('Verus Copilot: Azure OpenAI url and key need to be specified in settings')
    }

    const aoaiUrl = new URL(aoaiUrlStr)
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
        aoai_api_key: [aoaiKey],
        aoai_generation_model: deploymentId,
        aoai_debug_model: deploymentId,
        aoai_api_version: apiVersion,
        aoai_max_retries: 5,
    }
}

const getVerusPath = () => {
    let path = vscode.workspace.getConfiguration('verus-copilot').get<string>('verusPath')
    if (path != null && path != '') {
        return path
    }

    const path_list = vscode.workspace.getConfiguration('rust-analyzer').get<string[]>('checkOnSave.overrideCommand')
    if (path_list != null && path_list.length > 0) {
        return path_list[0]
    }

    throw new Error('Verus Copilot: Verus binary path need to be specified in settings')
}

const genConfig = () => {
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

export let isRunning = false
export const execPython = async (fileUriOrSource: vscode.Uri | string, ftype: string, params: object) => {
    if (isRunning) {
        throw new Error('Verus Copilot: Copilot request is already processing.')
    }
    isRunning = true
    const tempFolder = await fs.mkdtemp(path.join(os.tmpdir(), 'verus-copilot-'))
    try {
        // dump config
        const config = genConfig()
        const tempConfigPath = path.join(tempFolder, 'config.json')
        await fs.writeFile(tempConfigPath, JSON.stringify(config))
        const tempCodePath = path.join(tempFolder, 'code.rust')
        if (typeof(fileUriOrSource) == 'string') {
            await fs.writeFile(tempCodePath, fileUriOrSource)
        } else {
            await fs.copyFile(fileUriOrSource.fsPath, tempCodePath)
        }
        // get interpreter from python extension
        const pythonApi = await PythonExtension.api()
        const pythonBin = pythonApi.environments.getActiveEnvironmentPath().path

        const pythonSrc = path.join(getPythonRoot(), 'src')
        const scriptFile = path.join(pythonSrc, 'plugin_repair.py')
        // run python

        const args = [
            scriptFile,
            '--input',
            tempCodePath,
            '--config',
            tempConfigPath,
            '--ftype',
            ftype
        ]
        for (const [key, val] of Object.entries(params)) {
            args.push(
                `--${key}`,
                val,
            )
        }

        const proc = spawn(
            pythonBin,
            args,
            {
                env: {
                    'PYTHONPATH': pythonSrc
                },
            }
        )
        const stdout: string[] = []
        proc.stdout.on('data', data => {
            console.log('stdout: ' + data.toString())
            stdout.push(data.toString())
        })
        proc.stderr.on('data', data => console.log('stderr: ' + data.toString()))
        await new Promise((resolve, reject) => {
            proc.on('exit', code => {
                if (code === 0) {
                    resolve(code)
                } else {
                    reject('Verus Copilot: Failed to run python prompt script, please check dev tools for detail information.')
                }
            })
        })
        // TODO: detect unsafe / incorrect output
        return stdout.join('')
    } finally {
        isRunning = false
        // clean
        await fs.rm(tempFolder, {recursive: true, force: true})
    }
}
