// KASF Fast Baseline Generator — experimental KASF v1 writer.
// C++17, standard library only. This is a fast spectral-pursuit baseline,
// NOT a reimplementation of the full Rev.0.9.20 analysis/optimization stack.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
static constexpr double PI = 3.141592653589793238462643383279502884;
static constexpr double TAU = 2.0 * PI;

struct WavInfo {
    uint16_t format = 0; // 1=PCM, 3=IEEE float
    uint16_t channels = 0;
    uint32_t rate = 0;
    uint16_t blockAlign = 0;
    uint16_t bits = 0;
    uint64_t dataOffset = 0;
    uint64_t dataBytes = 0;
    uint64_t samples = 0;
};

struct Component { double f, a, p; };
struct Options {
    double frameMs = 10.0;
    double thresholdDb = -58.0;
    double minHz = 15.0;
    int maxComponents = 48;
    bool force = false;
    bool edgePad = false;
    bool temporalTracking = true;
    bool experimentalTrackRefine = false;
    std::string trackerAssignment = "greedy";
    fs::path baseWav;
    fs::path trackMap;
};

struct TempCleanup {
    std::vector<fs::path> paths;
    bool released = false;
    ~TempCleanup() {
        if (released) return;
        for (const auto& path : paths) {
            if (path.empty()) continue;
            std::error_code ec;
            fs::remove(path, ec);
        }
    }
};

static uint16_t u16(const uint8_t* p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
static uint32_t u32(const uint8_t* p) { return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24); }
static void writeU16(std::ostream& o, uint16_t x) { o.put(char(x&255)); o.put(char((x>>8)&255)); }
static void writeU32(std::ostream& o, uint32_t x) { for (int i=0;i<4;i++) o.put(char((x>>(8*i))&255)); }
static void writeU64(std::ostream& o, uint64_t x) { for (int i=0;i<8;i++) o.put(char((x>>(8*i))&255)); }
static void writeF64(std::ostream& o, double x) { uint64_t b; std::memcpy(&b,&x,8); writeU64(o,b); }
static uint64_t roundPositive(double x) { return static_cast<uint64_t>(std::floor(x + 0.5)); }

static WavInfo parseWav(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("Cannot open input WAV");
    std::array<uint8_t,12> head{};
    in.read(reinterpret_cast<char*>(head.data()), head.size());
    if (in.gcount()!=12 || std::memcmp(head.data(),"RIFF",4)!=0 || std::memcmp(head.data()+8,"WAVE",4)!=0)
        throw std::runtime_error("Input must be RIFF/WAVE (RF64 is not supported by this prototype)");
    WavInfo w; bool haveFmt=false, haveData=false;
    const uint64_t fileSize=fs::file_size(path);
    uint64_t pos=12;
    while (pos+8<=fileSize) {
        in.seekg(static_cast<std::streamoff>(pos));
        std::array<uint8_t,8> ch{}; in.read(reinterpret_cast<char*>(ch.data()),8);
        if (in.gcount()!=8) break;
        const uint32_t len=u32(ch.data()+4); const uint64_t start=pos+8;
        if (start+uint64_t(len)>fileSize) throw std::runtime_error("Truncated WAV chunk");
        if (std::memcmp(ch.data(),"fmt ",4)==0) {
            if (len<16 || len>4096) throw std::runtime_error("Invalid WAV fmt chunk");
            std::vector<uint8_t> f(len); in.seekg(static_cast<std::streamoff>(start));
            in.read(reinterpret_cast<char*>(f.data()),len);
            if (static_cast<uint32_t>(in.gcount())!=len) throw std::runtime_error("Truncated WAV fmt data");
            w.format=u16(f.data()); w.channels=u16(f.data()+2); w.rate=u32(f.data()+4);
            w.blockAlign=u16(f.data()+12); w.bits=u16(f.data()+14);
            if (w.format==0xFFFE) {
                if (len<40 || u16(f.data()+16)<22) throw std::runtime_error("Invalid WAVE_FORMAT_EXTENSIBLE fmt");
                const uint16_t validBits=u16(f.data()+18);
                if (validBits!=w.bits) throw std::runtime_error("Extensible WAV validBits != containerBits is unsupported");
                static const uint8_t pcmGuid[16]={1,0,0,0,0,0,16,0,128,0,0,170,0,56,155,113};
                if (std::memcmp(f.data()+24,pcmGuid,16)!=0)
                    throw std::runtime_error("Only WAVE_FORMAT_EXTENSIBLE PCM SubFormat is supported");
                w.format=1;
            }
            haveFmt=true;
        } else if (std::memcmp(ch.data(),"data",4)==0) {
            w.dataOffset=start; w.dataBytes=len; haveData=true;
        }
        pos=start+uint64_t(len)+(len&1u);
        if (haveFmt && haveData) break;
    }
    if (!haveFmt || !haveData) throw std::runtime_error("WAV fmt/data chunk missing");
    if (w.channels<1 || w.channels>8 || w.rate<1000 || w.rate>768000)
        throw std::runtime_error("WAV channel count or sample rate outside supported range");
    const bool pcm=w.format==1 && (w.bits==8||w.bits==16||w.bits==24||w.bits==32);
    if (!pcm) throw std::runtime_error("Input must be uncompressed integer PCM WAV (8/16/24/32-bit)");
    if (w.blockAlign!=w.channels*(w.bits/8)) throw std::runtime_error("Unsupported WAV block alignment");
    w.samples=w.dataBytes/w.blockAlign;
    if (!w.samples) throw std::runtime_error("Input WAV contains no samples");
    if (w.dataBytes%w.blockAlign) throw std::runtime_error("WAV data chunk ends mid-frame");
    return w;
}

