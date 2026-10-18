// InstaReframeX6 OFX plugin — v1: MEI-calibrated reframe from X6 combined
// dual-fisheye frame (front=left half, back=right half).
// Math replicated from the verified InstaReframeX6.fuse DCTL kernel.
// SPDX-License-Identifier: MIT
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#endif

#include <cstring>
#include <cstdio>
#include <cmath>
#include <atomic>
#include <thread>
#include <vector>
#include <string>
#include <fstream>
#include "ofxsImageEffect.h"
#include "ofxsMultiThread.h"
#include "ofxsProcessing.h"

using namespace OFX;

static const float PI = 3.14159265358979f;
static const char *LOGPATH = "C:/Users/stefa/AppData/Local/Temp/reframe_ofx.log";

static void plog(const char *fmt, double t, double a, double b, double c, double d, const char *s) {
    FILE *f = fopen(LOGPATH, "a");
    if (f) { fprintf(f, fmt, t, a, b, c, d, s); fclose(f); }
}

// ---------- calibration ----------
struct Calib {
    float fxi, ffx, ffy, fcx, fcy, fk1, fk2, fk3, fk4, fp1, fp2, fs1, fs2, fs3, fs4;
    float bxi, bfx, bfy, bcx, bcy, bk1, bk2, bk3, bk4, bp1, bp2, bs1, bs2, bs3, bs4;
    float fm[9], bm[9];
    // verified X6 default (VID_20260918_205557_00_014)
    Calib() {
        fxi=2.45543f; ffx=3611.11f; ffy=3611.11f; fcx=1926.45f; fcy=1939.42f;
        fk1=1.31325f; fk2=-1.59305f; fk3=6.99536f; fk4=-2.58052f;
        fp1=-0.00102256f; fp2=-0.00163018f;
        fs1=-0.00392101f; fs2=0.0146974f; fs3=0.00406541f; fs4=0.00244077f;
        bxi=2.45543f; bfx=3603.76f; bfy=3603.76f; bcx=1930.63f; bcy=1943.50f;
        bk1=1.27913f; bk2=-0.752754f; bk3=0.472147f; bk4=15.4547f;
        bp1=0.00126113f; bp2=0.00033189f;
        bs1=-0.0065367f; bs2=0.0131532f; bs3=-0.00036284f; bs4=-0.00159663f;
        fm[0]=0.999973f; fm[1]=0.0f; fm[2]=-0.007295f; fm[3]=-0.000023f; fm[4]=0.999995f;
        fm[5]=-0.003142f; fm[6]=0.007295f; fm[7]=0.003142f; fm[8]=0.999968f;
        bm[0]=-0.999986f; bm[1]=0.0f; bm[2]=-0.005288f; bm[3]=-0.000016f; bm[4]=0.999995f;
        bm[5]=0.003107f; bm[6]=0.005288f; bm[7]=0.003107f; bm[8]=-0.999981f;
    }
};

