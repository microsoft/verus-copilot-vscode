import * as vscode from 'vscode'
import path from 'node:path'
import os from 'node:os'
import fs from 'node:fs/promises'
import { spawn, ChildProcess } from 'node:child_process'
import { PythonExtension } from '@vscode/python-extension'

import { store } from '../store.js'
import { genPythonExecConfig, getPythonRoot } from './utils.js'

type PythonProcessContext = {
    tempFolder?: string,
    process?: ChildProcess,
    promise?: Promise<any>,
}

let context: PythonProcessContext | undefined = undefined

export const abortPython = async () => {
    if (context == null) {
        return
    }
    const prevContext = context
    context = undefined
    if (prevContext.process != null && prevContext.process) {
        prevContext.process.kill()
    }
    if (prevContext.promise != null) {
        await prevContext.promise.catch(() => {})
    }
    if (prevContext.tempFolder != null) {
        await fs.rm(prevContext.tempFolder, {recursive: true, force: true})
    }
}

const execPythonInner = async (tempFolder: string, source: string, ftype: string, params: object) => {
    // dump config
    const config = genPythonExecConfig()
    const tempConfigPath = path.join(tempFolder, 'config.json')
    await fs.writeFile(tempConfigPath, JSON.stringify(config))
    const tempCodePath = path.join(tempFolder, 'code.rust')
    await fs.writeFile(tempCodePath, source)
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
    return proc
}

export const execPython = async (source: string, ftype: string, params: object): Promise<string> => {
    if (context != null) {
        throw new Error('Verus Copilot: Copilot request is already processing.')
    }
    context = {}
    return vscode.window.withProgress(
        {
            cancellable: true,
            location: vscode.ProgressLocation.Notification,
            title: 'Verus Copilot: Request in progress'
        },
        async (_progress, token) => {
            token.onCancellationRequested(async () => {
                await abortPython()
            })
            const tempFolder = await fs.mkdtemp(path.join(os.tmpdir(), 'verus-copilot-'))
            context!.tempFolder = tempFolder
            const process = await execPythonInner(tempFolder, source, ftype, params)
            context!.process = process
            
            store.outputChannel!.show(true)
            context!.promise = new Promise((resolve, reject) => {
                const stdout: string[] = []
                process.stdout.on('data', data => {
                    store.outputChannel!.info('python stdout: ' + data.toString().trimEnd())
                    stdout.push(data.toString())
                })
                process.stderr.on('data', data => {
                    store.outputChannel!.error('python stderr: ' + data.toString().trimEnd())
                })
                process.on('exit', code => {
                    if (code === 0) {
                        resolve(stdout.join('\n'))
                    } else {
                        reject('Verus Copilot: Failed to run python prompt script, please check Verus Copilot\'s output log for detail information.')
                    }
                })
            })
            try {
                return await context!.promise
            } finally {
                // clean
                await abortPython()
            }
        }
    )
}