static void writePcmWavHeader(std::ostream& out, const WavInfo& w, uint64_t sampleCount) {
    if (w.format != 1 || !(w.bits==8 || w.bits==16 || w.bits==24 || w.bits==32))
        throw std::runtime_error("--base-wav requires integer PCM WAV input (8/16/24/32-bit)");
    const uint64_t dataBytes=sampleCount*w.blockAlign;
    if (dataBytes>0xFFFFFFFFULL-36ULL) throw std::runtime_error("Base WAV would exceed classic RIFF 4 GiB size limit");
    out.write("RIFF",4); writeU32(out,static_cast<uint32_t>(36+dataBytes));
    out.write("WAVEfmt ",8); writeU32(out,16); writeU16(out,1); writeU16(out,w.channels);
    writeU32(out,w.rate); writeU32(out,w.rate*w.blockAlign); writeU16(out,w.blockAlign); writeU16(out,w.bits);
    out.write("data",4); writeU32(out,static_cast<uint32_t>(dataBytes));
}

static void appendPcmSample(std::vector<uint8_t>& buffer, double value, uint16_t bits) {
    const int64_t scale=int64_t(1)<<(bits-1);
    double qd=std::floor(value*double(scale)+0.5);
    const int64_t q=static_cast<int64_t>(std::max(-double(scale),std::min(double(scale-1),qd)));
    uint64_t raw=static_cast<uint64_t>(q);
    if(bits==8) buffer.push_back(static_cast<uint8_t>(q+128));
    else for(unsigned i=0;i<bits/8;i++) buffer.push_back(static_cast<uint8_t>((raw>>(8*i))&255));
}

static double decodeOne(const uint8_t* p, const WavInfo& w) {
    switch (w.bits) {
        case 8: return (double(p[0])-128.0)/128.0;
        case 16: { int16_t x=static_cast<int16_t>(u16(p)); return double(x)/32768.0; }
        case 24: { int32_t x=int32_t(p[0])|(int32_t(p[1])<<8)|(int32_t(p[2])<<16); if(x&0x800000)x|=~0xFFFFFF; return double(x)/8388608.0; }
        case 32: { int32_t x=static_cast<int32_t>(u32(p)); return double(x)/2147483648.0; }
    }
    return 0.0;
}

static void readRange(std::ifstream& in, const WavInfo& w, uint64_t first,
                      uint64_t count, std::vector<std::vector<double>>& dst, size_t dstOffset) {
    if (count==0) return;
    const uint64_t bytes64=count*w.blockAlign;
    if (bytes64>std::numeric_limits<size_t>::max()) throw std::runtime_error("WAV read range is too large");
    std::vector<uint8_t> raw(static_cast<size_t>(bytes64));
    in.clear(); in.seekg(static_cast<std::streamoff>(w.dataOffset+first*w.blockAlign));
    in.read(reinterpret_cast<char*>(raw.data()),static_cast<std::streamsize>(raw.size()));
    if (static_cast<size_t>(in.gcount())!=raw.size()) throw std::runtime_error("Short WAV read");
    const size_t bps=w.bits/8;
    for (uint64_t i=0;i<count;i++) {
        const uint8_t* frame=raw.data()+static_cast<size_t>(i)*w.blockAlign;
        for (uint16_t ch=0;ch<w.channels;ch++) dst[ch][dstOffset+static_cast<size_t>(i)]=decodeOne(frame+ch*bps,w);
    }
}

static size_t nextPow2(size_t n) {
    size_t p=1; while(p<n) { if(p>(std::numeric_limits<size_t>::max()/2)) throw std::runtime_error("FFT size overflow"); p<<=1; }
    return p;
}

static void fft(std::vector<std::complex<double>>& a) {
    const size_t n=a.size();
    for(size_t i=1,j=0;i<n;i++) {
        size_t bit=n>>1; for(;j&bit;bit>>=1) j^=bit; j^=bit;
        if(i<j) std::swap(a[i],a[j]);
    }
    for(size_t len=2;len<=n;len<<=1) {
        const double angle=-TAU/double(len);
        const std::complex<double> step(std::cos(angle),std::sin(angle));
        for(size_t base=0;base<n;base+=len) {
            std::complex<double> w(1.0,0.0); const size_t half=len>>1;
            for(size_t j=0;j<half;j++) {
                const auto u=a[base+j], v=a[base+j+half]*w;
                a[base+j]=u+v; a[base+j+half]=u-v; w*=step;
            }
        }
        if(len==n) break; // prevent size_t shift wrap at the top end
    }
}

static void makeOsc(double omega, double phase, double& s, double& c,
                    double& ds, double& dc) {
    s=std::sin(phase); c=std::cos(phase); ds=std::sin(omega); dc=std::cos(omega);
}

static void advanceOsc(double& s, double& c, double ds, double dc) {
    const double ns=s*dc+c*ds, nc=c*dc-s*ds; s=ns; c=nc;
}