// parse key=value lines (.calib format, keys front_xi..front_m8, back_xi..back_m8)
static Calib loadCalib(const std::string &path) {
    Calib c;
    if (path.empty()) return c;
    std::ifstream in(path.c_str());
    if (!in) return c;
    std::string line;
    while (std::getline(in, line)) {
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = line.substr(0, eq);
        std::string v = line.substr(eq + 1);
        while (!k.empty() && isspace(k.back())) k.pop_back();
        while (!v.empty() && isspace(v.front())) v.erase(v.begin());
        float val = (float)atof(v.c_str());
        if (k == "front_xi") c.fxi = val;
        else if (k == "front_fx") c.ffx = val;
        else if (k == "front_fy") c.ffy = val;
        else if (k == "front_cx") c.fcx = val;
        else if (k == "front_cy") c.fcy = val;
        else if (k == "front_k1") c.fk1 = val;
        else if (k == "front_k2") c.fk2 = val;
        else if (k == "front_k3") c.fk3 = val;
        else if (k == "front_k4") c.fk4 = val;
        else if (k == "front_p1") c.fp1 = val;
        else if (k == "front_p2") c.fp2 = val;
        else if (k == "front_s1") c.fs1 = val;
        else if (k == "front_s2") c.fs2 = val;
        else if (k == "front_s3") c.fs3 = val;
        else if (k == "front_s4") c.fs4 = val;
        else if (k == "front_m0") c.fm[0] = val;
        else if (k == "front_m1") c.fm[1] = val;
        else if (k == "front_m2") c.fm[2] = val;
        else if (k == "front_m3") c.fm[3] = val;
        else if (k == "front_m4") c.fm[4] = val;
        else if (k == "front_m5") c.fm[5] = val;
        else if (k == "front_m6") c.fm[6] = val;
        else if (k == "front_m7") c.fm[7] = val;
        else if (k == "front_m8") c.fm[8] = val;
        else if (k == "back_xi") c.bxi = val;
        else if (k == "back_fx") c.bfx = val;
        else if (k == "back_fy") c.bfy = val;
        else if (k == "back_cx") c.bcx = val;
        else if (k == "back_cy") c.bcy = val;
        else if (k == "back_k1") c.bk1 = val;
        else if (k == "back_k2") c.bk2 = val;
        else if (k == "back_k3") c.bk3 = val;
        else if (k == "back_k4") c.bk4 = val;
        else if (k == "back_p1") c.bp1 = val;
        else if (k == "back_p2") c.bp2 = val;
        else if (k == "back_s1") c.bs1 = val;
        else if (k == "back_s2") c.bs2 = val;
        else if (k == "back_s3") c.bs3 = val;
        else if (k == "back_s4") c.bs4 = val;
        else if (k == "back_m0") c.bm[0] = val;
        else if (k == "back_m1") c.bm[1] = val;
        else if (k == "back_m2") c.bm[2] = val;
        else if (k == "back_m3") c.bm[3] = val;
        else if (k == "back_m4") c.bm[4] = val;
        else if (k == "back_m5") c.bm[5] = val;
        else if (k == "back_m6") c.bm[6] = val;
        else if (k == "back_m7") c.bm[7] = val;
        else if (k == "back_m8") c.bm[8] = val;
    }
    return c;
}

// ---------- pixel access ----------
static inline void getPixel(const Image *img, int x, int y, float rgba[4]) {
    const void *p = img->getPixelAddress(x, y);
    int n = img->getPixelComponentCount();
    for (int i = 0; i < 4; i++) rgba[i] = (i == 3) ? 1.0f : 0.0f;
    if (!p) return;
    switch (img->getPixelDepth()) {
        case eBitDepthUByte:  { const unsigned char *q = (const unsigned char*)p; for (int i=0;i<n;i++) rgba[i] = q[i] / 255.0f; break; }
        case eBitDepthUShort: { const unsigned short *q = (const unsigned short*)p; for (int i=0;i<n;i++) rgba[i] = q[i] / 65535.0f; break; }
        case eBitDepthFloat:  { const float *q = (const float*)p; for (int i=0;i<n;i++) rgba[i] = q[i]; break; }
        default: break;
    }
}

static inline void putPixel(Image *img, int x, int y, const float rgba[4]) {
    void *p = img->getPixelAddress(x, y);
    int n = img->getPixelComponentCount();
    if (!p) return;
    auto cl = [](float v) { return v < 0.f ? 0.f : (v > 1.f ? 1.f : v); };
    switch (img->getPixelDepth()) {
        case eBitDepthUByte:  { unsigned char *q = (unsigned char*)p; for (int i=0;i<n;i++) q[i] = (unsigned char)(cl(rgba[i])*255.0f + 0.5f); break; }
        case eBitDepthUShort: { unsigned short *q = (unsigned short*)p; for (int i=0;i<n;i++) q[i] = (unsigned short)(cl(rgba[i])*65535.0f + 0.5f); break; }
        case eBitDepthFloat:  { float *q = (float*)p; for (int i=0;i<n;i++) q[i] = rgba[i]; break; }
        default: break;
    }
}

