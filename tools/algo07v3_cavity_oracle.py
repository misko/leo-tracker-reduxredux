"""Frozen cavity mathematical bodies with explicit inputs; external oracle only."""
import ast
import inspect


def numerical_one(module, context, nominations=None):
    function = ast.parse(inspect.getsource(module.one)).body[0]
    block = next(n for n in function.body if isinstance(n, ast.Try))

    class ExplicitInputs(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id in ('d', 'nom') for t in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == 'print':
                    return None
                if (isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr == 'print_exc'):
                    return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            node.keywords = [k for k in node.keywords if k.arg != 'nomination_sha256']
            return self.generic_visit(node)

    block = ExplicitInputs().visit(block)
    block.finalbody = []
    namespace = dict(module.one.__globals__, d=context, nom=nominations, case=context['case'])
    tree = ast.Module(body=[block], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), inspect.getsourcefile(module), 'exec'), namespace)
    return namespace['result']


def reference_nominate_families(context):
    import probe_ds23_family_cavity_nominations as original

    return numerical_one(original, context)


def reference_cavity_policy(context, nominations):
    import fast_graph_engine as engine
    import probe_ds23_family_cavity_position as original

    if nominations['status'] != 'complete':
        return nominations
    result = numerical_one(original, context, nominations)
    function = ast.parse(inspect.getsource(engine.cavity)).body[0]
    adoption = next(n for n in function.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.BoolOp))

    class NoPublication(ast.NodeTransformer):
        def visit_Expr(self, node):
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == 'write'):
                return None
            return self.generic_visit(node)

    namespace = dict(engine.cavity.__globals__, result=result)
    tree = ast.Module(body=[NoPublication().visit(adoption)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), inspect.getsourcefile(engine), 'exec'), namespace)
    return namespace['result']
