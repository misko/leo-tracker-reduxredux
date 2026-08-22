#define PY_SSIZE_T_CLEAN
#define NPY_NO_DEPRECATED_API NPY_2_0_API_VERSION

#include <Python.h>
#include <complex.h>
#include <float.h>
#include <math.h>
#include <numpy/arrayobject.h>


typedef enum {
    GRID_BACKEND_AUTO = 0,
    GRID_BACKEND_PORTABLE = 1,
    GRID_BACKEND_AVX2_FMA = 2,
} GridBackend;


typedef struct {
    const npy_cdouble *samples;
    const npy_cdouble *references;
    const double *frequencies;
    const npy_intp *starts;
    const npy_intp *stops;
    const npy_intp *offsets;
    const double *prefix;
    double *scores;
    double *accumulated;
    npy_int32 *support;
    double *correlation_real;
    double *correlation_imag;
    double *rotated_real;
    double *rotated_imag;
    npy_intp sample_count;
    npy_intp cfo_count;
    npy_intp symbol_count;
    npy_intp offset_count;
    double sample_rate_hz;
    int epoch_count;
    int fast_magnitude;
    int invalid_geometry;
} FoldedAnchorGridKernel;


#define LEO_GRID_FUNCTION folded_anchor_grid_portable
#define LEO_GRID_TARGET
#include "_native_acquisition_grid.inc"
#undef LEO_GRID_FUNCTION
#undef LEO_GRID_TARGET


#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__))
#define LEO_HAS_AVX2_FMA_TARGET 1
#define LEO_GRID_FUNCTION folded_anchor_grid_avx2_fma
#define LEO_GRID_TARGET __attribute__((target("avx2,fma,tune=haswell")))
#include "_native_acquisition_grid.inc"
#undef LEO_GRID_FUNCTION
#undef LEO_GRID_TARGET
#else
#define LEO_HAS_AVX2_FMA_TARGET 0
#endif


static int avx2_fma_available(void) {
#if LEO_HAS_AVX2_FMA_TARGET
    __builtin_cpu_init();
    return __builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma");
#else
    return 0;
#endif
}


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