static void sampleBilinear(const Image *src, float u, float v, float out[4]) {
    OfxRectI b = src->getBounds();
    int x0 = (int)std::floor(u), y0 = (int)std::floor(v);
    int x1 = x0 + 1, y1 = y0 + 1;
    auto clx = [&](int x) { return x < b.x1 ? b.x1 : (x > b.x2 - 1 ? b.x2 - 1 : x); };
    auto cly = [&](int y) { return y < b.y1 ? b.y1 : (y > b.y2 - 1 ? b.y2 - 1 : y); };
    float fx = u - x0, fy = v - y0;
    float p00[4], p10[4], p01[4], p11[4];
    getPixel(src, clx(x0), cly(y0), p00);
    getPixel(src, clx(x1), cly(y0), p10);
    getPixel(src, clx(x0), cly(y1), p01);
    getPixel(src, clx(x1), cly(y1), p11);
    for (int i = 0; i < 4; i++)
        out[i] = (1-fx)*(1-fy)*p00[i] + fx*(1-fy)*p10[i] + (1-fx)*fy*p01[i] + fx*fy*p11[i];
}

// ---------- warp processor ----------
class WarpProcessor : public ImageProcessor {
    const Image *_srcImg;
    Calib _calib;
    float _fov, _pan, _tilt, _roll, _byaw, _bpitch; // degrees
public:
    WarpProcessor(ImageEffect &instance) : ImageProcessor(instance), _srcImg(0) {}
    void setSrcImg(const Image *v) { _srcImg = v; }
    void setCalib(const Calib &c) { _calib = c; }
    void setAngles(float fov, float pan, float tilt, float roll, float byaw, float bpitch) {
        _fov = fov; _pan = pan; _tilt = tilt; _roll = roll; _byaw = byaw; _bpitch = bpitch;
    }