static bool fitSine(const std::vector<double>& residual, const std::vector<double>& win,
                    double rate, double frequency, double& amplitude, double& phase) {
    const double omega=TAU*frequency/rate;
    double s,c,ds,dc; makeOsc(omega,0.0,s,c,ds,dc);
    double ss=0,sc=0,cc=0,ys=0,yc=0;
    for(size_t n=0;n<residual.size();n++) {
        const double wt=win[n], x=residual[n];
        ss+=wt*s*s; sc+=wt*s*c; cc+=wt*c*c;
        ys+=wt*x*s; yc+=wt*x*c;
        advanceOsc(s,c,ds,dc);
        if((n&127u)==127u) { const double norm=1.0/std::hypot(s,c); s*=norm; c*=norm; }
    }
    const double det=ss*cc-sc*sc;
    if(!(det>1e-20) || !std::isfinite(det)) return false;
    const double coefSin=(ys*cc-yc*sc)/det;
    const double coefCos=(yc*ss-ys*sc)/det;
    amplitude=std::hypot(coefSin,coefCos);
    phase=std::atan2(coefCos,coefSin);
    return std::isfinite(amplitude)&&std::isfinite(phase);
}

static double wrapPhase(double p) { p=std::fmod(p,TAU); if(p<0)p+=TAU; return p; }
static Component quantized(double f,double a,double p) {
    const uint32_t qf=static_cast<uint32_t>(std::min<uint64_t>(0xFFFFFF,roundPositive(std::max(0.0,std::min(96000.0,f))/96000.0*0xFFFFFF)));
    const uint32_t qa=static_cast<uint32_t>(std::min<uint64_t>(0x3FFF,roundPositive(std::max(0.0,std::min(1.0,a))*0x3FFF)));
    const uint32_t qp=static_cast<uint32_t>(std::min<uint64_t>(1023,roundPositive(wrapPhase(p)/TAU*1024.0)));
    return {double(qf)/0xFFFFFF*96000.0,double(qa)/0x3FFF,double(qp)*TAU/1024.0};
}

static std::vector<Component> analyzeFrame(const std::vector<double>& source,
        const std::vector<double>& win, std::vector<std::complex<double>>& spec,
        uint32_t rate, const Options& opt, double threshold) {
    const size_t n=source.size(), m=spec.size();
    std::vector<double> residual=source;
    std::vector<Component> comps; comps.reserve(static_cast<size_t>(opt.maxComponents));
    for(int iteration=0;iteration<opt.maxComponents;iteration++) {
        std::fill(spec.begin(),spec.end(),std::complex<double>(0.0,0.0));
        for(size_t i=0;i<n;i++) spec[i]=std::complex<double>(residual[i]*win[i],0.0);
        fft(spec);
        const size_t nyquistEnd=m/2;
        const size_t firstAllowed=std::max<size_t>(1,static_cast<size_t>(std::ceil(opt.minHz*double(m)/double(rate))));
        const size_t maxFreqEnd=static_cast<size_t>(std::floor(96000.0*double(m)/double(rate)))+1;
        const size_t last=std::min(nyquistEnd,maxFreqEnd);
        size_t best=0; double bestMag=0.0;
        for(size_t k=firstAllowed;k<last;k++) {
            const double mag=std::norm(spec[k]);
            if(mag>bestMag) { bestMag=mag; best=k; }
        }
        if(best==0 || !(bestMag>1e-30)) break;
        const double ym=std::log(std::max(1e-300,std::abs(spec[best-1])));
        const double y0=std::log(std::max(1e-300,std::abs(spec[best])));
        const double yp=std::log(std::max(1e-300,std::abs(spec[best+1])));
        const double den=ym-2.0*y0+yp;
        double delta=std::abs(den)>1e-15?0.5*(ym-yp)/den:0.0;
        delta=std::max(-0.5,std::min(0.5,delta));
        const double freq=(double(best)+delta)*double(rate)/double(m);
        if(freq<opt.minHz || freq>=double(rate)*0.499999 || freq>96000.0) break;
        double amp=0.0,phase=0.0;
        if(!fitSine(residual,win,double(rate),freq,amp,phase)) break;
        if(amp<threshold || !std::isfinite(amp)) break;
        const Component q=quantized(freq,amp,phase);
        if(q.a<=0.0) break;
        comps.push_back(q);
        // Subtract the *quantized* component, not its unquantized fit.
        const double omega=TAU*q.f/double(rate);
        double s,c,ds,dc; makeOsc(omega,q.p,s,c,ds,dc);
        for(size_t i=0;i<n;i++) {
            residual[i]-=q.a*s;
            advanceOsc(s,c,ds,dc);
            if((i&127u)==127u) { const double norm=1.0/std::hypot(s,c); s*=norm; c*=norm; }
        }
    }
    std::sort(comps.begin(),comps.end(),[](const Component& a,const Component& b){return a.f<b.f;});
    return comps;
}

static double wrapSignedPhase(double p) {
    p = std::remainder(p, TAU);
    if (p <= -PI) p += TAU;
    if (p > PI) p -= TAU;
    return p;
}

struct TrackState {
    uint64_t id = 0;
    uint64_t lastFrame = 0;
    uint64_t previousFrame = 0;
    double lastFrequency = 0.0;
    double previousFrequency = 0.0;
    double lastAmplitude = 0.0;
    double lastPhase = 0.0;
};

struct TrackPair {
    size_t trackIndex = 0;
    size_t componentIndex = 0;
    double score = 0.0;
    double predictedFrequency = 0.0;
    double predictedPhase = 0.0;
    double frequencyGate = 0.0;
    double phaseDerivedFrequency = 0.0;
    bool phaseFrequencyValid = false;
};

class TemporalTracker {
public:
    TemporalTracker(uint32_t rate, size_t hop, size_t frameSize, size_t fftSize,
                    bool useHungarian)
        : rate_(rate), hop_(hop), frameSize_(frameSize), fftSize_(fftSize),
          useHungarian_(useHungarian) {}

