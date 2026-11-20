// KASF Rev.0.9.16 numerical kernel — Emscripten-compatible C++ / WebAssembly.
// No filesystem, audio-device, or browser APIs are used here.
#include <stdint.h>
#include <stddef.h>
#if defined(__wasm_simd128__)
#include <wasm_simd128.h>
#endif

extern "C" {
// Freestanding memory primitive: keeps the validation build self-contained.
void* memset(void* dst, int value, size_t count) {
    unsigned char* p = static_cast<unsigned char*>(dst);
    for (size_t i = 0; i < count; ++i) p[i] = static_cast<unsigned char>(value);
    return dst;
}
extern unsigned char __heap_base;
static uintptr_t kasf_heap_top = 0;

__attribute__((visibility("default")))
void kasf_reset_heap() {
    kasf_heap_top = (reinterpret_cast<uintptr_t>(&__heap_base) + 15u) & ~uintptr_t(15u);
}

__attribute__((visibility("default")))
uintptr_t kasf_alloc(uint32_t bytes) {
    if (!kasf_heap_top) kasf_reset_heap();
    uintptr_t p = (kasf_heap_top + 15u) & ~uintptr_t(15u);
    uintptr_t end = p + ((bytes + 15u) & ~uintptr_t(15u));
    uintptr_t currentBytes = static_cast<uintptr_t>(__builtin_wasm_memory_size(0)) * 65536u;
    if (end > currentBytes) {
        uintptr_t extra = end - currentBytes;
        uint32_t pages = static_cast<uint32_t>((extra + 65535u) / 65536u);
        if (__builtin_wasm_memory_grow(0, pages) == (size_t)-1) return 0;
    }
    kasf_heap_top = end;
    return p;
}

__attribute__((visibility("default")))
int kasf_simd_enabled() {
#ifdef __wasm_simd128__
    return 1;
#else
    return 0;
#endif
}

static double dot_range(const double* a, const double* b, int n) {
    int i = 0;
    double sum = 0.0;
#if defined(__wasm_simd128__)
    v128_t acc = wasm_f64x2_splat(0.0);
    for (; i + 1 < n; i += 2) {
        v128_t x = wasm_v128_load(a + i);
        v128_t y = wasm_v128_load(b + i);
        acc = wasm_f64x2_add(acc, wasm_f64x2_mul(x, y));
    }
    sum = wasm_f64x2_extract_lane(acc, 0) + wasm_f64x2_extract_lane(acc, 1);
#endif
    for (; i < n; ++i) sum += a[i] * b[i];
    return sum;
}

// Column-major input: columns[d][n]. Output beta[d].
// Solves min ||X beta - y||^2 + lambda ||beta-prior||^2 using Householder QR.
// scratchA: rows*d doubles; scratchB: rows doubles. rows = n+d.
__attribute__((visibility("default")))
int kasf_solve_ridge_qr(const double* columns, const double* target,
                        const double* prior, int n, int d, double lambda,
                        double* scratchA, double* scratchB, double* beta) {
    if (!columns || !target || !prior || !scratchA || !scratchB || !beta || n < 1 || d < 1 || d > 4096) return -1;
    const int rows = n + d;
    const double ridge = lambda > 0.0 ? __builtin_sqrt(lambda) : 0.0;
    for (int j = 0; j < d; ++j) {
        double* col = scratchA + static_cast<size_t>(j) * rows;
        for (int i = 0; i < n; ++i) col[i] = columns[static_cast<size_t>(j) * n + i];
        for (int i = 0; i < d; ++i) col[n + i] = (i == j) ? ridge : 0.0;
    }
    for (int i = 0; i < n; ++i) scratchB[i] = target[i];
    for (int i = 0; i < d; ++i) scratchB[n + i] = ridge * prior[i];

    int rank = d;
    for (int k = 0; k < d; ++k) {
        double* col = scratchA + static_cast<size_t>(k) * rows;
        double norm2 = dot_range(col + k, col + k, rows - k);
        double norm = __builtin_sqrt(norm2);
        if (norm < 1e-12) { --rank; continue; }
        const double alpha = col[k] >= 0.0 ? -norm : norm;
        const double vk = col[k] - alpha;
        double vnorm2 = vk * vk + dot_range(col + k + 1, col + k + 1, rows - k - 1);
        if (vnorm2 < 1e-25) { --rank; continue; }
        const double factor = 2.0 / vnorm2;
        for (int j = k + 1; j < d; ++j) {
            double* c = scratchA + static_cast<size_t>(j) * rows;
            double dot = vk * c[k] + dot_range(col + k + 1, c + k + 1, rows - k - 1);
            dot *= factor;
            c[k] -= dot * vk;
            int i = k + 1;
#if defined(__wasm_simd128__)
            v128_t vd = wasm_f64x2_splat(dot);
            v128_t vc = wasm_f64x2_splat(0.0);
            for (; i + 1 < rows; i += 2) {
                v128_t cv = wasm_v128_load(c + i);
                v128_t av = wasm_v128_load(col + i);
                cv = wasm_f64x2_sub(cv, wasm_f64x2_mul(vd, av));
                wasm_v128_store(c + i, cv);
            }
#endif
            for (; i < rows; ++i) c[i] -= dot * col[i];
        }
        double dotb = vk * scratchB[k] + dot_range(col + k + 1, scratchB + k + 1, rows - k - 1);
        dotb *= factor;
        scratchB[k] -= dotb * vk;
        int i = k + 1;
#if defined(__wasm_simd128__)
        v128_t vdb = wasm_f64x2_splat(dotb);
        for (; i + 1 < rows; i += 2) {
            v128_t bv = wasm_v128_load(scratchB + i);
            v128_t av = wasm_v128_load(col + i);
            bv = wasm_f64x2_sub(bv, wasm_f64x2_mul(vdb, av));
            wasm_v128_store(scratchB + i, bv);
        }
#endif
        for (; i < rows; ++i) scratchB[i] -= dotb * col[i];
        col[k] = alpha;
        for (i = k + 1; i < rows; ++i) col[i] = 0.0;
    }
    for (int k = d - 1; k >= 0; --k) {
        double rhs = scratchB[k];
        for (int j = k + 1; j < d; ++j) rhs -= scratchA[static_cast<size_t>(j) * rows + k] * beta[j];
        double diag = scratchA[static_cast<size_t>(k) * rows + k];
        beta[k] = (diag < 1e-12 && diag > -1e-12) ? prior[k] : rhs / diag;
    }
    return rank;
}
// In-place ridge QR variant used by Rev.0.9.12.
// Input matrix is already stored with rows=n+d stride per column. The first n
// values in each column are generated by the caller; this function writes the
// ridge rows and performs the same Householder operations directly in place.
// Arithmetic order is intentionally kept identical to kasf_solve_ridge_qr.
__attribute__((visibility("default")))
int kasf_solve_ridge_qr_inplace(double* columns, const double* target,
                                const double* prior, int n, int d, double lambda,
                                double* scratchB, double* beta) {
    if (!columns || !target || !prior || !scratchB || !beta || n < 1 || d < 1 || d > 4096) return -1;
    const int rows = n + d;
    const double ridge = lambda > 0.0 ? __builtin_sqrt(lambda) : 0.0;
    for (int j = 0; j < d; ++j) {
        double* col = columns + static_cast<size_t>(j) * rows;
        for (int i = 0; i < d; ++i) col[n + i] = (i == j) ? ridge : 0.0;
    }
    for (int i = 0; i < n; ++i) scratchB[i] = target[i];
    for (int i = 0; i < d; ++i) scratchB[n + i] = ridge * prior[i];

    int rank = d;
    for (int k = 0; k < d; ++k) {
        double* col = columns + static_cast<size_t>(k) * rows;
        double norm2 = dot_range(col + k, col + k, rows - k);
        double norm = __builtin_sqrt(norm2);
        if (norm < 1e-12) { --rank; continue; }
        const double alpha = col[k] >= 0.0 ? -norm : norm;
        const double vk = col[k] - alpha;
        double vnorm2 = vk * vk + dot_range(col + k + 1, col + k + 1, rows - k - 1);
        if (vnorm2 < 1e-25) { --rank; continue; }
        const double factor = 2.0 / vnorm2;
        for (int j = k + 1; j < d; ++j) {
            double* c = columns + static_cast<size_t>(j) * rows;
            double dot = vk * c[k] + dot_range(col + k + 1, c + k + 1, rows - k - 1);
            dot *= factor;
            c[k] -= dot * vk;
            int i = k + 1;
#if defined(__wasm_simd128__)
            v128_t vd = wasm_f64x2_splat(dot);
            for (; i + 1 < rows; i += 2) {
                v128_t cv = wasm_v128_load(c + i);
                v128_t av = wasm_v128_load(col + i);
                cv = wasm_f64x2_sub(cv, wasm_f64x2_mul(vd, av));
                wasm_v128_store(c + i, cv);
            }
#endif
            for (; i < rows; ++i) c[i] -= dot * col[i];
        }
        double dotb = vk * scratchB[k] + dot_range(col + k + 1, scratchB + k + 1, rows - k - 1);
        dotb *= factor;
        scratchB[k] -= dotb * vk;
        int i = k + 1;
#if defined(__wasm_simd128__)
        v128_t vdb = wasm_f64x2_splat(dotb);
        for (; i + 1 < rows; i += 2) {
            v128_t bv = wasm_v128_load(scratchB + i);
            v128_t av = wasm_v128_load(col + i);
            bv = wasm_f64x2_sub(bv, wasm_f64x2_mul(vdb, av));
            wasm_v128_store(scratchB + i, bv);
        }
#endif
        for (; i < rows; ++i) scratchB[i] -= dotb * col[i];
        col[k] = alpha;
        for (i = k + 1; i < rows; ++i) col[i] = 0.0;
    }
    for (int k = d - 1; k >= 0; --k) {
        double rhs = scratchB[k];
        for (int j = k + 1; j < d; ++j) rhs -= columns[static_cast<size_t>(j) * rows + k] * beta[j];
        double diag = columns[static_cast<size_t>(k) * rows + k];
        beta[k] = (diag < 1e-12 && diag > -1e-12) ? prior[k] : rhs / diag;
    }
    return rank;
}

}