    void multiThreadProcessImages(OfxRectI procWindow) {
        OfxRectI sb = _srcImg->getBounds();
        int srcW = sb.x2 - sb.x1, srcH = sb.y2 - sb.y1;
        float halfW = srcW * 0.5f;
        OfxRectI ob = _dstImg->getBounds();
        int outW = ob.x2 - ob.x1, outH = ob.y2 - ob.y1;

        float focal = (outH * 0.5f) / std::tan(_fov * 0.5f * PI / 180.0f);
        float cr = std::cos(_roll * PI / 180.0f), sr = std::sin(_roll * PI / 180.0f);
        float ct = std::cos(_tilt * PI / 180.0f), st = std::sin(_tilt * PI / 180.0f);
        float cp = std::cos(_pan * PI / 180.0f), sp = std::sin(_pan * PI / 180.0f);
        float rmax = std::min(halfW, (float)srcH) * 0.5f * 0.97f;
        std::atomic<long> written{0}, skipped{0};
        static long lastlog = 0;
        if (++lastlog <= 3) {
            FILE *f = fopen("C:/Users/stefa/AppData/Local/Temp/reframe_ofx.log", "a");
            if (f) { fprintf(f, "geom src=%dx%d dst=%dx%d depth=%d comp=%d rowbytes=%d proc=(%d,%d,%d,%d)\n",
                srcW, srcH, outW, outH, (int)_srcImg->getPixelDepth(), (int)_srcImg->getPixelComponentCount(),
                (int)_srcImg->getRowBytes(), procWindow.x1, procWindow.y1, procWindow.x2, procWindow.y2); fclose(f); }
        }

        auto warpRows = [&](int ya, int yb) {
        for (int y = ya; y < yb; y++) {
            if (_effect.abort()) break;
            for (int x = procWindow.x1; x < procWindow.x2; x++) {
                // direction ray (y-down convention, same as verified kernel)
                float dx = ((float)x - outW * 0.5f) / focal;
                float dy = ((float)y - outH * 0.5f) / focal;
                float dz = 1.0f;
                float x1 = cr*dx - sr*dy, y1 = sr*dx + cr*dy, z1 = dz;
                float x2 = x1, y2 = ct*y1 - st*z1, z2 = st*y1 + ct*z1;
                float x3 = cp*x2 + sp*z2, y3 = y2, z3 = -sp*x2 + cp*z2;
                float inv = 1.0f / std::sqrt(x3*x3 + y3*y3 + z3*z3);
                x3 *= inv; y3 *= inv; z3 *= inv;

                const float *m; float xi, fx, fy, cx, cy, k1, k2, k3, k4, p1, p2, s1, s2, s3, s4;
                bool front = (z3 >= 0.0f);
                if (front) {
                    m = _calib.fm;
                    xi=_calib.fxi; fx=_calib.ffx; fy=_calib.ffy; cx=_calib.fcx; cy=_calib.fcy;
                    k1=_calib.fk1; k2=_calib.fk2; k3=_calib.fk3; k4=_calib.fk4;
                    p1=_calib.fp1; p2=_calib.fp2; s1=_calib.fs1; s2=_calib.fs2; s3=_calib.fs3; s4=_calib.fs4;
                } else {
                    m = _calib.bm;
                    xi=_calib.bxi; fx=_calib.bfx; fy=_calib.bfy; cx=_calib.bcx; cy=_calib.bcy;
                    k1=_calib.bk1; k2=_calib.bk2; k3=_calib.bk3; k4=_calib.bk4;
                    p1=_calib.bp1; p2=_calib.bp2; s1=_calib.bs1; s2=_calib.bs2; s3=_calib.bs3; s4=_calib.bs4;
                }

                // Resolve feeds the source scaled to timeline resolution: adapt calibration
                // (reference lens image is 3840x3840) to the actual source size
                float sx = halfW / 3840.0f, sy = (float)srcH / 3840.0f;
                fx *= sx; cx *= sx; fy *= sy; cy *= sy;

                float Xl = m[0]*x3 + m[1]*y3 + m[2]*z3;
                float Yl = m[3]*x3 + m[4]*y3 + m[5]*z3;
                float Zl = m[6]*x3 + m[7]*y3 + m[8]*z3;

                if (!front) {
                    // seam fine-tune: extra yaw/pitch of back lens (deg -> rad)
                    float by = _byaw * PI / 180.0f, bp = _bpitch * PI / 180.0f;
                    if (by != 0.0f) {
                        float cyy = std::cos(by), syy = std::sin(by);
                        float Xr = cyy*Xl - syy*Zl, Zr = syy*Xl + cyy*Zl;
                        Xl = Xr; Zl = Zr;
                    }
                    if (bp != 0.0f) {
                        float cpp = std::cos(bp), spp = std::sin(bp);
                        float Yr = cpp*Yl - spp*Zl, Zr2 = spp*Yl + cpp*Zl;
                        Yl = Yr; Zl = Zr2;
                    }
                }

                float norm = std::sqrt(Xl*Xl + Yl*Yl + Zl*Zl);
                if (norm <= 1e-6f) { skipped++; continue; }
                float Xs = Xl/norm, Ys = Yl/norm, Zs = Zl/norm;
                float denom = Zs + xi;
                if (denom <= 1e-4f) { skipped++; continue; }
                float mx = Xs/denom, my = Ys/denom;
                float r2 = mx*mx + my*my, r4 = r2*r2;
                float radial = 1.0f + k1*r2 + k2*r4 + k3*r2*r4 + k4*r4*r4;
                float xd = mx*radial + 2.0f*p1*mx*my + p2*(r2 + 2.0f*mx*mx) + s1*r2 + s2*r4;
                float yd = my*radial + p1*(r2 + 2.0f*my*my) + 2.0f*p2*mx*my + s3*r2 + s4*r4;
                float u = fx*xd + cx, v = fy*yd + cy;

                // bounds in stream space: rmax circle + inside half frame
                float du = u - cx, dv = v - cy;
                if (std::sqrt(du*du + dv*dv) > rmax) { skipped++; continue; }
                if (u < 0.0f || u > halfW - 1.0f || v < 0.0f || v > srcH - 1.0f) { skipped++; continue; }

                // map stream coords to combined frame: front=left half, back=right half
                float uf = front ? u : u + halfW;
                float rgba[4];
                sampleBilinear(_srcImg, uf, v, rgba);
                putPixel(_dstImg, x, y, rgba);
                written++;
            }
        }
        };
        int nrows = procWindow.y2 - procWindow.y1;
        int nt = (int)std::thread::hardware_concurrency();
        if (nt > nrows) nt = nrows;
        if (nt < 1) nt = 1;
        std::vector<std::thread> th;
        for (int t = 0; t < nt; t++) {
            int ya = procWindow.y1 + nrows * t / nt;
            int yb = procWindow.y1 + nrows * (t + 1) / nt;
            th.emplace_back([&, ya, yb]() { warpRows(ya, yb); });
        }
        for (auto &x : th) x.join();
        if (lastlog <= 3) {
            FILE *f = fopen("C:/Users/stefa/AppData/Local/Temp/reframe_ofx.log", "a");
            if (f) { fprintf(f, "stats written=%ld skipped=%ld\n", written.load(), skipped.load()); fclose(f); }
        }
    }
};

