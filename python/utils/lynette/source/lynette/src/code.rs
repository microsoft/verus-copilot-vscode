use quote::ToTokens;
use serde_json::json;
use std::ops::RangeInclusive;
use std::path::PathBuf;
use syn::spanned::Spanned;

use crate::func::detect_non_linear_assert_expr;
use crate::utils::*;

#[derive(Debug)]
pub enum CallType<'a> {
    Function(&'a syn_verus::ExprCall),
    Method(&'a syn_verus::ExprMethodCall),
}

fn get_calls_expr(expr: &syn_verus::Expr) -> Vec<CallType> {
    match expr {
        syn_verus::Expr::Call(call) => vec![CallType::Function(call)]
            .into_iter()
            .chain(call.args.iter().flat_map(get_calls_expr))
            .collect(),
        syn_verus::Expr::Array(ea) => ea.elems.iter().flat_map(get_calls_expr).collect(),
        syn_verus::Expr::Assign(asg) => {
            // XXX: Can a function call returns a left value?
            get_calls_expr(&asg.right)
        }
        syn_verus::Expr::AssignOp(asop) => {
            // XXX: Can a function call returns a left value?
            get_calls_expr(&asop.right)
        }
        syn_verus::Expr::Async(asy) => asy.block.stmts.iter().flat_map(get_calls_stmt).collect(),
        syn_verus::Expr::Await(aw) => get_calls_expr(&aw.base),
        syn_verus::Expr::Binary(b) => {
            get_calls_expr(&b.left).into_iter().chain(get_calls_expr(&b.right)).collect()
        }
        syn_verus::Expr::Block(bl) => bl.block.stmts.iter().flat_map(get_calls_stmt).collect(),
        syn_verus::Expr::Box(bx) => get_calls_expr(&bx.expr),
        syn_verus::Expr::Break(br) => br.expr.as_ref().map_or(vec![], |expr| get_calls_expr(expr)),
        syn_verus::Expr::Cast(c) => get_calls_expr(&c.expr),
        syn_verus::Expr::Closure(cl) => get_calls_expr(&cl.body),
        // syn_verus::Expr::Continue(co) => {}
        syn_verus::Expr::Field(f) => get_calls_expr(&f.base),
        syn_verus::Expr::ForLoop(fl) => get_calls_expr(&fl.expr)
            .into_iter()
            .chain(fl.body.stmts.iter().flat_map(get_calls_stmt))
            .collect(),
        syn_verus::Expr::Group(g) => get_calls_expr(&g.expr),
        syn_verus::Expr::If(i) => get_calls_expr(&i.cond)
            .into_iter()
            .chain(i.then_branch.stmts.iter().map(|stmt| get_calls_stmt(stmt)).flatten())
            .chain(i.else_branch.as_ref().map_or(vec![], |(_, eexpr)| get_calls_expr(&*eexpr)))
            .collect(),
        syn_verus::Expr::Index(i) => {
            get_calls_expr(&i.expr).into_iter().chain(get_calls_expr(&i.index)).collect()
        }
        syn_verus::Expr::Let(l) => get_calls_expr(&l.expr),
        // syn_verus::Expr::Lit(l) => {}
        syn_verus::Expr::Loop(l) => l.body.stmts.iter().flat_map(get_calls_stmt).collect(),
        // syn_verus::Expr::Macro(m) => {}
        syn_verus::Expr::Match(m) => get_calls_expr(&m.expr)
            .into_iter()
            .chain(
                m.arms
                    .iter()
                    .map(|arm| {
                        arm.guard
                            .as_ref()
                            .map_or(vec![], |(_, gexpr)| get_calls_expr(&*gexpr))
                            .into_iter()
                            .chain(get_calls_expr(&arm.body))
                    })
                    .flatten(),
            )
            .collect(),
        syn_verus::Expr::MethodCall(m) => {
            let mut calls = get_calls_expr(&m.receiver);
            calls.push(CallType::Method(m));
            calls.into_iter().chain(m.args.iter().flat_map(get_calls_expr)).collect::<Vec<_>>()
        }
        syn_verus::Expr::Paren(p) => get_calls_expr(&p.expr),
        // syn_verus::Expr::Path(p) => {}
        syn_verus::Expr::Range(r) => r
            .from
            .as_ref()
            .map_or(vec![], |expr| get_calls_expr(expr))
            .into_iter()
            .chain(r.to.as_ref().map_or(vec![], |expr| get_calls_expr(expr)))
            .collect(),
        syn_verus::Expr::Reference(r) => get_calls_expr(&r.expr),
        syn_verus::Expr::Repeat(r) => {
            get_calls_expr(&r.expr).into_iter().chain(get_calls_expr(&r.len)).collect()
        }
        syn_verus::Expr::Return(r) => r.expr.as_ref().map_or(vec![], |expr| get_calls_expr(expr)),
        syn_verus::Expr::Struct(s) => s
            .fields
            .iter()
            .flat_map(|field| get_calls_expr(&field.expr))
            .collect::<Vec<_>>()
            .into_iter()
            .chain(s.rest.as_ref().map_or(vec![], |r| get_calls_expr(&*r)))
            .collect(),
        syn_verus::Expr::Try(t) => get_calls_expr(&t.expr),
        syn_verus::Expr::TryBlock(t) => t.block.stmts.iter().flat_map(get_calls_stmt).collect(),
        syn_verus::Expr::Tuple(t) => t.elems.iter().flat_map(get_calls_expr).collect(),
        // syn_verus::Expr::Type(t) => {}
        syn_verus::Expr::Unary(u) => get_calls_expr(&u.expr),
        syn_verus::Expr::Unsafe(_) => {
            // XXX: throw an error?
            vec![]
        }
        // syn_verus::Expr::Verbatim(v) => {}
        syn_verus::Expr::While(w) => get_calls_expr(&w.cond)
            .into_iter()
            .chain(w.body.stmts.iter().flat_map(get_calls_stmt))
            .collect(),
        syn_verus::Expr::Yield(y) => y.expr.as_ref().map_or(vec![], |expr| get_calls_expr(expr)),
        _ => vec![],
    }
}

fn get_calls_stmt(stmt: &syn_verus::Stmt) -> Vec<CallType> {
    match stmt {
        syn_verus::Stmt::Expr(e) => get_calls_expr(e),
        syn_verus::Stmt::Local(l) => {
            l.init.as_ref().map_or(vec![], |(_, expr)| get_calls_expr(&*expr))
        }
        syn_verus::Stmt::Item(i) => get_calls_item(i),
        syn_verus::Stmt::Semi(e, _) => get_calls_expr(e),
    }
}

fn get_calls_item(item: &syn_verus::Item) -> Vec<CallType> {
    match item {
        syn_verus::Item::Fn(f) => f.block.stmts.iter().flat_map(get_calls_stmt).collect(),
        syn_verus::Item::Const(c) => c.expr.as_ref().map_or(vec![], |expr| get_calls_expr(expr)),
        syn_verus::Item::Static(s) => s.expr.as_ref().map_or(vec![], |expr| get_calls_expr(expr)),
        _ => vec![],
    }
}

pub fn get_calls_at(
    filepath: &PathBuf,
    ranges: Option<Vec<RangeInclusive<usize>>>,
) -> Result<Vec<serde_json::Value>, Error> {
    fextract_verus_macro(filepath).and_then(|(files, _)| {
        let mut objs: Vec<serde_json::Value> = Vec::new();

        for file in files {
            let calls = file
                .items
                .iter()
                .flat_map(get_calls_item)
                .filter(|call| {
                    if let Some(ranges) = &ranges {
                        let line = match call {
                            CallType::Function(f) => f.func.span().start().line,
                            CallType::Method(m) => m.method.span().start().line,
                        };

                        ranges.iter().any(|range| range.contains(&line))
                    } else {
                        true
                    }
                })
                .collect::<Vec<_>>();

            for call in calls {
                let ret = match call {
                    CallType::Function(f) => {
                        json!({
                            "func": f.func.to_token_stream().to_string(),
                            "args": arg_list_to_string(&f.args),
                            "line": f.func.span().start().line,
                        })
                    }
                    CallType::Method(m) => {
                        json!({
                            "func": m.method.to_token_stream().to_string(),
                            "args": arg_list_to_string(&m.args),
                            "line": m.method.span().start().line,
                        })
                    }
                };
                objs.push(ret);
            }
        }

        Ok(objs)
    })
}

pub enum Loc {
    Line(usize),
    Offset(usize),
}

fn line_in_span(span: &proc_macro2::Span, line: usize) -> bool {
    span.start().line <= line && span.end().line >= line
}

fn offset_in_span(span: &proc_macro2::Span, offset: usize) -> bool {
    span.byte_range().contains(&offset)
}

fn func_in_range(func: &syn_verus::ItemFn, loc: &Loc) -> bool {
    match loc {
        Loc::Line(l) => line_in_span(&func.block.span(), *l) || line_in_span(&func.sig.span(), *l),
        Loc::Offset(o) => {
            offset_in_span(&func.block.span(), *o) || offset_in_span(&func.sig.span(), *o)
        }
    }
}

fn get_func_at_item(item: &syn_verus::Item, loc: &Loc) -> Option<String> {
    match item {
        syn_verus::Item::Fn(f) => Some(f.sig.ident.to_string()).filter(|_| func_in_range(f, loc)),
        _ => None,
    }
}

pub fn get_func_at(
    filepath: &PathBuf,
    line: Option<usize>,
    offset: Option<usize>,
) -> Result<Vec<String>, Error> {
    fextract_verus_macro(filepath).and_then(|(files, _)| {
        let loc = if let Some(line) = line {
            Loc::Line(line)
        } else if let Some(offset) = offset {
            Loc::Offset(offset)
        } else {
            return Err(Error::NotFound("line or offset".to_string()));
        };

        Ok(files
            .iter()
            .flat_map(|file| &file.items)
            .find_map(|item| get_func_at_item(item, &loc))
            .map_or_else(|| Vec::new(), |func| vec![func]))
    })
}

fn extract_asserts_expr(expr: &syn_verus::Expr) -> Vec<&syn_verus::Assert> {
    match expr {
        syn_verus::Expr::Block(bl) => {
            bl.block.stmts.iter().flat_map(extract_asserts_stmt).collect()
        }
        syn_verus::Expr::If(i) => i
            .then_branch
            .stmts
            .iter()
            .flat_map(extract_asserts_stmt)
            .chain(
                i.else_branch.as_ref().map_or(vec![], |(_, eexpr)| extract_asserts_expr(&*eexpr)),
            )
            .collect(),
        syn_verus::Expr::Match(m) => m
            .arms
            .iter()
            .flat_map(|arm| {
                arm.guard
                    .as_ref()
                    .map_or(vec![], |(_, gexpr)| extract_asserts_expr(&*gexpr))
                    .into_iter()
                    .chain(extract_asserts_expr(&arm.body))
            })
            .collect(),
        syn_verus::Expr::While(w) => w.body.stmts.iter().flat_map(extract_asserts_stmt).collect(),
        syn_verus::Expr::ForLoop(fl) => {
            fl.body.stmts.iter().flat_map(extract_asserts_stmt).collect()
        }
        syn_verus::Expr::Loop(l) => l.body.stmts.iter().flat_map(extract_asserts_stmt).collect(),
        syn_verus::Expr::TryBlock(t) => {
            t.block.stmts.iter().flat_map(extract_asserts_stmt).collect()
        }
        syn_verus::Expr::Assert(a) => {
            vec![a]
        }
        _ => vec![],
    }
}

fn extract_asserts_stmt(stmt: &syn_verus::Stmt) -> Vec<&syn_verus::Assert> {
    match stmt {
        syn_verus::Stmt::Expr(e) => extract_asserts_expr(e),
        syn_verus::Stmt::Local(_l) => {
            //l.init.as_ref().map_or(vec![], |(_, expr)| extract_asserts_expr(&*expr))
            vec![]
        }
        syn_verus::Stmt::Item(_i) => {
            //extract_asserts_item(i)
            vec![]
        }
        syn_verus::Stmt::Semi(e, _) => extract_asserts_expr(e),
    }
}

fn extract_invariant_expr(expr: &syn_verus::Expr) -> Vec<&syn_verus::Expr> {
    match expr {
        syn_verus::Expr::Block(bl) => {
            bl.block.stmts.iter().flat_map(extract_invariant_stmt).collect()
        }
        syn_verus::Expr::If(i) => i
            .then_branch
            .stmts
            .iter()
            .flat_map(extract_invariant_stmt)
            .chain(
                i.else_branch.as_ref().map_or(vec![], |(_, eexpr)| extract_invariant_expr(&*eexpr)),
            )
            .collect(),
        syn_verus::Expr::Match(m) => m
            .arms
            .iter()
            .flat_map(|arm| {
                arm.guard
                    .as_ref()
                    .map_or(vec![], |(_, gexpr)| extract_invariant_expr(&*gexpr))
                    .into_iter()
                    .chain(extract_invariant_expr(&arm.body))
            })
            .collect(),
        syn_verus::Expr::While(w) => w.invariant.as_ref().map_or(vec![], |i| {
            i.exprs
                .exprs
                .iter()
                .chain(w.body.stmts.iter().flat_map(extract_invariant_stmt))
                .collect()
        }),
        syn_verus::Expr::ForLoop(fl) => fl.invariant.as_ref().map_or(vec![], |i| {
            i.exprs
                .exprs
                .iter()
                .chain(fl.body.stmts.iter().flat_map(extract_invariant_stmt))
                .collect()
        }),
        syn_verus::Expr::Loop(l) => l.invariant.as_ref().map_or(vec![], |i| {
            i.exprs
                .exprs
                .iter()
                .chain(l.body.stmts.iter().flat_map(extract_invariant_stmt))
                .collect()
        }),
        syn_verus::Expr::TryBlock(t) => {
            t.block.stmts.iter().flat_map(extract_invariant_stmt).collect()
        }
        _ => vec![],
    }
}

fn extract_invariant_stmt(stmt: &syn_verus::Stmt) -> Vec<&syn_verus::Expr> {
    match stmt {
        syn_verus::Stmt::Expr(e) => extract_invariant_expr(e),
        syn_verus::Stmt::Local(_l) => {
            //l.init.as_ref().map_or(vec![], |(_, expr)| extract_asserts_expr(&*expr))
            vec![]
        }
        syn_verus::Stmt::Item(_i) => {
            //extract_asserts_item(i)
            vec![]
        }
        syn_verus::Stmt::Semi(e, _) => extract_invariant_expr(e),
    }
}

enum GhostVariant<'a> {
    Invariant(&'a syn_verus::Expr),
    Assert(&'a syn_verus::Assert),
}

fn extract_invariant_asserts_stmt(stmt: &syn_verus::Stmt) -> Vec<GhostVariant> {
    extract_invariant_stmt(stmt)
        .into_iter()
        .map(GhostVariant::Invariant)
        .chain(extract_asserts_stmt(stmt).into_iter().map(GhostVariant::Assert))
        .collect()
}

pub fn fdetect_nl(filepath: &PathBuf) -> Result<Vec<(&str,(usize, usize))>, Error> {
    fextract_verus_macro(filepath).and_then(|(files, _)| {
        Ok(files
            .iter()
            .map(|file| {
                file.items.iter().flat_map(|items| {
                    match items {
                        // TODO: deal with method
                        syn_verus::Item::Fn(f) => f
                            .block
                            .stmts
                            .iter()
                            .flat_map(extract_invariant_asserts_stmt)
                            .filter(|ea| //detect_non_linear_assert_expr(&asrt.expr)
                                match ea {
                                    GhostVariant::Invariant(i) => detect_non_linear_assert_expr(i),
                                    GhostVariant::Assert(a) => detect_non_linear_assert_expr(&a.expr),
                                })
                            .map(|a| match a {
                                GhostVariant::Invariant(i) => {
                                    ("invariant", (i.span().start().line, i.span().end().line))
                                }
                                GhostVariant::Assert(a) => {
                                    ("assert", (a.span().start().line, a.span().end().line))
                                }
                            })
                            .collect::<Vec<_>>(),
                        _ => vec![],
                    }
                })
            })
            .flatten()
            .collect::<Vec<_>>())
    })
}

pub fn fget_target(filepath: &PathBuf) -> Result<Vec<FnMethod>, Error> {
    let files = fextract_verus_macro(filepath)?; // Assuming this function is defined elsewhere and returns Result<(Vec<syn_verus::File>, _), Error>
    let mut ret = Vec::new();

    for file in files.0 {
        for item in file.items {
            match item {
                syn_verus::Item::Fn(f) => {
                    if func_is_target(&f) {
                        ret.push(FnMethod::Fn(f.clone()));
                    }
                }
                syn_verus::Item::Impl(i) => {
                    for item in &i.items {
                        if let syn_verus::ImplItem::Method(m) = item {
                            if method_is_target(&m) {
                                ret.push(FnMethod::Method(
                                    syn_verus::ItemImpl { items: vec![], ..i.clone() },
                                    m.clone(),
                                ));
                            }
                        }
                    }
                }
                _ => {}
            }
        }
    }

    Ok(ret)
}