// Exact-order radix-2 forward FFT kernel.
// Twiddle pairs are generated by JavaScript Math.cos/Math.sin and passed in,
// preserving the source implementation's transcendental values. Arithmetic
// order mirrors the JavaScript FFT; compile with -ffp-contract=off.
extern "C" __attribute__((visibility("default")))
int kasf_fft_inplace_scalar(double* real, double* imag, const double* twiddles, int n) {
    if (!real || !imag || !twiddles || n < 2 || (n & (n - 1)) != 0) return -1;

    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; (j & bit) != 0; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            double temp = real[i];
            real[i] = real[j];
            real[j] = temp;
            temp = imag[i];
            imag[i] = imag[j];
            imag[j] = temp;
        }
    }

    int stage = 0;
    for (int length = 2; length <= n; length <<= 1, ++stage) {
        const double wReal = twiddles[stage * 2];
        const double wImag = twiddles[stage * 2 + 1];
        const int half = length >> 1;
        for (int start = 0; start < n; start += length) {
            double currentReal = 1.0;
            double currentImag = 0.0;
            for (int j = 0; j < half; ++j) {
                const int evenIndex = start + j;
                const int oddIndex = evenIndex + half;
                const double oddReal = real[oddIndex];
                const double oddImag = imag[oddIndex];
                const double transformedReal = oddReal * currentReal - oddImag * currentImag;
                const double transformedImag = oddReal * currentImag + oddImag * currentReal;
                const double evenReal = real[evenIndex];
                const double evenImag = imag[evenIndex];
                real[evenIndex] = evenReal + transformedReal;
                imag[evenIndex] = evenImag + transformedImag;
                real[oddIndex] = evenReal - transformedReal;
                imag[oddIndex] = evenImag - transformedImag;
                const double nextReal = currentReal * wReal - currentImag * wImag;
                const double nextImag = currentReal * wImag + currentImag * wReal;
                currentReal = nextReal;
                currentImag = nextImag;
            }
        }
    }
    return 0;
}


