"""Build an isolated FP64 sparse-column kernel with the original arithmetic loops."""

import argparse
import json
import shlex
import shutil
import subprocess
import sysconfig
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files

WRAPPER = '''static PyObject *folded_anchor_score_columns(PyObject *self, PyObject *args) {
    if (PyTuple_Size(args) != 10) {
        PyErr_SetString(PyExc_TypeError, "sparse columns require ten arguments");
        return NULL;
    }
    PyObject *object = PyTuple_GetItem(args, 9);
    if (!PyArray_Check(object) || PyArray_TYPE((PyArrayObject *)object) != NPY_INTP ||
            PyArray_NDIM((PyArrayObject *)object) != 1 ||
            PyArray_SIZE((PyArrayObject *)object) <= 0 ||
            PyArray_SIZE((PyArrayObject *)object) > INT_MAX) {
        PyErr_SetString(PyExc_ValueError, "columns must be a nonempty intp vector");
        return NULL;
    }
    PyArrayObject *columns = (PyArrayObject *)PyArray_FROM_OTF(
        object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    if (!columns) return NULL;
    PyObject *original_args = PyTuple_GetSlice(args, 0, 9);
    if (!original_args) { Py_DECREF(columns); return NULL; }
    PyObject *result = folded_anchor_score_grid_with_backend(
        self, original_args, GRID_BACKEND_AUTO, (const npy_intp *)PyArray_DATA(columns),
        (int)PyArray_SIZE(columns));
    Py_DECREF(original_args);
    Py_DECREF(columns);
    return result;
}

'''


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Unknown sparse-kernel source layout: ' + before[:60])
    return text.replace(before, after)


def transform(source, grid):
    source = replace_once(source, '#include <math.h>', '#include <math.h>\n#include <limits.h>')
    source = replace_once(source, '    const npy_intp *offsets;',
                          '    const npy_intp *offsets;\n    const npy_intp *epoch_indices;')
    source = replace_once(source, '        GridBackend backend) {',
                          '        GridBackend backend, const npy_intp *epoch_indices,\n'
                          '        int column_count) {')
    start = source.index('static PyObject *folded_anchor_score_grid_with_backend(')
    split = source.index('    PyArrayObject *samples_array =', start)
    validation = '''    if (epoch_indices != NULL) {
        if (column_count <= 0) {
            PyErr_SetString(PyExc_ValueError, "empty sparse column request");
            return NULL;
        }
        for (int i = 0; i < column_count; ++i) {
            if (epoch_indices[i] < 0 || epoch_indices[i] >= epoch_count) {
                PyErr_SetString(PyExc_ValueError, "sparse column outside original epoch grid");
                return NULL;
            }
        }
        epoch_count = column_count;
    }

'''
    source = source[:split] + validation + source[split:]
    source = replace_once(source, '        .offsets = offsets,',
                          '        .offsets = offsets,\n        .epoch_indices = epoch_indices,')
    for backend in ('AUTO', 'PORTABLE', 'AVX2_FMA', 'AVX2_FMA_REGISTER_ACCUMULATION'):
        source = replace_once(source, 'GRID_BACKEND_' + backend + ');',
                              'GRID_BACKEND_' + backend + ', NULL, 0);')
    source = replace_once(source, 'static PyMethodDef module_methods[] = {',
                          WRAPPER + 'static PyMethodDef module_methods[] = {\n'
                          '    {"folded_anchor_score_columns", folded_anchor_score_columns,\n'
                          '     METH_VARARGS, "Evaluate selected FP64 columns in one call."},')
    grid = replace_once(grid, '            if (valid_epochs > kernel->epoch_count) {',
                        '            if (kernel->epoch_indices != NULL ||\n'
                        '                    valid_epochs > kernel->epoch_count) {')
    grid = replace_once(grid, '                const npy_intp position = base + epoch;',
                        '                const npy_intp selected_epoch = '
                        'kernel->epoch_indices != NULL\n'
                        '                    ? kernel->epoch_indices[epoch] : epoch;\n'
                        '                if (selected_epoch >= '
                        'valid_position_count - base) continue;\n'
                        '                const npy_intp position = base + selected_epoch;')
    return source, grid


def build(base, pin, output):
    import numpy

    base, output = base.resolve(strict=True), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research directory required')
    manifest = verify(base, pin)
    prefix = 'src/leo/analysis/starlink/'
    names = [prefix+n for n in ('_native_acquisition.c', '_native_acquisition_grid.inc')]
    changed = transform(*[(base/n).read_text() for n in names])
    output.mkdir(parents=True)
    for name in manifest['files_sha256']:
        dest = output/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base/name, dest)
    for name, source in zip(names, changed, strict=True):
        (output/name).write_text(source)
    extension = prefix + '_native_acquisition' + sysconfig.get_config_var('EXT_SUFFIX')
    command = [*shlex.split(sysconfig.get_config_var('CC')), '-shared', '-fPIC', '-O3',
               '-fno-math-errno', '-Wall', '-Wextra',
               '-I'+sysconfig.get_path('include'), '-I'+numpy.get_include(),
               str(output/names[0]), str(output/prefix/'fast_scan_fold.c'),
               '-lm', '-o', str(output/extension)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    inventory = {n: digest(output/n) for n in manifest['files_sha256']}
    differences = sorted(n for n in inventory if inventory[n] != manifest['files_sha256'][n])
    if differences != sorted([*names, extension]):
        raise ValueError('Unexpected sparse prototype changes')
    verify(base, pin)
    verify_files(output, inventory)
    receipt = dict(base=str(base), base_pin=pin, candidate=str(output),
                   files_sha256=inventory, changes=differences, compile_command=command,
                   compiler=subprocess.check_output(command[:1]+['--version'], text=True),
                   compiler_stderr=result.stderr, builder_sha256=digest(Path(__file__)),
                   production_modified=False, qualification='research sparse FP64 probe')
    (output/'sparse-probe.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return dict(candidate=str(output), changes=differences)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.pin, args.output)))