// ---------- plugin ----------
class ReframePlugin : public ImageEffect {
    Clip *dstClip_, *srcClip_;
    DoubleParam *fov_, *pan_, *tilt_, *roll_, *byaw_, *bpitch_;
    StringParam *calib_;
public:
    ReframePlugin(OfxImageEffectHandle handle) : ImageEffect(handle) {
        dstClip_ = fetchClip(kOfxImageEffectOutputClipName);
        srcClip_ = fetchClip(kOfxImageEffectSimpleSourceClipName);
        fov_    = fetchDoubleParam("FOV");
        pan_    = fetchDoubleParam("PAN");
        tilt_   = fetchDoubleParam("TILT");
        roll_   = fetchDoubleParam("ROLL");
        byaw_   = fetchDoubleParam("BYAW");
        bpitch_ = fetchDoubleParam("BPITCH");
        calib_  = fetchStringParam("CALIB");
    }

    void render(const RenderArguments &args) override {
        std::string calibPath;
        calib_->getValue(calibPath);
        // animated params must be sampled AT THE RENDER TIME (keyframes)
        double fov, pan, tilt, roll, byaw, bpitch;
        fov_->getValueAtTime(args.time, fov);
        pan_->getValueAtTime(args.time, pan);
        tilt_->getValueAtTime(args.time, tilt);
        roll_->getValueAtTime(args.time, roll);
        byaw_->getValueAtTime(args.time, byaw);
        bpitch_->getValueAtTime(args.time, bpitch);
        plog("render t=%.3f fov=%.2f pan=%.2f tilt=%.2f roll=%.2f calib=%s\n",
             args.time, fov, pan, tilt, roll, calibPath.c_str());

        Calib calib = loadCalib(calibPath);

        WarpProcessor proc(*this);
        std::unique_ptr<Image> dst(dstClip_->fetchImage(args.time));
        std::unique_ptr<Image> src(srcClip_->fetchImage(args.time));
        proc.setDstImg(dst.get());
        proc.setSrcImg(src.get());
        proc.setCalib(calib);
        proc.setAngles((float)fov, (float)pan, (float)tilt, (float)roll,
                       (float)byaw, (float)bpitch);
        proc.setRenderWindow(args.renderWindow);
        clock_t tc0 = clock();
        proc.process();
        { FILE *f = fopen(LOGPATH, "a");
          if (f) { fprintf(f, "render done t=%.3f in %.1f ms\n", args.time,
                  1000.0 * (clock() - tc0) / CLOCKS_PER_SEC); fclose(f); } }
    }
};