// SIMD radix-2 FFT. Per-stage twiddle recurrence remains scalar and follows
// the JS recurrence exactly; independent butterfly pairs are evaluated in
// two Float64 SIMD lanes. This keeps each lane's operation order unchanged.
extern "C" __attribute__((visibility("default")))
int kasf_fft_inplace(double* real, double* imag, const double* stageTwiddles,
                     double* twiddleReal, double* twiddleImag, int n) {
    if (!real || !imag || !stageTwiddles || !twiddleReal || !twiddleImag ||
        n < 2 || (n & (n - 1)) != 0) return -1;

    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; (j & bit) != 0; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            double temp = real[i]; real[i] = real[j]; real[j] = temp;
            temp = imag[i]; imag[i] = imag[j]; imag[j] = temp;
        }
    }

    int stage = 0;
    for (int length = 2; length <= n; length <<= 1, ++stage) {
        const double wReal = stageTwiddles[stage * 2];
        const double wImag = stageTwiddles[stage * 2 + 1];
        const int half = length >> 1;
        twiddleReal[0] = 1.0;
        twiddleImag[0] = 0.0;
        for (int j = 1; j < half; ++j) {
            const double prevReal = twiddleReal[j - 1];
            const double prevImag = twiddleImag[j - 1];
            const double nextReal = prevReal * wReal - prevImag * wImag;
            const double nextImag = prevReal * wImag + prevImag * wReal;
            twiddleReal[j] = nextReal;
            twiddleImag[j] = nextImag;
        }
        for (int start = 0; start < n; start += length) {
            int j = 0;
#if defined(__wasm_simd128__)
            for (; j + 1 < half; j += 2) {
                const int evenIndex = start + j;
                const int oddIndex = evenIndex + half;
                const v128_t oddReal = wasm_v128_load(real + oddIndex);
                const v128_t oddImag = wasm_v128_load(imag + oddIndex);
                const v128_t currentReal = wasm_v128_load(twiddleReal + j);
                const v128_t currentImag = wasm_v128_load(twiddleImag + j);
                const v128_t transformedReal = wasm_f64x2_sub(
                    wasm_f64x2_mul(oddReal, currentReal),
                    wasm_f64x2_mul(oddImag, currentImag));
                const v128_t transformedImag = wasm_f64x2_add(
                    wasm_f64x2_mul(oddReal, currentImag),
                    wasm_f64x2_mul(oddImag, currentReal));
                const v128_t evenReal = wasm_v128_load(real + evenIndex);
                const v128_t evenImag = wasm_v128_load(imag + evenIndex);
                wasm_v128_store(real + evenIndex, wasm_f64x2_add(evenReal, transformedReal));
                wasm_v128_store(imag + evenIndex, wasm_f64x2_add(evenImag, transformedImag));
                wasm_v128_store(real + oddIndex, wasm_f64x2_sub(evenReal, transformedReal));
                wasm_v128_store(imag + oddIndex, wasm_f64x2_sub(evenImag, transformedImag));
            }
#endif
            for (; j < half; ++j) {
                const int evenIndex = start + j;
                const int oddIndex = evenIndex + half;
                const double oddReal = real[oddIndex];
                const double oddImag = imag[oddIndex];
                const double currentReal = twiddleReal[j];
                const double currentImag = twiddleImag[j];
                const double transformedReal = oddReal * currentReal - oddImag * currentImag;
                const double transformedImag = oddReal * currentImag + oddImag * currentReal;
                const double evenReal = real[evenIndex];
                const double evenImag = imag[evenIndex];
                real[evenIndex] = evenReal + transformedReal;
                imag[evenIndex] = evenImag + transformedImag;
                real[oddIndex] = evenReal - transformedReal;
                imag[oddIndex] = evenImag - transformedImag;
            }
        }
    }
    return 0;
}



