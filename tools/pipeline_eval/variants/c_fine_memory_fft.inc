/* Included after the original twiddle and radix functions. The first two
 * passes share only 32 columns at a time. The dense binary64 input plane and
 * its restore-to-zero pass are absent. */
void fine_search_transform(const Complex *restrict weighted, const Complex *restrict roots,
                           Complex *restrict work, Complex *restrict selected, int frames,
                           int bins) {
    enum { columns = 32, width2 = 625, width3 = 125, width4 = 25 };
    const Complex zero = {0, 0};
    Complex *second = work, *prefix = work + fft_size;
    Complex *first = prefix, *third = prefix + width4*max_bins;
    const int used3 = bins < 160 ? bins : 160;
    for (int frame = 0; frame < frames; ++frame) {
        const Complex *pilot = weighted + frame*150*taps;
        for (int base = 0; base < width2; base += columns) {
            const int count = width2-base < columns ? width2-base : columns;
            for (int stripe = 0; stripe < 4; ++stripe) {
                for (int i = 0; i < count; ++i) {
                    const int column = base + i + stripe*width2;
                    Complex input[8], part[8];
                    for (int k = 0; k < 6; ++k) {
                        const int index = column + k*2500;
                        const int within = index % (2*taps);
                        input[k] = index >= 2*taps && index < 301*taps && within < taps
                            ? pilot[(index/(2*taps)-1)*taps+within] : zero;
                    }
                    input[6] = input[7] = zero;
                    radix8(input, 1, part);
                    first[stripe*columns+i] = part[0];
                    for (int d = 1; d < 8; ++d)
                        first[(4*d+stripe)*columns+i] = mix(part[d], roots[column*d]);
                }
            }
            for (int k = 0; k < 8; ++k) {
                #pragma omp simd
                for (int i = 0; i < count; ++i) {
                    Complex part[4];
                    radix4(first+4*k*columns+i, columns, part);
                    second[base+i+width2*k] = part[0];
                    for (int d = 1; d < 4; ++d)
                        second[base+i+width2*(k+8*d)] = mix(part[d], roots[(base+i)*8*d]);
                }
            }
        }
        /* Compute one column of pass four at a time. Pass three consumes all
         * five independent row positions before feeding that column. */
        for (int i = 0; i < width4; ++i) {
            for (int k = 0; k < 32 && k < used3; ++k) {
                for (int j = 0; j < 5; ++j) {
                    const int index = i + width4*j;
                    const Complex *in = second + index + 5*width3*k;
                    if (k+32 >= used3) {
                        third[5*k+j] = radix5_zero(in, width3);
                    } else {
                        Complex part[5];
                        radix5(in, width3, part);
                        third[5*k+j] = part[0];
                        for (int d = 1; d < 5 && k+32*d < used3; ++d)
                            third[5*(k+32*d)+j] = mix(part[d], roots[index*32*d]);
                    }
                }
            }
            for (int k = 0; k < used3; ++k) {
                if (k+160 >= bins) {
                    prefix[k*width4+i] = radix5_zero(third+5*k, 1);
                } else {
                    Complex part[5];
                    radix5(third+5*k, 1, part);
                    prefix[k*width4+i] = part[0];
                    prefix[(k+160)*width4+i] = mix(part[1], roots[i*160]);
                    if (k+320 < bins) prefix[(k+320)*width4+i] = mix(part[2], roots[i*320]);
                }
            }
        }
        for (int k = 0; k < bins; ++k) {
            Complex part[5];
            for (int i = 0; i < 5; ++i) part[i] = radix5_zero(prefix+i+width4*k, 5);
            selected[frame*bins+k] = radix5_zero(part, 1);
        }
    }
}
