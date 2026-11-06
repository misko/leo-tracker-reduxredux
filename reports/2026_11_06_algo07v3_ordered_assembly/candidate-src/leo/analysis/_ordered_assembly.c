#define PY_SSIZE_T_CLEAN
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <Python.h>
#include <numpy/arrayobject.h>
#include "_ordered_scatter.c"

static PyObject *scatter(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *objects[5];
    PyArrayObject *arrays[5];
    if (!PyArg_ParseTuple(args, "OOOOO", &objects[0], &objects[1], &objects[2],
                          &objects[3], &objects[4])) return NULL;
    for (int i = 0; i < 5; ++i) {
        int type = (i == 1 || i == 2) ? NPY_INTP : NPY_DOUBLE;
        if (!PyArray_Check(objects[i])) {
            PyErr_SetString(PyExc_ValueError, "ndarrays required");
            return NULL;
        }
        arrays[i] = (PyArrayObject *)objects[i];
        if (PyArray_NDIM(arrays[i]) != 1 || PyArray_TYPE(arrays[i]) != type ||
            !PyArray_ISCARRAY_RO(arrays[i]) || !PyArray_ISNOTSWAPPED(arrays[i])) {
            PyErr_SetString(PyExc_ValueError, "Native contiguous aligned vectors required");
            return NULL;
        }
    }
    if (!PyArray_ISWRITEABLE(arrays[0]) ||
        PyArray_SIZE(arrays[1]) != PyArray_SIZE(arrays[2]) ||
        PyArray_SIZE(arrays[1]) != PyArray_SIZE(arrays[4])) {
        PyErr_SetString(PyExc_ValueError, "Writable output and matching index/group/value lengths required");
        return NULL;
    }
    uintptr_t begin = (uintptr_t)PyArray_DATA(arrays[0]);
    uintptr_t end = begin + PyArray_NBYTES(arrays[0]);
    for (int i = 1; i < 5; ++i) {
        uintptr_t input = (uintptr_t)PyArray_DATA(arrays[i]);
        uintptr_t input_end = input + PyArray_NBYTES(arrays[i]);
        if (begin < input_end && input < end) {
            PyErr_SetString(PyExc_ValueError, "Output must not alias inputs");
            return NULL;
        }
    }
    int status = ordered_scatter(
        (double *)PyArray_DATA(arrays[0]), PyArray_SIZE(arrays[0]),
        (intptr_t *)PyArray_DATA(arrays[1]), (intptr_t *)PyArray_DATA(arrays[2]),
        (double *)PyArray_DATA(arrays[3]), PyArray_SIZE(arrays[3]),
        (double *)PyArray_DATA(arrays[4]), PyArray_SIZE(arrays[4]));
    if (status) {
        PyErr_SetString(PyExc_ValueError, "Index or group outside bounds");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"scatter", scatter, METH_VARARGS, "Ordered separate multiply and scatter add."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_ordered_assembly", NULL, -1, methods,
    NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__ordered_assembly(void) {
    import_array();
    return PyModule_Create(&module);
}