// Build the DPSS concentration matrix from its symmetric Toeplitz kernel.
// Each kernel value is produced once by JavaScript Math.sin; copying it by
// |i-j| reproduces the reference matrix entries bit-for-bit while avoiding
// N*N transcendental calls and the N*N JS-to-WASM matrix transfer.
extern "C" __attribute__((visibility("default")))
int kasf_dpss_build_toeplitz(const double* kernel, double* matrix, int n) {
    if (!kernel || !matrix || n < 2 || n > 4096) return -1;
    for (int i = 0; i < n; ++i) {
        const size_t row = static_cast<size_t>(i) * n;
        for (int j = 0; j < n; ++j) {
            const int d = i > j ? i - j : j - i;
            matrix[row + j] = kernel[d];
        }
    }
    return 0;
}

// DPSS-style power iteration kernel. The spectral concentration matrix and
// initial vector are built by JS to retain its Math.sin/cos values; the
// sequential dot products, orthogonalization and normalization run in WASM.
extern "C" __attribute__((visibility("default")))
int kasf_dpss_power_iteration(const double* matrix, const double* initial,
                              const double* previousBasis, int basisCount,
                              double* result, double* scratch,
                              int n, int iterations) {
    if (!matrix || !initial || !result || !scratch || n < 2 ||
        basisCount < 0 || basisCount > 8 || iterations < 0 || iterations > 10000 ||
        (basisCount > 0 && !previousBasis)) return -1;

    for (int i = 0; i < n; ++i) result[i] = initial[i];
    double* current = result;
    double* next = scratch;

    auto orthogonalize_and_normalize = [&]() {
        for (int q = 0; q < basisCount; ++q) {
            const double* basis = previousBasis + static_cast<size_t>(q) * n;
            double dot = 0.0;
            for (int i = 0; i < n; ++i) dot += current[i] * basis[i];
            for (int i = 0; i < n; ++i) current[i] -= dot * basis[i];
        }
        double norm2 = 0.0;
        for (int i = 0; i < n; ++i) norm2 += current[i] * current[i];
        double norm = __builtin_sqrt(norm2);
        if (norm == 0.0) norm = 1.0;
        for (int i = 0; i < n; ++i) current[i] /= norm;
    };

    orthogonalize_and_normalize();
    for (int iteration = 0; iteration < iterations; ++iteration) {
        for (int i = 0; i < n; ++i) {
            const double* row = matrix + static_cast<size_t>(i) * n;
            double sum = 0.0;
            for (int j = 0; j < n; ++j) sum += row[j] * current[j];
            next[i] = sum;
        }
        double* swap = current;
        current = next;
        next = swap;
        orthogonalize_and_normalize();
    }
    if (current != result) {
        for (int i = 0; i < n; ++i) result[i] = current[i];
    }
    return 0;
}




