# Independent scalar validation of detected peaks

The fine-grid experiment found a higher-scoring but unqualified rank-endpoint peak for scan 5579ea7efd8c20da: training gain 2.995290, optimizer ABNORMAL, gradient 0.00000214. Preserve this failed result.

Independently validate every detected grid peak in all six profiles using bounded scalar minimization of negative training score between its adjacent grid points, xatol 1e-10 and maxiter 100. Require scalar success, no global timing boundary hit, absolute model timing gradient <=0.01, central finite-difference discrepancy <=0.02, and training score no worse than the grid peak by more than 1e-7. These are declared before execution; do not relax gates. Report held scores only after training selection. This is a separate numerical validation, not a silent retry of the original optimizer or evidence of a global optimum.
