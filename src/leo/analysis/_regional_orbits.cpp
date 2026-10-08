// Double-precision orbit kernel qualified in the N01--N64 Hard60 replay.
// No fast-math; the Python scorer remains the oracle.
#include <cmath>
#include <algorithm>
static int predict_kernel(int n, int k, int t, double node0, double step,
 const double* times, const double* rf, const double* shifts,
 const double* pos, const double* vel, const double* site, const double* up,
 const double* jac, int derivatives, double* prediction, unsigned char* visible,
 double* spatial, double* timing) {
 for(int i=0;i<n;i++) for(int j=0;j<k;j++) {
  double query=times[i]+shifts[j];
  if(query<node0 || query>node0+(t-1)*step) return 1;
  double frac=(query-node0)/step;
  int lo=std::min(int(std::floor(frac)),t-2); double w=frac-lo;
  long index=(long(j)*t+lo)*3, out=long(i)*k+j;
  double delta[3],v[3],pr[3],acc[3],d[3];
  double dist2=0;
  for(int a=0;a<3;a++) {
   double pd=pos[index+3+a]-pos[index+a], vd=vel[index+3+a]-vel[index+a];
   delta[a]=pos[index+a]+w*pd-site[a]; v[a]=vel[index+a]+w*vd;
   pr[a]=pd/step; acc[a]=vd/step; dist2+=delta[a]*delta[a];
  }
  double dist=std::sqrt(dist2); if(dist<=0) return 2;
  double radial=0,elevation=0,dr=0;
  for(int a=0;a<3;a++) { d[a]=delta[a]/dist; radial+=d[a]*v[a]; elevation+=d[a]*up[a]; dr+=d[a]*pr[a]; }
  double factor=rf[i]/299792.458;
  prediction[out]=-factor*radial; visible[out]=elevation>=0;
  if(derivatives) {
   for(int axis=0;axis<2;axis++) {
    double value=0;
    for(int a=0;a<3;a++) value+=(factor*(v[a]-radial*d[a])/dist)*jac[axis*3+a];
    spatial[out*2+axis]=value;
   }
   double rate=0;
   for(int a=0;a<3;a++) rate+=((pr[a]-d[a]*dr)/dist)*v[a]+d[a]*acc[a];
   timing[out]=-factor*rate;
  }
 }
 return 0;
}

#define PY_SSIZE_T_CLEAN
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <Python.h>
#include <numpy/arrayobject.h>