// GPO/GFRE ordered exact Reader-domain delta score. JS prepares old/new
// quantized component sample values with the same Math.sin/Math.cos path;
// WASM performs only the scalar residual update and squared-error reduction.
extern "C" __attribute__((visibility("default")))
int kasf_gpo_component_sse(const double* residual, const double* oldValues,
                           const double* newValues, int n, double* out) {
    if (!residual || !oldValues || !newValues || !out || n < 0) return -1;
    double sse = 0.0;
    int i = 0;
#if defined(__wasm_simd128__)
    // SIMD computes two independent residual squares at once, but lane 0 and
    // lane 1 are accumulated in the original scalar order. This preserves the
    // exact IEEE-754 reduction sequence used by the JS reference.
    for (; i + 1 < n; i += 2) {
        const v128_t delta = wasm_f64x2_sub(
            wasm_v128_load(newValues + i), wasm_v128_load(oldValues + i));
        const v128_t r = wasm_f64x2_sub(wasm_v128_load(residual + i), delta);
        const v128_t squared = wasm_f64x2_mul(r, r);
        sse += wasm_f64x2_extract_lane(squared, 0);
        sse += wasm_f64x2_extract_lane(squared, 1);
    }
#endif
    for (; i < n; ++i) {
        const double delta = newValues[i] - oldValues[i];
        const double r = residual[i] - delta;
        sse += r * r;
    }
    out[0] = sse;
    return 0;
}