    std::vector<uint64_t> apply(uint64_t frameIndex, std::vector<Component>& components,
                                bool experimentalRefine) {
        const size_t trackCount = tracks_.size();
        const size_t componentCount = components.size();
        if (useHungarian_ && (trackCount > 256 || componentCount > 256)) {
            throw std::runtime_error(
                "Hungarian tracker is limited to 256 active tracks and 256 components per channel/frame; use greedy mode for larger limits");
        }
        const double unmatchedCost = 1.120001;
        std::vector<TrackPair> pairs;
        pairs.reserve(trackCount * componentCount);
        std::vector<std::vector<TrackPair>> pairInfo(
            trackCount, std::vector<TrackPair>(componentCount));
        // Hungarian mode receives one private dummy column per track, so every
        // track can remain unmatched without blocking another track's dummy.
        std::vector<std::vector<double>> costs(
            trackCount, std::vector<double>(componentCount + trackCount, unmatchedCost));
        std::vector<uint64_t> componentTrackIds(componentCount, 0);
        const double binHz = double(rate_) / double(fftSize_);

        for (size_t ti = 0; ti < trackCount; ++ti) {
            const auto& t = tracks_[ti];
            if (frameIndex <= t.lastFrame) continue;
            const uint64_t gapFrames = frameIndex - t.lastFrame;
            if (gapFrames > maxGapFrames_ + 1) continue;

            double slope = 0.0;
            if (t.lastFrame > t.previousFrame) {
                slope = (t.lastFrequency - t.previousFrequency) /
                        double(t.lastFrame - t.previousFrame);
            }
            const double maxSlope = std::max(2.0 * binHz, t.lastFrequency * 0.08);
            slope = std::max(-maxSlope, std::min(maxSlope, slope));
            const double dtFrames = double(gapFrames);
            const double predictedFrequency = std::max(0.0, t.lastFrequency + slope * dtFrames);
            const double meanFrequency = 0.5 * (t.lastFrequency + predictedFrequency);
            const double predictedPhase = t.lastPhase + TAU * meanFrequency *
                (dtFrames * double(hop_)) / double(rate_);
            const double frequencyGate = std::max(
                2.5 * binHz,
                0.025 * std::max(predictedFrequency, 1.0) + 0.5 * std::abs(slope) * dtFrames
            );

            for (size_t ci = 0; ci < componentCount; ++ci) {
                const auto& c = components[ci];
                const double frequencyError = std::abs(c.f - predictedFrequency);
                if (frequencyError > frequencyGate) continue;
                const double phaseError = std::abs(wrapSignedPhase(c.p - predictedPhase));
                const double ampError = std::abs(std::log(
                    (c.a + 1e-8) / (t.lastAmplitude + 1e-8)));
                const double score = 0.62 * (frequencyError / frequencyGate) +
                    0.30 * (phaseError / PI) + 0.08 * std::min(1.0, ampError / 2.0);

                // Unwrap measured phase advance using the predicted frequency to
                // choose the integer cycle count. This remains diagnostic unless
                // the explicit experimental refinement flag is enabled.
                const double deltaSamples = dtFrames * double(hop_);
                const double observedPhaseDelta = wrapSignedPhase(c.p - t.lastPhase);
                const double predictedAverageFrequency = 0.5 * (t.lastFrequency + predictedFrequency);
                const double estimatedCycles = predictedAverageFrequency * deltaSamples / double(rate_) -
                                               observedPhaseDelta / TAU;
                const double cycles = std::floor(estimatedCycles + 0.5);
                const double unwrappedPhaseDelta = observedPhaseDelta + TAU * cycles;
                const double phaseDerivedFrequency = unwrappedPhaseDelta * double(rate_) /
                                                     (TAU * deltaSamples);
                const bool phaseFrequencyValid =
                    std::min(c.a, t.lastAmplitude) >= 0.02 &&
                    ampError <= 0.6931471805599453 &&
                    std::isfinite(phaseDerivedFrequency) &&
                    std::abs(phaseDerivedFrequency - predictedAverageFrequency) <=
                    std::max(frequencyGate, 2.0 * binHz);

                if (score <= 1.12) {
                    TrackPair pair{ti, ci, score, predictedFrequency,
                                   wrapPhase(predictedPhase), frequencyGate,
                                   phaseDerivedFrequency, phaseFrequencyValid};
                    pairs.push_back(pair);
                    pairInfo[ti][ci] = pair;
                    costs[ti][ci] = score;
                }
            }
        }

        std::vector<const TrackPair*> matched(componentCount, nullptr);
        if (useHungarian_) {
            const std::vector<int> assignment = hungarianAssignment(costs);
            for (size_t ti = 0; ti < assignment.size(); ++ti) {
                const int assignedColumn = assignment[ti];
                if (assignedColumn < 0 || static_cast<size_t>(assignedColumn) >= componentCount) continue;
                const size_t ci = static_cast<size_t>(assignedColumn);
                if (costs[ti][ci] >= unmatchedCost) continue;
                matched[ci] = &pairInfo[ti][ci];
            }
        } else {
            std::sort(pairs.begin(), pairs.end(), [](const TrackPair& a, const TrackPair& b) {
                if (a.score != b.score) return a.score < b.score;
                if (a.trackIndex != b.trackIndex) return a.trackIndex < b.trackIndex;
                return a.componentIndex < b.componentIndex;
            });
            std::vector<bool> componentUsed(componentCount, false);
            std::vector<bool> trackUsed(trackCount, false);
            for (const auto& pair : pairs) {
                if (trackUsed[pair.trackIndex] || componentUsed[pair.componentIndex]) continue;
                trackUsed[pair.trackIndex] = true;
                componentUsed[pair.componentIndex] = true;
                matched[pair.componentIndex] = &pair;
            }
        }

        // Update only matched existing tracks. New tracks are appended afterward.
        for (size_t ci = 0; ci < componentCount; ++ci) {
            auto& c = components[ci];
            const TrackPair* pair = matched[ci];
            if (!pair) continue;

            auto& t = tracks_[pair->trackIndex];
            const double measuredPhase = c.p;
            const double measuredFrequency = c.f;
            if (experimentalRefine && pair->phaseFrequencyValid) {
                const double phaseFrequencyWeight =
                    (frameIndex - t.lastFrame == 1) ? 0.70 : 0.35;
                const double refinedFrequency = c.f * (1.0 - phaseFrequencyWeight) +
                    pair->phaseDerivedFrequency * phaseFrequencyWeight;
                const double centerSample = 0.5 * double(frameSize_ - 1);
                const double adjustedPhase = wrapPhase(measuredPhase + TAU *
                    (measuredFrequency - refinedFrequency) * centerSample / double(rate_));
                c = quantized(refinedFrequency, c.a, adjustedPhase);
            }

            t.previousFrame = t.lastFrame;
            t.previousFrequency = t.lastFrequency;
            t.lastFrame = frameIndex;
            t.lastFrequency = c.f;
            t.lastAmplitude = c.a;
            t.lastPhase = measuredPhase;
            componentTrackIds[ci] = t.id;
            matched_++;
        }

        for (size_t ci = 0; ci < componentCount; ++ci) {
            if (matched[ci]) continue;
            const auto& c = components[ci];
            TrackState t;
            t.id = nextId_++;
            t.lastFrame = frameIndex;
            t.previousFrame = frameIndex;
            t.lastFrequency = c.f;
            t.previousFrequency = c.f;
            t.lastAmplitude = c.a;
            t.lastPhase = c.p;
            componentTrackIds[ci] = t.id;
            tracks_.push_back(t);
            created_++;
        }
        tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(),
            [frameIndex, this](const TrackState& t) {
                return frameIndex > t.lastFrame && frameIndex - t.lastFrame > maxGapFrames_ + 1;
            }), tracks_.end());
        return componentTrackIds;
    }

    uint64_t matchedCount() const { return matched_; }
    uint64_t createdCount() const { return created_; }

