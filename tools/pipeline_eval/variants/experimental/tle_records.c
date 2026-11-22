/* Fast path for canonical ASCII 3LE archives. Other layouts use the Python reader. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>

static int next_line(const char **cursor, const char *end, const char **line, size_t *length) {
    const char *start = *cursor;
    if (start == end) return 0;
    const char *newline = memchr(start, '\n', (size_t)(end - start));
    const char *stop = newline ? newline : end;
    *cursor = newline ? newline + 1 : end;
    if (stop > start && stop[-1] == '\r') stop--;
    *line = start;
    *length = (size_t)(stop - start);
    return 1;
}

static int valid_line(const char *s, size_t length, char prefix) {
    if (length != 69 || s[0] != prefix || s[1] != ' ') return 0;
    unsigned total = 0;
    for (size_t i = 0; i < 68; i++) {
        unsigned ch = (unsigned char)s[i];
        if (ch < 32 || ch > 126) return 0;
        total += ch >= '0' && ch <= '9' ? ch - '0' : (unsigned)(ch == '-');
    }
    return s[68] == '0' + (int)(total % 10);
}

static PyObject *records(PyObject *self, PyObject *args) {
    PyObject *text, *record_type;
    if (!PyArg_ParseTuple(args, "UO", &text, &record_type)) return NULL;
    if (!PyUnicode_IS_ASCII(text)) Py_RETURN_NONE;
    Py_ssize_t size;
    const char *cursor = PyUnicode_AsUTF8AndSize(text, &size);
    if (cursor == NULL) return NULL;
    const char *end = cursor + size;
    PyObject *rows = PyList_New(0);
    if (rows == NULL) return NULL;
    while (cursor < end) {
        const char *name, *first, *second;
        size_t nn, n1, n2;
        if (!next_line(&cursor, end, &name, &nn) || nn <= 2 || name[0] != '0' || name[1] != ' '
                || !next_line(&cursor, end, &first, &n1) || !valid_line(first, n1, '1')
                || !next_line(&cursor, end, &second, &n2) || !valid_line(second, n2, '2')
                || memcmp(first + 2, second + 2, 5) != 0) goto fallback;
        name += 2;
        nn -= 2;
        if (name[0] == ' ' || name[nn - 1] == ' ') goto fallback;
        for (size_t i = 0; i < nn; i++) {
            if ((unsigned char)name[i] < 32 || (unsigned char)name[i] > 126) goto fallback;
        }
        long number = 0;
        int start = 2;
        if (first[2] >= 'A' && first[2] <= 'Z' && first[2] != 'I' && first[2] != 'O') {
            number = first[2] - 'A' + 10 - (first[2] > 'I') - (first[2] > 'O');
            start = 3;
        }
        for (int i = start; i < 7; i++) {
            if (first[i] < '0' || first[i] > '9') goto fallback;
            number = number * 10 + first[i] - '0';
        }
        PyObject *row = PyObject_CallFunction(record_type, "s#ls#s#", name, (Py_ssize_t)nn,
                                              number, first, (Py_ssize_t)n1, second, (Py_ssize_t)n2);
        if (row == NULL) goto error;
        int added = PyList_Append(rows, row);
        Py_DECREF(row);
        if (added < 0) goto error;
    }
    if (PyList_GET_SIZE(rows) == 0) goto fallback;
    PyObject *result = PyList_AsTuple(rows);
    Py_DECREF(rows);
    return result;
fallback:
    Py_DECREF(rows);
    Py_RETURN_NONE;
error:
    Py_DECREF(rows);
    return NULL;
}

static PyMethodDef methods[] = {
    {"records", records, METH_VARARGS, "Read canonical 3LE records, or return None."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_leo_tle_records", NULL, -1, methods};
PyMODINIT_FUNC PyInit__leo_tle_records(void) { return PyModule_Create(&module); }
