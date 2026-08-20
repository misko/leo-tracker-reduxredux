#define PY_SSIZE_T_CLEAN
#define NPY_NO_DEPRECATED_API NPY_2_0_API_VERSION

#include <Python.h>
#include <complex.h>
#include <math.h>
#include <numpy/arrayobject.h>


static PyObject *folded_anchor_scores(PyObject *self, PyObject *args) {
    PyObject *derotated_object;
    PyObject *template_object;
    PyObject *local_starts_object;
    PyObject *local_stops_object;
    PyObject *frame_offsets_object;
    PyObject *power_prefix_object;
    int epoch_count;
    (void)self;

    if (!PyArg_ParseTuple(
            args,
            "OOOOOOi",
            &derotated_object,
            &template_object,
            &local_starts_object,
            &local_stops_object,
            &frame_offsets_object,
            &power_prefix_object,
            &epoch_count)) {
        return NULL;
    }
    if (epoch_count <= 0) {
        PyErr_SetString(PyExc_ValueError, "epoch_count must be positive");
        return NULL;
    }

    PyArrayObject *derotated = (PyArrayObject *)PyArray_FROM_OTF(
        derotated_object, NPY_COMPLEX128, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *template = (PyArrayObject *)PyArray_FROM_OTF(
        template_object, NPY_COMPLEX128, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *local_starts = (PyArrayObject *)PyArray_FROM_OTF(
        local_starts_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *local_stops = (PyArrayObject *)PyArray_FROM_OTF(
        local_stops_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *frame_offsets = (PyArrayObject *)PyArray_FROM_OTF(
        frame_offsets_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *power_prefix = (PyArrayObject *)PyArray_FROM_OTF(
        power_prefix_object, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    if (derotated == NULL || template == NULL || local_starts == NULL ||
        local_stops == NULL || frame_offsets == NULL || power_prefix == NULL) {
        Py_XDECREF(derotated);
        Py_XDECREF(template);
        Py_XDECREF(local_starts);
        Py_XDECREF(local_stops);
        Py_XDECREF(frame_offsets);
        Py_XDECREF(power_prefix);
        return NULL;
    }

    const npy_intp sample_count = PyArray_SIZE(derotated);
    const npy_intp template_count = PyArray_SIZE(template);
    const npy_intp symbol_count = PyArray_SIZE(local_starts);
    if (PyArray_NDIM(derotated) != 1 || PyArray_NDIM(template) != 1 ||
        PyArray_NDIM(local_starts) != 1 || PyArray_NDIM(local_stops) != 1 ||
        PyArray_NDIM(frame_offsets) != 1 || PyArray_NDIM(power_prefix) != 1 ||
        PyArray_SIZE(local_stops) != symbol_count ||
        PyArray_SIZE(power_prefix) != sample_count + 1) {
        PyErr_SetString(PyExc_ValueError, "native folded-anchor geometry is invalid");
        Py_DECREF(derotated);
        Py_DECREF(template);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }

    npy_intp output_shape[1] = {(npy_intp)epoch_count};
    PyArrayObject *output = (PyArrayObject *)PyArray_ZEROS(1, output_shape, NPY_DOUBLE, 0);
    npy_int32 *support = PyMem_Calloc((size_t)epoch_count, sizeof(npy_int32));
    if (output == NULL || support == NULL) {
        PyErr_NoMemory();
        Py_XDECREF(output);
        PyMem_Free(support);
        Py_DECREF(derotated);
        Py_DECREF(template);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }

    const npy_cdouble *samples = (const npy_cdouble *)PyArray_DATA(derotated);
    const npy_cdouble *references = (const npy_cdouble *)PyArray_DATA(template);
    const npy_intp *starts = (const npy_intp *)PyArray_DATA(local_starts);
    const npy_intp *stops = (const npy_intp *)PyArray_DATA(local_stops);
    const npy_intp *offsets = (const npy_intp *)PyArray_DATA(frame_offsets);
    const npy_intp offset_count = PyArray_SIZE(frame_offsets);
    const double *prefix = (const double *)PyArray_DATA(power_prefix);
    double *scores = (double *)PyArray_DATA(output);

    int invalid_geometry = 0;
    Py_BEGIN_ALLOW_THREADS
    for (npy_intp symbol = 0; symbol < symbol_count && !invalid_geometry; ++symbol) {
        const npy_intp local_start = starts[symbol];
        const npy_intp local_stop = stops[symbol];
        const npy_intp reference_count = local_stop - local_start;
        if (local_start < 0 || local_stop > template_count || reference_count <= 0 ||
            reference_count > sample_count) {
            invalid_geometry = 1;
            break;
        }
        double reference_energy = 0.0;
        for (npy_intp index = local_start; index < local_stop; ++index) {
            const double real = creal(references[index]);
            const double imag = cimag(references[index]);
            reference_energy += real * real + imag * imag;
        }
        const npy_intp valid_position_count = sample_count - reference_count + 1;
        for (npy_intp frame = 0; frame < offset_count; ++frame) {
            const npy_intp base = local_start + offsets[frame];
            if (base >= valid_position_count) {
                break;
            }
            npy_intp valid_epochs = valid_position_count - base;
            if (valid_epochs > epoch_count) {
                valid_epochs = epoch_count;
            }
            for (npy_intp epoch = 0; epoch < valid_epochs; ++epoch) {
                const npy_intp position = base + epoch;
                double correlation_real = 0.0;
                double correlation_imag = 0.0;
                for (npy_intp index = 0; index < reference_count; ++index) {
                    const npy_cdouble received = samples[position + index];
                    const npy_cdouble reference = references[local_start + index];
                    const double received_real = creal(received);
                    const double received_imag = cimag(received);
                    const double reference_real = creal(reference);
                    const double reference_imag = cimag(reference);
                    correlation_real +=
                        received_real * reference_real + received_imag * reference_imag;
                    correlation_imag +=
                        received_imag * reference_real - received_real * reference_imag;
                }
                double received_energy =
                    prefix[position + reference_count] - prefix[position];
                if (received_energy < 0.0) {
                    received_energy = 0.0;
                }
                const double denominator = sqrt(reference_energy * received_energy);
                if (denominator > 0.0) {
                    scores[epoch] += hypot(correlation_real, correlation_imag) / denominator;
                }
                support[epoch] += 1;
            }
        }
    }
    if (!invalid_geometry) {
        for (int epoch = 0; epoch < epoch_count; ++epoch) {
            scores[epoch] = support[epoch] > 0 ? scores[epoch] / support[epoch] : 0.0;
        }
    }
    Py_END_ALLOW_THREADS

    PyMem_Free(support);
    Py_DECREF(derotated);
    Py_DECREF(template);
    Py_DECREF(local_starts);
    Py_DECREF(local_stops);
    Py_DECREF(frame_offsets);
    Py_DECREF(power_prefix);
    if (invalid_geometry) {
        Py_DECREF(output);
        PyErr_SetString(PyExc_ValueError, "native folded-anchor indexes are invalid");
        return NULL;
    }
    return (PyObject *)output;
}


static PyMethodDef module_methods[] = {
    {
        "folded_anchor_scores",
        folded_anchor_scores,
        METH_VARARGS,
        "Compute folded anchor scores with a fused native loop.",
    },
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_definition = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "_native_acquisition",
    .m_doc = "Native numerical kernels paired with Python reference implementations.",
    .m_size = -1,
    .m_methods = module_methods,
};


PyMODINIT_FUNC PyInit__native_acquisition(void) {
    import_array();
    return PyModule_Create(&module_definition);
}
