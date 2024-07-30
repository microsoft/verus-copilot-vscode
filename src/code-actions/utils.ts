
import {SyntaxTreeNode} from '../syntaxTree'

export type FnInfo = {
    node: SyntaxTreeNode
    body: SyntaxTreeNode
}

// TODO: recursive limit
const findFunctionsRecursive = (cur: SyntaxTreeNode, res: Array<FnInfo>) => {
    if (cur.info.type === 'FN') {
        const body = cur.children.find(x => x.info.type == 'BLOCK_EXPR')
        if (body != null) {
            res.push({
                node: cur,
                body,
            })
        }
    }
    for (const child of cur.children) {
        findFunctionsRecursive(child, res)
    }
}

export const findFunctions = (root: SyntaxTreeNode) => {
    const res: Array<FnInfo> = []
    findFunctionsRecursive(root, res)

    return res
}

export type TokenInfo = {
    node: SyntaxTreeNode
    parentFn: FnInfo
}

const findTokenRecursive = (cur: SyntaxTreeNode, token: string, res: Array<SyntaxTreeNode>) => {
    if (cur.info.type === 'FN') {
        return
    }
    if (cur.info.type === token) {
        res.push(cur)
    }
    for (const child of cur.children) {
        findTokenRecursive(child, token, res)
    }
}

export const findToken = (root: SyntaxTreeNode, token: string) => {
    const fns = findFunctions(root)
    const res: Array<TokenInfo> = []
    for (const fn of fns) {
        if (fn.body == null) {
            continue
        }
        const fnRes: Array<SyntaxTreeNode> = []
        findTokenRecursive(fn.body, token, fnRes)
        for (const node of fnRes) {
            res.push({
                node,
                parentFn: fn
            })
        }
    }

    return res
}