mDeclarePluginFactory(ReframeFactory, {}, {});

void ReframeFactory::describe(ImageEffectDescriptor &desc) {
    desc.setLabels("InstaReframeX6 Reframe", "ReframeX6", "InstaReframeX6 Reframe");
    desc.setPluginGrouping("InstaReframeX6");
    desc.addSupportedContext(eContextFilter);
    desc.addSupportedBitDepth(eBitDepthUByte);
    desc.addSupportedBitDepth(eBitDepthUShort);
    desc.addSupportedBitDepth(eBitDepthFloat);
    desc.setSingleInstance(false);
    desc.setHostFrameThreading(false);
    desc.setSupportsMultiResolution(true);
    desc.setSupportsTiles(false);
    desc.setTemporalClipAccess(false);
    desc.setRenderTwiceAlways(false);
    desc.setSupportsMultipleClipPARs(false);
}

void ReframeFactory::describeInContext(ImageEffectDescriptor &desc, ContextEnum context) {
    ClipDescriptor *srcClip = desc.defineClip(kOfxImageEffectSimpleSourceClipName);
    srcClip->addSupportedComponent(ePixelComponentRGBA);
    srcClip->addSupportedComponent(ePixelComponentAlpha);
    srcClip->setTemporalClipAccess(false);
    srcClip->setSupportsTiles(false);
    srcClip->setIsMask(false);

    ClipDescriptor *dstClip = desc.defineClip(kOfxImageEffectOutputClipName);
    dstClip->addSupportedComponent(ePixelComponentRGBA);
    dstClip->addSupportedComponent(ePixelComponentAlpha);
    dstClip->setSupportsTiles(false);

    GroupParamDescriptor *group = desc.defineGroupParam("ReframeGroup");
    group->setLabel("InstaReframeX6");

    DoubleParamDescriptor *p;
    p = desc.defineDoubleParam("FOV");
    p->setLabel("Field of View (deg)");
    p->setRange(10.0, 170.0);
    p->setDisplayRange(10.0, 170.0);
    p->setDefault(90.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("PAN");
    p->setLabel("Pan (deg)");
    p->setRange(-180.0, 180.0);
    p->setDisplayRange(-180.0, 180.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("TILT");
    p->setLabel("Tilt (deg)");
    p->setRange(-90.0, 90.0);
    p->setDisplayRange(-90.0, 90.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("ROLL");
    p->setLabel("Roll (deg)");
    p->setRange(-180.0, 180.0);
    p->setDisplayRange(-180.0, 180.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("BYAW");
    p->setLabel("Seam yaw (deg)");
    p->setRange(-10.0, 10.0);
    p->setDisplayRange(-10.0, 10.0);
    p->setDefault(0.0);
    p->setIncrement(0.1);
    p->setParent(*group);

    p = desc.defineDoubleParam("BPITCH");
    p->setLabel("Seam pitch (deg)");
    p->setRange(-10.0, 10.0);
    p->setDisplayRange(-10.0, 10.0);
    p->setDefault(0.0);
    p->setIncrement(0.1);
    p->setParent(*group);

    StringParamDescriptor *calib = desc.defineStringParam("CALIB");
    calib->setLabel("Calibration file (.calib)");
    calib->setStringType(eStringTypeFilePath);
    calib->setDefault("");
    calib->setParent(*group);
}

ImageEffect* ReframeFactory::createInstance(OfxImageEffectHandle handle, ContextEnum ctx) {
    return new ReframePlugin(handle);
}

namespace OFX { namespace Plugin {
    void getPluginIDs(PluginFactoryArray &ids) {
        static ReframeFactory p("com.instareframex6.reframe", 1, 0);
        ids.push_back(&p);
    }
}}