static PyObject *folded_anchor_score_grid_with_backend(
        PyObject *self,
        PyObject *args,
        GridBackend backend) {
    PyObject *samples_object;
    PyObject *template_object;
    PyObject *cfo_object;
    PyObject *local_starts_object;
    PyObject *local_stops_object;
    PyObject *frame_offsets_object;
    PyObject *power_prefix_object;
    double sample_rate_hz;
    int epoch_count;
    (void)self;

    if (backend == GRID_BACKEND_AVX2_FMA && !avx2_fma_available()) {
        PyErr_SetString(PyExc_RuntimeError, "AVX2/FMA native acquisition is unavailable");
        return NULL;
    }

    if (!PyArg_ParseTuple(
            args,
            "OOOOOOOdi",
            &samples_object,
            &template_object,
            &cfo_object,
            &local_starts_object,
            &local_stops_object,
            &frame_offsets_object,
            &power_prefix_object,
            &sample_rate_hz,
            &epoch_count)) {
        return NULL;
    }
    if (!isfinite(sample_rate_hz) || sample_rate_hz <= 0.0 || epoch_count <= 0) {
        PyErr_SetString(PyExc_ValueError, "sample rate and epoch count must be positive");
        return NULL;
    }

    PyArrayObject *samples_array = (PyArrayObject *)PyArray_FROM_OTF(
        samples_object, NPY_COMPLEX128, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *template = (PyArrayObject *)PyArray_FROM_OTF(
        template_object, NPY_COMPLEX128, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *cfo = (PyArrayObject *)PyArray_FROM_OTF(
        cfo_object, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *local_starts = (PyArrayObject *)PyArray_FROM_OTF(
        local_starts_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *local_stops = (PyArrayObject *)PyArray_FROM_OTF(
        local_stops_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *frame_offsets = (PyArrayObject *)PyArray_FROM_OTF(
        frame_offsets_object, NPY_INTP, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *power_prefix = (PyArrayObject *)PyArray_FROM_OTF(
        power_prefix_object, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    if (samples_array == NULL || template == NULL || cfo == NULL ||
        local_starts == NULL || local_stops == NULL || frame_offsets == NULL ||
        power_prefix == NULL) {
        Py_XDECREF(samples_array);
        Py_XDECREF(template);
        Py_XDECREF(cfo);
        Py_XDECREF(local_starts);
        Py_XDECREF(local_stops);
        Py_XDECREF(frame_offsets);
        Py_XDECREF(power_prefix);
        return NULL;
    }

    const npy_intp sample_count = PyArray_SIZE(samples_array);
    const npy_intp template_count = PyArray_SIZE(template);
    const npy_intp cfo_count = PyArray_SIZE(cfo);
    const npy_intp symbol_count = PyArray_SIZE(local_starts);
    if (PyArray_NDIM(samples_array) != 1 || PyArray_NDIM(template) != 1 ||
        PyArray_NDIM(cfo) != 1 || PyArray_NDIM(local_starts) != 1 ||
        PyArray_NDIM(local_stops) != 1 || PyArray_NDIM(frame_offsets) != 1 ||
        PyArray_NDIM(power_prefix) != 1 || cfo_count <= 0 || symbol_count <= 0 ||
        PyArray_SIZE(local_stops) != symbol_count ||
        PyArray_SIZE(power_prefix) != sample_count + 1) {
        PyErr_SetString(PyExc_ValueError, "native folded-anchor grid geometry is invalid");
        Py_DECREF(samples_array);
        Py_DECREF(template);
        Py_DECREF(cfo);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }
    if (cfo_count > NPY_MAX_INTP / epoch_count) {
        PyErr_SetString(PyExc_OverflowError, "native folded-anchor grid is too large");
        Py_DECREF(samples_array);
        Py_DECREF(template);
        Py_DECREF(cfo);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }

    npy_intp maximum_reference_count = 0;
    const npy_intp *starts = (const npy_intp *)PyArray_DATA(local_starts);
    const npy_intp *stops = (const npy_intp *)PyArray_DATA(local_stops);
    for (npy_intp symbol = 0; symbol < symbol_count; ++symbol) {
        const npy_intp reference_count = stops[symbol] - starts[symbol];
        if (starts[symbol] < 0 || stops[symbol] > template_count ||
            reference_count <= 0 || reference_count > sample_count) {
            PyErr_SetString(PyExc_ValueError, "native folded-anchor indexes are invalid");
            Py_DECREF(samples_array);
            Py_DECREF(template);
            Py_DECREF(cfo);
            Py_DECREF(local_starts);
            Py_DECREF(local_stops);
            Py_DECREF(frame_offsets);
            Py_DECREF(power_prefix);
            return NULL;
        }
        if (reference_count > maximum_reference_count) {
            maximum_reference_count = reference_count;
        }
    }
    if (maximum_reference_count > NPY_MAX_INTP / cfo_count) {
        PyErr_SetString(PyExc_OverflowError, "native folded-anchor reference grid is too large");
        Py_DECREF(samples_array);
        Py_DECREF(template);
        Py_DECREF(cfo);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }

    npy_intp output_shape[2] = {cfo_count, (npy_intp)epoch_count};
    PyArrayObject *output = (PyArrayObject *)PyArray_EMPTY(2, output_shape, NPY_DOUBLE, 0);
    const npy_intp score_count = cfo_count * epoch_count;
    const npy_intp rotated_count = cfo_count * maximum_reference_count;
    double *restrict accumulated = PyMem_Calloc((size_t)score_count, sizeof(double));
    npy_int32 *support = PyMem_Calloc((size_t)epoch_count, sizeof(npy_int32));
    double *restrict correlation_real = PyMem_Malloc((size_t)cfo_count * sizeof(double));
    double *restrict correlation_imag = PyMem_Malloc((size_t)cfo_count * sizeof(double));
    double *restrict rotated_real = PyMem_Malloc((size_t)rotated_count * sizeof(double));
    double *restrict rotated_imag = PyMem_Malloc((size_t)rotated_count * sizeof(double));
    if (output == NULL || accumulated == NULL || support == NULL ||
        correlation_real == NULL || correlation_imag == NULL ||
        rotated_real == NULL || rotated_imag == NULL) {
        PyErr_NoMemory();
        Py_XDECREF(output);
        PyMem_Free(accumulated);
        PyMem_Free(support);
        PyMem_Free(correlation_real);
        PyMem_Free(correlation_imag);
        PyMem_Free(rotated_real);
        PyMem_Free(rotated_imag);
        Py_DECREF(samples_array);
        Py_DECREF(template);
        Py_DECREF(cfo);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        return NULL;
    }

    const npy_cdouble *samples = (const npy_cdouble *)PyArray_DATA(samples_array);
    const npy_cdouble *references = (const npy_cdouble *)PyArray_DATA(template);
    const double *frequencies = (const double *)PyArray_DATA(cfo);
    const npy_intp *offsets = (const npy_intp *)PyArray_DATA(frame_offsets);
    const npy_intp offset_count = PyArray_SIZE(frame_offsets);
    const double *prefix = (const double *)PyArray_DATA(power_prefix);
    double *scores = (double *)PyArray_DATA(output);
    int invalid_frequency = 0;
    for (npy_intp frequency = 0; frequency < cfo_count; ++frequency) {
        if (!isfinite(frequencies[frequency])) {
            invalid_frequency = 1;
        }
    }
    if (invalid_frequency) {
        PyMem_Free(accumulated);
        PyMem_Free(support);
        PyMem_Free(correlation_real);
        PyMem_Free(correlation_imag);
        PyMem_Free(rotated_real);
        PyMem_Free(rotated_imag);
        Py_DECREF(samples_array);
        Py_DECREF(template);
        Py_DECREF(cfo);
        Py_DECREF(local_starts);
        Py_DECREF(local_stops);
        Py_DECREF(frame_offsets);
        Py_DECREF(power_prefix);
        Py_DECREF(output);
        PyErr_SetString(PyExc_ValueError, "native folded-anchor CFO grid contains a non-finite value");
        return NULL;
    }
    FoldedAnchorGridKernel kernel = {
        .samples = samples,
        .references = references,
        .frequencies = frequencies,
        .starts = starts,
        .stops = stops,
        .offsets = offsets,
        .prefix = prefix,
        .scores = scores,
        .accumulated = accumulated,
        .support = support,
        .correlation_real = correlation_real,
        .correlation_imag = correlation_imag,
        .rotated_real = rotated_real,
        .rotated_imag = rotated_imag,
        .sample_count = sample_count,
        .cfo_count = cfo_count,
        .symbol_count = symbol_count,
        .offset_count = offset_count,
        .sample_rate_hz = sample_rate_hz,
        .epoch_count = epoch_count,
        .fast_magnitude = 0,
        .invalid_geometry = 0,
    };

    const int use_avx2_fma =
        backend == GRID_BACKEND_AVX2_FMA ||
        (backend == GRID_BACKEND_AUTO && avx2_fma_available());
    Py_BEGIN_ALLOW_THREADS
    double maximum_sample_component = 0.0;
    double maximum_reference_component = 0.0;
    for (npy_intp index = 0; index < sample_count; ++index) {
        maximum_sample_component = fmax(
            maximum_sample_component,
            fmax(fabs(creal(samples[index])), fabs(cimag(samples[index]))));
    }
    for (npy_intp index = 0; index < template_count; ++index) {
        maximum_reference_component = fmax(
            maximum_reference_component,
            fmax(fabs(creal(references[index])), fabs(cimag(references[index]))));
    }
    const double correlation_bound =
        2.0 * maximum_reference_count * maximum_sample_component *
        maximum_reference_component;
    kernel.fast_magnitude =
        isfinite(correlation_bound) && correlation_bound <= sqrt(DBL_MAX / 2.0);
#if LEO_HAS_AVX2_FMA_TARGET
    if (use_avx2_fma) {
        folded_anchor_grid_avx2_fma(&kernel);
    } else {
        folded_anchor_grid_portable(&kernel);
    }
#else
    (void)use_avx2_fma;
    folded_anchor_grid_portable(&kernel);
#endif
    Py_END_ALLOW_THREADS

    PyMem_Free(accumulated);
    PyMem_Free(support);
    PyMem_Free(correlation_real);
    PyMem_Free(correlation_imag);
    PyMem_Free(rotated_real);
    PyMem_Free(rotated_imag);
    Py_DECREF(samples_array);
    Py_DECREF(template);
    Py_DECREF(cfo);
    Py_DECREF(local_starts);
    Py_DECREF(local_stops);
    Py_DECREF(frame_offsets);
    Py_DECREF(power_prefix);
    if (kernel.invalid_geometry) {
        Py_DECREF(output);
        PyErr_SetString(PyExc_ValueError, "native folded-anchor indexes are invalid");
        return NULL;
    }
    return (PyObject *)output;
}


static PyObject *folded_anchor_score_grid(PyObject *self, PyObject *args) {
    return folded_anchor_score_grid_with_backend(self, args, GRID_BACKEND_AUTO);
}


static PyObject *folded_anchor_score_grid_portable_py(PyObject *self, PyObject *args) {
    return folded_anchor_score_grid_with_backend(self, args, GRID_BACKEND_PORTABLE);
}


static PyObject *folded_anchor_score_grid_avx2_fma_py(PyObject *self, PyObject *args) {
    return folded_anchor_score_grid_with_backend(self, args, GRID_BACKEND_AVX2_FMA);
}


static PyObject *folded_anchor_score_grid_backend(PyObject *self, PyObject *args) {
    (void)self;
    if (!PyArg_ParseTuple(args, "")) {
        return NULL;
    }
    return PyUnicode_FromString(avx2_fma_available() ? "avx2_fma" : "portable");
}


static PyMethodDef module_methods[] = {
    {
        "folded_anchor_scores",
        folded_anchor_scores,
        METH_VARARGS,
        "Compute folded anchor scores with a fused native loop.",
    },
    {
        "folded_anchor_score_grid",
        folded_anchor_score_grid,
        METH_VARARGS,
        "Compute a complete folded-anchor CFO grid with runtime native dispatch.",
    },
    {
        "folded_anchor_score_grid_portable",
        folded_anchor_score_grid_portable_py,
        METH_VARARGS,
        "Compute a complete folded-anchor CFO grid with the portable kernel.",
    },
    {
        "folded_anchor_score_grid_avx2_fma",
        folded_anchor_score_grid_avx2_fma_py,
        METH_VARARGS,
        "Compute a complete folded-anchor CFO grid with the AVX2/FMA kernel.",
    },
    {
        "folded_anchor_score_grid_backend",
        folded_anchor_score_grid_backend,
        METH_VARARGS,
        "Return the automatically selected folded-anchor grid backend.",
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