private:
    static std::vector<int> hungarianAssignment(const std::vector<std::vector<double>>& matrix) {
        const size_t n = matrix.size();
        if (n == 0) return {};
        const size_t m = matrix.front().size();
        if (m < n) throw std::runtime_error("Hungarian assignment requires columns >= rows");
        const double inf = std::numeric_limits<double>::infinity();
        std::vector<double> u(n + 1, 0.0), v(m + 1, 0.0);
        std::vector<size_t> p(m + 1, 0), way(m + 1, 0);
        for (size_t i = 1; i <= n; ++i) {
            p[0] = i;
            size_t j0 = 0;
            std::vector<double> minv(m + 1, inf);
            std::vector<bool> used(m + 1, false);
            do {
                used[j0] = true;
                const size_t i0 = p[j0];
                double delta = inf;
                size_t j1 = 0;
                for (size_t j = 1; j <= m; ++j) {
                    if (used[j]) continue;
                    const double current = matrix[i0 - 1][j - 1] - u[i0] - v[j];
                    if (current < minv[j]) {
                        minv[j] = current;
                        way[j] = j0;
                    }
                    if (minv[j] < delta) {
                        delta = minv[j];
                        j1 = j;
                    }
                }
                if (!std::isfinite(delta)) throw std::runtime_error("Hungarian assignment has no finite path");
                for (size_t j = 0; j <= m; ++j) {
                    if (used[j]) {
                        u[p[j]] += delta;
                        v[j] -= delta;
                    } else {
                        minv[j] -= delta;
                    }
                }
                j0 = j1;
            } while (p[j0] != 0);
            do {
                const size_t j1 = way[j0];
                p[j0] = p[j1];
                j0 = j1;
            } while (j0 != 0);
        }
        std::vector<int> assignment(n, -1);
        for (size_t j = 1; j <= m; ++j) {
            if (p[j] != 0) assignment[p[j] - 1] = static_cast<int>(j - 1);
        }
        return assignment;
    }

    uint32_t rate_;
    size_t hop_;
    size_t frameSize_;
    size_t fftSize_;
    bool useHungarian_ = false;
    uint64_t nextId_ = 1;
    uint64_t matched_ = 0;
    uint64_t created_ = 0;
    uint64_t maxGapFrames_ = 2;
    std::vector<TrackState> tracks_;
};

static std::vector<Component> shiftComponents(const std::vector<Component>& source,
                                                double shiftSeconds) {
    std::vector<Component> result;
    result.reserve(source.size());
    for (const auto& c : source) {
        result.push_back(quantized(c.f, c.a, c.p + TAU * c.f * shiftSeconds));
    }
    std::sort(result.begin(), result.end(), [](const Component& a, const Component& b) { return a.f < b.f; });
    return result;
}

static void writeComponent(std::ostream& out,const Component& c) {
    const uint32_t qf=static_cast<uint32_t>(roundPositive(c.f/96000.0*0xFFFFFF));
    const uint32_t qa=static_cast<uint32_t>(roundPositive(c.a*0x3FFF));
    const uint32_t qp=static_cast<uint32_t>(roundPositive(wrapPhase(c.p)/TAU*1024.0));
    const uint64_t bits=uint64_t(qf)|(uint64_t(qa)<<24)|(uint64_t(std::min<uint32_t>(1023,qp))<<38);
    for(int i=0;i<6;i++) out.put(char((bits>>(8*i))&255));
}