static PyObject* predict(PyObject*, PyObject* args) {
    PyObject* objects[8];
    double node0, step;
    int derivatives;
    if (!PyArg_ParseTuple(args, "OOOOOOOOddp", &objects[0], &objects[1], &objects[2],
            &objects[3], &objects[4], &objects[5], &objects[6], &objects[7],
            &node0, &step, &derivatives)) return nullptr;
    PyArrayObject* a[8] = {};
    PyArrayObject* out[4] = {};
    PyObject* result = nullptr;
    npy_intp n = 0, k = 0, t = 0;
    for (int i = 0; i < 8; ++i) {
        a[i] = reinterpret_cast<PyArrayObject*>(
            PyArray_FROM_OTF(objects[i], NPY_DOUBLE, NPY_ARRAY_IN_ARRAY));
        if (!a[i]) goto done;
    }
    if (PyArray_NDIM(a[0]) != 1 || PyArray_NDIM(a[1]) != 1 ||
        PyArray_NDIM(a[2]) != 1 || PyArray_NDIM(a[3]) != 3 ||
        PyArray_NDIM(a[4]) != 3 || PyArray_NDIM(a[5]) != 1 ||
        PyArray_NDIM(a[6]) != 1 || PyArray_NDIM(a[7]) != 2) {
        PyErr_SetString(PyExc_ValueError, "invalid native orbit dimensions"); goto done;
    }
    n = PyArray_DIM(a[0], 0); k = PyArray_DIM(a[2], 0); t = PyArray_DIM(a[3], 1);
    if (n < 1 || k < 1 || t < 2 || n > INT_MAX || k > INT_MAX || t > INT_MAX ||
        PyArray_DIM(a[1], 0) != n ||
        PyArray_DIM(a[3], 0) != k || PyArray_DIM(a[3], 2) != 3 ||
        PyArray_DIM(a[4], 0) != k || PyArray_DIM(a[4], 1) != t ||
        PyArray_DIM(a[4], 2) != 3 || PyArray_DIM(a[5], 0) != 3 ||
        PyArray_DIM(a[6], 0) != 3 || PyArray_DIM(a[7], 0) != 2 ||
        PyArray_DIM(a[7], 1) != 3 || !std::isfinite(node0) ||
        !std::isfinite(step) || step <= 0) {
        PyErr_SetString(PyExc_ValueError, "invalid native orbit shapes or step"); goto done;
    }
    // Direct callers receive the same finite-input guarantee as the Python port.
    for (int i = 0; i < 8; ++i) {
        auto* data = static_cast<double*>(PyArray_DATA(a[i]));
        for (npy_intp j = 0; j < PyArray_SIZE(a[i]); ++j)
            if (!std::isfinite(data[j])) {
                PyErr_SetString(PyExc_ValueError, "nonfinite native orbit input"); goto done;
            }
    }
    {
        npy_intp dims[3] = {n, k, 2};
        npy_intp empty[1] = {0};
        out[0] = reinterpret_cast<PyArrayObject*>(PyArray_SimpleNew(2, dims, NPY_DOUBLE));
        out[1] = reinterpret_cast<PyArrayObject*>(PyArray_SimpleNew(2, dims, NPY_BOOL));
        out[2] = reinterpret_cast<PyArrayObject*>(PyArray_SimpleNew(
            derivatives ? 3 : 1, derivatives ? dims : empty, NPY_DOUBLE));
        out[3] = reinterpret_cast<PyArrayObject*>(PyArray_SimpleNew(
            derivatives ? 2 : 1, derivatives ? dims : empty, NPY_DOUBLE));
        if (!out[0] || !out[1] || !out[2] || !out[3]) goto done;
        int code;
        Py_BEGIN_ALLOW_THREADS
        code = predict_kernel(int(n), int(k), int(t), node0, step,
            static_cast<double*>(PyArray_DATA(a[0])),
            static_cast<double*>(PyArray_DATA(a[1])),
            static_cast<double*>(PyArray_DATA(a[2])),
            static_cast<double*>(PyArray_DATA(a[3])),
            static_cast<double*>(PyArray_DATA(a[4])),
            static_cast<double*>(PyArray_DATA(a[5])),
            static_cast<double*>(PyArray_DATA(a[6])),
            static_cast<double*>(PyArray_DATA(a[7])), derivatives,
            static_cast<double*>(PyArray_DATA(out[0])),
            static_cast<unsigned char*>(PyArray_DATA(out[1])),
            static_cast<double*>(PyArray_DATA(out[2])),
            static_cast<double*>(PyArray_DATA(out[3])));
        Py_END_ALLOW_THREADS
        if (code) {
            PyErr_SetString(PyExc_ValueError, code == 1 ?
                "orbit query outside ephemeris support" : "satellite coincides with observer");
            goto done;
        }
        result = PyTuple_Pack(4, out[0], out[1], out[2], out[3]);
    }
done:
    for (auto* item : a) Py_XDECREF(item);
    for (auto* item : out) Py_XDECREF(item);
    return result;
}
static PyMethodDef methods[] = {
    {"predict", predict, METH_VARARGS, "Bounded orbit interpolation and derivatives."},
    {nullptr, nullptr, 0, nullptr}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_regional_orbits", nullptr, -1, methods,
    nullptr, nullptr, nullptr, nullptr
};
PyMODINIT_FUNC PyInit__regional_orbits() { import_array(); return PyModule_Create(&module); }