// Exact-order Haar wavelet-packet matching-pursuit step. Metadata and atoms
// are packed once by JavaScript. Dot products, candidate traversal, tie
// breaking, and residual subtraction preserve the reference loop order.
extern "C" __attribute__((visibility("default")))
int kasf_haar_best_update(double* residual, int n,
                          const double* atoms, const double* offsets,
                          const double* lengths, const double* hops,
                          int atomCount, double minScore, double* out) {
    if (!residual || !atoms || !offsets || !lengths || !hops || !out ||
        n < 1 || atomCount < 1) return -1;
    int found = 0;
    int bestStart = 0;
    int bestAtom = 0;
    double bestDot = 0.0;
    double bestScore = 0.0;
    for (int a = 0; a < atomCount; ++a) {
        const int offset = static_cast<int>(offsets[a]);
        const int length = static_cast<int>(lengths[a]);
        const int hop = static_cast<int>(hops[a]);
        if (length > n || length < 2 || hop < 1 || offset < 0) continue;
        int start = 0;
        for (; start + length <= n; start += hop) {
            double dot = 0.0;
            int j = 0;
#if defined(__wasm_simd128__)
            for (; j + 1 < length; j += 2) {
                const v128_t products = wasm_f64x2_mul(
                    wasm_v128_load(residual + start + j),
                    wasm_v128_load(atoms + offset + j));
                dot += wasm_f64x2_extract_lane(products, 0);
                dot += wasm_f64x2_extract_lane(products, 1);
            }
#endif
            for (; j < length; ++j) {
                dot += residual[start + j] * atoms[offset + j];
            }
            const double score = dot * dot;
            if (!found || score > bestScore) {
                found = 1;
                bestScore = score;
                bestDot = dot;
                bestStart = start;
                bestAtom = a;
            }
        }
    }
    if (!found || bestScore < minScore) {
        out[0] = found ? bestScore : 0.0;
        out[1] = 0.0;
        out[2] = 0.0;
        out[3] = 0.0;
        out[4] = 0.0;
        return 0;
    }
    const int atomOffset = static_cast<int>(offsets[bestAtom]);
    const int atomLength = static_cast<int>(lengths[bestAtom]);
    for (int j = 0; j < atomLength; ++j) {
        residual[bestStart + j] -= bestDot * atoms[atomOffset + j];
    }
    out[0] = bestScore;
    out[1] = bestDot;
    out[2] = static_cast<double>(bestStart);
    out[3] = static_cast<double>(bestAtom);
    out[4] = 1.0;
    return 0;
}

extern "C" __attribute__((visibility("default")))
double kasf_haar_residual_energy(const double* residual, int n) {
    if (!residual || n < 0) return -1.0;
    double energy = 0.0;
    for (int i = 0; i < n; ++i) energy += residual[i] * residual[i];
    return energy;
}

// Exact-gate energy kernel. Segmentation and accumulation order mirror the
// JavaScript implementation. The caller supplies its already-rounded hop.
extern "C" __attribute__((visibility("default")))
int kasf_qrp_exact_gate(const double* original, const double* recon,
                        const double* delta, int n, int hop,
                        double minFraction, double energyLimit,
                        double* out) {
    if (!original || !recon || !delta || !out || n < 1 || hop < 1) return -1;
    double gain = 0.0, sourceEnergy = 0.0, addedEnergy = 0.0, initial = 0.0;
    for (int start = 0; start < n; start += hop) {
        const int end = (start + hop < n) ? start + hop : n;
        double srcE = 0.0, baseE = 0.0, afterE = 0.0;
        for (int i = start; i < end; ++i) {
            const double e = original[i] - recon[i];
            const double d = delta[i];
            const double originalValue = original[i];
            const double reconValue = recon[i];
            gain += 2.0 * e * d - d * d;
            srcE += originalValue * originalValue;
            baseE += reconValue * reconValue;
            const double afterValue = reconValue + d;
            afterE += afterValue * afterValue;
            sourceEnergy += originalValue * originalValue;
            addedEnergy += d * d;
            initial += e * e;
        }
        const double src = __builtin_sqrt(srcE);
        const double base = __builtin_sqrt(baseE);
        const double after = __builtin_sqrt(afterE);
        const double a = src * 1.40;
        const double b = base * 1.12;
        const double limit = (a > b ? a : b) + 0.0001;
        if (after > limit && after > src + 0.01) {
            out[0] = 0.0; out[1] = gain;
            out[2] = gain / (initial > 1e-15 ? initial : 1e-15);
            out[3] = sourceEnergy; out[4] = addedEnergy; out[5] = initial;
            return 0;
        }
    }
    const double fraction = gain / (initial > 1e-15 ? initial : 1e-15);
    const int accept = gain > 0.0 && fraction > minFraction && addedEnergy < sourceEnergy * energyLimit;
    out[0] = accept ? 1.0 : 0.0; out[1] = gain; out[2] = fraction;
    out[3] = sourceEnergy; out[4] = addedEnergy; out[5] = initial;
    return 0;
}