static void usage() {
    std::cerr << "KASF Fast Baseline Generator (C++17)\n"
              << "Usage: kasf_fastgen INPUT.wav OUTPUT.kasf [--frame-ms 10] [--max-components 48]\n"
              << "       [--threshold-db -58] [--min-hz 15] [--edge-pad] [--no-tracking]\n"
              << "       [--track-map OUTPUT.jsonl] [--tracker-assignment greedy|hungarian]\n"
              << "       [--experimental-track-refine]\n"
              << "       [--base-wav OUTPUT.wav] [--force]\n";
}

int main(int argc,char** argv) {
 try {
    if(argc<3) { usage(); return 2; }
    const fs::path input=argv[1], output=argv[2]; Options opt;
    for(int i=3;i<argc;i++) {
        const std::string a=argv[i];
        auto val=[&]()->std::string { if(i+1>=argc) throw std::runtime_error("Missing value for "+a); return argv[++i]; };
        if(a=="--frame-ms") opt.frameMs=std::stod(val());
        else if(a=="--max-components") opt.maxComponents=std::stoi(val());
        else if(a=="--threshold-db") opt.thresholdDb=std::stod(val());
        else if(a=="--min-hz") opt.minHz=std::stod(val());
        else if(a=="--force") opt.force=true;
        else if(a=="--edge-pad") opt.edgePad=true;
        else if(a=="--no-tracking") opt.temporalTracking=false;
        else if(a=="--experimental-track-refine") opt.experimentalTrackRefine=true;
        else if(a=="--track-map") opt.trackMap=val();
        else if(a=="--tracker-assignment") opt.trackerAssignment=val();
        else if(a=="--base-wav") opt.baseWav=val();
        else throw std::runtime_error("Unknown option: "+a);
    }
    if(!std::isfinite(opt.frameMs)||opt.frameMs<1.0||opt.frameMs>100.0) throw std::runtime_error("frame-ms must be between 1 and 100");
    if(opt.maxComponents<1||opt.maxComponents>4096) throw std::runtime_error("max-components must be 1..4096");
    if(!std::isfinite(opt.thresholdDb)||opt.thresholdDb < -140.0||opt.thresholdDb>0.0) throw std::runtime_error("threshold-db must be -140..0");
    if(!std::isfinite(opt.minHz)||opt.minHz<0.0||opt.minHz>96000.0) throw std::runtime_error("min-hz must be between 0 and 96000");
    if(fs::exists(output)&&!opt.force) throw std::runtime_error("Output exists; pass --force to replace it");
    if(!opt.baseWav.empty() && (fs::absolute(opt.baseWav)==fs::absolute(input) || fs::absolute(opt.baseWav)==fs::absolute(output)))
        throw std::runtime_error("Base WAV path must differ from input and KASF output");
    if(!opt.trackMap.empty() && (fs::absolute(opt.trackMap)==fs::absolute(input) ||
       fs::absolute(opt.trackMap)==fs::absolute(output) ||
       (!opt.baseWav.empty() && fs::absolute(opt.trackMap)==fs::absolute(opt.baseWav))))
        throw std::runtime_error("Track map path must differ from input, KASF, and Base WAV");
    if (opt.trackerAssignment != "greedy" && opt.trackerAssignment != "hungarian")
        throw std::runtime_error("tracker-assignment must be greedy or hungarian");
    if(!opt.trackMap.empty() && !opt.temporalTracking)
        throw std::runtime_error("--track-map requires temporal tracking; remove --no-tracking");
    if(opt.experimentalTrackRefine && !opt.temporalTracking)
        throw std::runtime_error("--experimental-track-refine requires temporal tracking");
    if(!opt.baseWav.empty() && fs::exists(opt.baseWav) && !opt.force) throw std::runtime_error("Base WAV exists; pass --force to replace it");
    if(!opt.trackMap.empty() && fs::exists(opt.trackMap) && !opt.force) throw std::runtime_error("Track map exists; pass --force to replace it");
    if(!fs::exists(input)) throw std::runtime_error("Input file does not exist");
    const WavInfo w=parseWav(input);
    if(!opt.baseWav.empty() && w.format!=1)
        throw std::runtime_error("--base-wav bridge currently requires integer PCM WAV input");
    const size_t N=std::max<uint64_t>(1,roundPositive(double(w.rate)*opt.frameMs/1000.0));
    const size_t H=std::max<uint64_t>(1,roundPositive(double(w.rate)*opt.frameMs/2000.0));
    const uint64_t padSamples=opt.edgePad?H:0;
    if (w.samples > std::numeric_limits<uint64_t>::max()-2*padSamples) throw std::runtime_error("Padded timeline overflow");
    const uint64_t timelineSamples=w.samples+2*padSamples;
    const uint64_t frameCount=timelineSamples<=N?1:((timelineSamples-N+H-1)/H+1);
    const size_t M=nextPow2(N);
    const double threshold=std::pow(10.0,opt.thresholdDb/20.0);
    std::vector<double> win(N), hannDummy;
    double winSum=0;
    for(size_t i=0;i<N;i++){win[i]=0.5-0.5*std::cos(TAU*double(i)/double(N));winSum+=win[i];}
    std::vector<std::vector<double>> window(w.channels,std::vector<double>(N,0.0));
    std::vector<std::vector<Component>> frame(w.channels);
    std::vector<std::complex<double>> spec(M);
    std::ifstream wav(input,std::ios::binary);
    if(!wav) throw std::runtime_error("Cannot reopen input WAV");
    std::vector<std::vector<Component>> preRoll(w.channels), lastFull(w.channels);
    std::vector<TemporalTracker> trackers;
    trackers.reserve(w.channels);
    for (uint16_t ch=0; ch<w.channels; ++ch) trackers.emplace_back(w.rate,H,N,M,opt.trackerAssignment=="hungarian");
    const uint64_t lastFullSourceStart=w.samples>N?((w.samples-N)/H)*H:0;
    const uint64_t lastFullFileFrame=lastFullSourceStart/H+1;
    if(opt.edgePad) {
        std::vector<std::vector<double>> firstSource(w.channels,std::vector<double>(N,0.0));
        std::vector<std::vector<double>> lastSource(w.channels,std::vector<double>(N,0.0));
        readRange(wav,w,0,std::min<uint64_t>(N,w.samples),firstSource,0);
        readRange(wav,w,lastFullSourceStart,std::min<uint64_t>(N,w.samples-lastFullSourceStart),lastSource,0);
        for(uint16_t ch=0;ch<w.channels;ch++) {
            const auto firstSeed=analyzeFrame(firstSource[ch],win,spec,w.rate,opt,threshold);
            preRoll[ch]=shiftComponents(firstSeed,-double(H)/double(w.rate));
            lastFull[ch]=analyzeFrame(lastSource[ch],win,spec,w.rate,opt,threshold);
        }
    }
    const uint64_t firstRead=opt.edgePad?std::min<uint64_t>(N-H,w.samples):std::min<uint64_t>(N,w.samples);
    readRange(wav,w,0,firstRead,window,opt.edgePad?H:0);
    uint64_t nextUnread=firstRead;
    fs::path temp=output; temp += ".part";
    fs::path tempBase=opt.baseWav; if(!tempBase.empty()) tempBase += ".part";
    fs::path tempTrackMap=opt.trackMap; if(!tempTrackMap.empty()) tempTrackMap += ".part";
    TempCleanup cleanup{{temp, tempBase, tempTrackMap}, false};
    if(fs::exists(temp)) fs::remove(temp);
    if(!tempBase.empty() && fs::exists(tempBase)) fs::remove(tempBase);
    if(!tempTrackMap.empty() && fs::exists(tempTrackMap)) fs::remove(tempTrackMap);
    std::ofstream out(temp,std::ios::binary|std::ios::trunc);
    if(!out) throw std::runtime_error("Cannot create output file");
    std::ofstream baseOut;
    std::ofstream trackMapOut;
    if (!tempTrackMap.empty()) {
        trackMapOut.open(tempTrackMap, std::ios::binary | std::ios::trunc);
        if (!trackMapOut) throw std::runtime_error("Cannot create track map output");
    }
    std::vector<std::vector<double>> olaRing;
    std::vector<uint8_t> baseBuffer;
    uint64_t baseCursor=0;
    if(!tempBase.empty()) {
        if(w.format!=1) throw std::runtime_error("--base-wav bridge currently requires integer PCM input");
        baseOut.open(tempBase,std::ios::binary|std::ios::trunc);
        if(!baseOut) throw std::runtime_error("Cannot create Base WAV output");
        writePcmWavHeader(baseOut,w,w.samples);
        const size_t ringSize=N+H+2;
        olaRing.assign(w.channels,std::vector<double>(ringSize,0.0));
        baseBuffer.reserve(65536);
    }
    out.write("KASF",4); writeU32(out,1); writeU64(out,w.channels); writeU64(out,frameCount); writeF64(out,opt.frameMs/1000.0);
    uint64_t totalComponents=0; const auto begin=std::chrono::steady_clock::now();
    for(uint64_t m=0;m<frameCount;m++) {
        std::vector<std::vector<uint64_t>> frameTrackIds(w.channels);
        for(uint16_t ch=0;ch<w.channels;ch++) {
            if(opt.edgePad && m==0) frame[ch]=preRoll[ch];
            else if(opt.edgePad && m==lastFullFileFrame) frame[ch]=lastFull[ch];
            else if(opt.edgePad && m>lastFullFileFrame)
                frame[ch]=shiftComponents(lastFull[ch],double((m-lastFullFileFrame)*H)/double(w.rate));
            else frame[ch]=analyzeFrame(window[ch],win,spec,w.rate,opt,threshold);
            if (opt.temporalTracking) {
                frameTrackIds[ch] = trackers[ch].apply(m, frame[ch], opt.experimentalTrackRefine);
            }
        }
        if (trackMapOut.is_open()) {
            for (uint16_t ch=0; ch<w.channels; ++ch) {
                trackMapOut << "{\"frame\":" << m << ",\"channel\":" << ch << ",\"track_ids\":[";
                for (size_t i=0; i<frameTrackIds[ch].size(); ++i) {
                    if (i) trackMapOut << ',';
                    trackMapOut << frameTrackIds[ch][i];
                }
                trackMapOut << "]}\n";
            }
        }
        for(uint16_t ch=0;ch<w.channels;ch++) {
            writeU64(out,frame[ch].size());
            for(const auto& c:frame[ch]) writeComponent(out,c);
            totalComponents+=frame[ch].size();
        }
        if(!out) throw std::runtime_error("KASF write failed");
        if(!tempBase.empty()) {
            const size_t ringSize=olaRing[0].size();
            for(uint16_t ch=0;ch<w.channels;ch++) {
                for(size_t local=0;local<N;local++) {
                    const uint64_t global=m*H+local;
                    if(global>=timelineSamples) break;
                    double total=0.0;
                    for(const auto& c:frame[ch])
                        if(c.a>0.0) total += c.a*std::sin(TAU*c.f*(double(local)/double(w.rate))+c.p);
                    olaRing[ch][global%ringSize] += win[local]*total;
                }
            }
            const uint64_t flushUntil=std::min<uint64_t>((m+1)*H,timelineSamples);
            while(baseCursor<flushUntil) {
                if(baseCursor>=padSamples && baseCursor<padSamples+w.samples) {
                    for(uint16_t ch=0;ch<w.channels;ch++)
                        appendPcmSample(baseBuffer,olaRing[ch][baseCursor%ringSize],w.bits);
                }
                for(uint16_t ch=0;ch<w.channels;ch++) olaRing[ch][baseCursor%ringSize]=0.0;
                ++baseCursor;
                if(baseBuffer.size()>=65536) {
                    baseOut.write(reinterpret_cast<const char*>(baseBuffer.data()),static_cast<std::streamsize>(baseBuffer.size()));
                    baseBuffer.clear();
                }
            }
        }
        if(m+1<frameCount) {
            for(uint16_t ch=0;ch<w.channels;ch++) {
                if(H<N) std::memmove(window[ch].data(),window[ch].data()+H,(N-H)*sizeof(double));
                std::fill(window[ch].begin()+(N-H),window[ch].end(),0.0);
            }
            const uint64_t count=nextUnread<w.samples?std::min<uint64_t>(H,w.samples-nextUnread):0;
            if(count) { readRange(wav,w,nextUnread,count,window,N-H); nextUnread+=count; }
        }
        if((m+1)%std::max<uint64_t>(1,frameCount/10)==0 || m+1==frameCount)
            std::cerr << "progress " << (100.0*double(m+1)/double(frameCount)) << "%\r" << std::flush;
    }
    if(!tempBase.empty() && baseCursor<timelineSamples) {
        const size_t ringSize=olaRing[0].size();
        while(baseCursor<timelineSamples) {
            if(baseCursor>=padSamples && baseCursor<padSamples+w.samples) {
                for(uint16_t ch=0;ch<w.channels;ch++)
                    appendPcmSample(baseBuffer,olaRing[ch][baseCursor%ringSize],w.bits);
            }
            for(uint16_t ch=0;ch<w.channels;ch++) olaRing[ch][baseCursor%ringSize]=0.0;
            ++baseCursor;
            if(baseBuffer.size()>=65536) {
                baseOut.write(reinterpret_cast<const char*>(baseBuffer.data()),static_cast<std::streamsize>(baseBuffer.size()));
                baseBuffer.clear();
            }
        }
    }
    if(!tempBase.empty() && !baseBuffer.empty()) {
        baseOut.write(reinterpret_cast<const char*>(baseBuffer.data()),static_cast<std::streamsize>(baseBuffer.size()));
        baseBuffer.clear();
    }
    out.flush(); if(!out) throw std::runtime_error("KASF flush failed"); out.close();
    if(!tempBase.empty()) { baseOut.flush(); if(!baseOut) throw std::runtime_error("Base WAV flush failed"); baseOut.close(); }
    if(trackMapOut.is_open()) { trackMapOut.flush(); if(!trackMapOut) throw std::runtime_error("Track map flush failed"); trackMapOut.close(); }
    if(opt.force && fs::exists(output)) fs::remove(output);
    if(opt.force && !opt.baseWav.empty() && fs::exists(opt.baseWav)) fs::remove(opt.baseWav);
    if(opt.force && !opt.trackMap.empty() && fs::exists(opt.trackMap)) fs::remove(opt.trackMap);
    fs::rename(temp,output);
    if(!tempBase.empty()) fs::rename(tempBase,opt.baseWav);
    if(!tempTrackMap.empty()) fs::rename(tempTrackMap,opt.trackMap);
    cleanup.released=true;
    const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
    const uint64_t bytes=fs::file_size(output);
    std::cout << std::setprecision(8)
              << "{\"status\":\"ok\",\"format\":\"KASF v1\",\"magic\":\"KASF\","
              << "\"sample_rate_hz\":"<<w.rate<<",\"channels\":"<<w.channels<<",\"sample_count\":"<<w.samples<<"," 
              << "\"frame_size\":"<<N<<",\"hop_samples\":"<<H<<",\"frame_count\":"<<frameCount<<"," 
              << "\"edge_padding_samples\":"<<padSamples<<",\"analysis_timeline_sample_count\":"<<timelineSamples<<"," 
              << "\"components\":"<<totalComponents<<",\"file_bytes\":"<<bytes<<",\"elapsed_seconds\":"<<elapsed<<"," 
              << "\"threshold_db\":"<<opt.thresholdDb<<",\"max_components_per_frame\":"<<opt.maxComponents
              << ",\"temporal_tracking_enabled\":"<<(opt.temporalTracking?"true":"false")
              << ",\"temporal_tracker_assignment\":\""<<opt.trackerAssignment<<"\""
              << ",\"temporal_tracks_created\":";
    uint64_t tracksCreated=0, tracksMatched=0;
    for (const auto& tracker : trackers) { tracksCreated += tracker.createdCount(); tracksMatched += tracker.matchedCount(); }
    std::cout << tracksCreated << ",\"temporal_matches\":" << tracksMatched
              << ",\"temporal_refinement_enabled\":"<<(opt.experimentalTrackRefine?"true":"false")
              << ",\"track_map_written\":"<<(!opt.trackMap.empty()?"true":"false")
              << ",\"base_wav_written\":"<<(!opt.baseWav.empty()?"true":"false")<<"}\n";
    return 0;
 } catch(const std::exception& e) { std::cerr << "ERROR: " << e.what() << "\n"; return 1; }
}
