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

const _findCargoToml = async (root: string, current: string) => {
    const rel = path.relative(root, current)
    if (rel.startsWith('..')) {
        return null
    }
    const dirents = await fs.readdir(current, {withFileTypes: true})
    for (const d of dirents) {
        if (d.name === 'Cargo.toml' && d.isFile()) {
            return path.resolve(current, d.name)
        }
    }

    const parent = path.dirname(current)
    if (path.relative(parent, current) === '') {
        return null
    }

    return _findCargoToml(root, parent)
}

const _prepWorkspace = async (tempRoot: string, uri: vscode.Uri) => {
    const wsFolder = vscode.workspace.getWorkspaceFolder(uri)
    if (wsFolder == null) {
        throw new Error(`Target file doesn't have main function or isn't in a valid rust project folder: ${uri.fsPath}`)
    }
    for (const doc of vscode.workspace.textDocuments) {
        if (doc.isDirty && vscode.workspace.getWorkspaceFolder(doc.uri) == wsFolder) {
            throw new Error(`Please ensure all modified files are saved before using verus copilot: ${doc.uri.fsPath}`)
        }
    }

    const cargoPath = await _findCargoToml(wsFolder.uri.fsPath, path.dirname(uri.fsPath))
    if (cargoPath == null) {
        throw new Error('Can not find Cargo.toml in the workspace folder')
    }

    const srcDir = await fs.readdir(path.join(path.dirname(cargoPath), 'src'), {withFileTypes: true})
    const mainRes = srcDir.find(d => d.name.toLowerCase() === 'main.rs' && d.isFile())
    const libRes = srcDir.find(d => d.name.toLowerCase() === 'lib.rs' && d.isFile())
    let targetMainFile = null
    if (mainRes != null) {
        targetMainFile = path.join(mainRes.parentPath, mainRes.name)
    } else if (libRes != null) {
        targetMainFile = path.join(libRes.parentPath, libRes.name)
    } else {
        throw new Error('Can not find src/main.rs or src/lib.rs in the workspace folder.')
    }

    const rustFiles = await vscode.workspace.findFiles(new vscode.RelativePattern(wsFolder, '**/*.rs'))
    for (const uri of rustFiles) {
        const dst = path.resolve(tempRoot, path.relative(wsFolder.uri.fsPath, uri.fsPath))
        await fs.mkdir(path.dirname(dst), {recursive: true})
        await fs.cp(uri.fsPath, dst)
    }

    const dstCargo = path.resolve(tempRoot, path.relative(wsFolder.uri.fsPath, cargoPath))
    await fs.cp(cargoPath, dstCargo)
    const dstMain = path.resolve(tempRoot, path.relative(wsFolder.uri.fsPath, targetMainFile))
    const dstInput = path.resolve(tempRoot, path.relative(wsFolder.uri.fsPath, uri.fsPath))
    return {
        inputPath: dstInput,
        mainPath: dstMain,
        tomlPath: dstCargo,
    }
}

const _prepSingleFile = async (tempRoot: string, uriOrCode: vscode.Uri | string) => {
    const codePath = path.join(tempRoot, 'code.rs')
    let code
    if (typeof uriOrCode === 'string') {
        code = uriOrCode
    } else {
        code = (await vscode.workspace.openTextDocument(uriOrCode)).getText()
    }
    await fs.writeFile(codePath, code)

    return codePath
}

const execPythonInner = async (tempFolder: string, uri: vscode.Uri, ftype: string, params: object, hasMainFn: boolean, externalCode?: string) => {
    // dump config
    const config = genPythonExecConfig()
    const tempConfigPath = path.join(tempFolder, 'config.json')
    await fs.writeFile(tempConfigPath, JSON.stringify(config))
    const tempCodeRoot = path.join(tempFolder, 'code')
    await fs.mkdir(tempCodeRoot)
    let inputPath, mainPath, tomlPath
    if (externalCode != null) {
        inputPath = await _prepSingleFile(tempCodeRoot, externalCode)
    } else if (hasMainFn) {
        inputPath = await _prepSingleFile(tempCodeRoot, uri)
    } else {
        ({inputPath, mainPath, tomlPath} = await _prepWorkspace(tempCodeRoot, uri))
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
        inputPath,
        '--config',
        tempConfigPath,
        '--ftype',
        ftype
    ]
    if (mainPath != null) {
        args.push(
            '--main_file',
            mainPath
        )
    }
    if (tomlPath != null) {
        args.push(
            '--toml_file',
            tomlPath
        )
    }

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

export const execPython = async (uri: vscode.Uri, ftype: string, params: object, hasMainFn: boolean, externalCode?: string): Promise<string> => {
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
            try {
                const tempFolder = await fs.mkdtemp(path.join(os.tmpdir(), 'verus-copilot-'))
                context!.tempFolder = tempFolder
                const process = await execPythonInner(tempFolder, uri, ftype, params, hasMainFn, externalCode)
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
                return await context!.promise
            } finally {
                // clean
                await abortPython()
            }
        }
    )
}
