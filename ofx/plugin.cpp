// InstaReframeX6 OFX plugin — v0: parameters + passthrough render.
// Proves: Resolve loads the plugin, parameters reach the render loop.
// SPDX-License-Identifier: MIT
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#endif

#include <cstring>
#include <cstdio>
#include "ofxsImageEffect.h"
#include "ofxsMultiThread.h"
#include "ofxsProcessing.h"

using namespace OFX;

static void logf(const char *fmt, double t, double a, double b, double c, double d, const char *s) {
    FILE *f = fopen("C:/Users/stefa/AppData/Local/Temp/reframe_ofx.log", "a");
    if (f) { fprintf(f, fmt, t, a, b, c, d, s); fclose(f); }
}

// passthrough processor (v0)
class CopyProcessor : public ImageProcessor {
    const Image *_srcImg;
public:
    CopyProcessor(ImageEffect &instance) : ImageProcessor(instance), _srcImg(0) {}
    void setSrcImg(const Image *v) { _srcImg = v; }
    void multiThreadProcessImages(OfxRectI procWindow) {
        for (int y = procWindow.y1; y < procWindow.y2; y++) {
            if (_effect.abort()) break;
            char *dstRow = (char *)_dstImg->getPixelAddress(procWindow.x1, y);
            const char *srcRow = _srcImg ? (const char *)_srcImg->getPixelAddress(procWindow.x1, y) : nullptr;
            size_t rowBytes = (size_t)(_dstImg->getRowBytes());
            if (srcRow) std::memcpy(dstRow, srcRow, rowBytes);
            else std::memset(dstRow, 0, rowBytes);
        }
    }
};

class ReframePlugin : public ImageEffect {
    Clip *dstClip_, *srcClip_;
    DoubleParam *fov_, *pan_, *tilt_, *roll_;
    StringParam *calib_;
public:
    ReframePlugin(OfxImageEffectHandle handle) : ImageEffect(handle) {
        dstClip_ = fetchClip(kOfxImageEffectOutputClipName);
        srcClip_ = fetchClip(kOfxImageEffectSimpleSourceClipName);
        fov_   = fetchDoubleParam("FOV");
        pan_   = fetchDoubleParam("PAN");
        tilt_  = fetchDoubleParam("TILT");
        roll_  = fetchDoubleParam("ROLL");
        calib_ = fetchStringParam("CALIB");
    }

    void render(const RenderArguments &args) override {
        std::string calibPath;
        calib_->getValue(calibPath);
        logf("render t=%.3f fov=%.2f pan=%.2f tilt=%.2f roll=%.2f calib=%s\n",
             args.time, fov_->getValue(), pan_->getValue(),
             tilt_->getValue(), roll_->getValue(),
             calibPath.c_str());

        CopyProcessor proc(*this);
        std::unique_ptr<Image> dst(dstClip_->fetchImage(args.time));
        std::unique_ptr<Image> src(srcClip_->fetchImage(args.time));
        proc.setDstImg(dst.get());
        proc.setSrcImg(src.get());
        proc.setRenderWindow(args.renderWindow);
        proc.process();
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
    p->setDefault(60.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("PAN");
    p->setLabel("Pan (deg)");
    p->setRange(-180.0, 180.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("TILT");
    p->setLabel("Tilt (deg)");
    p->setRange(-90.0, 90.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
    p->setParent(*group);

    p = desc.defineDoubleParam("ROLL");
    p->setLabel("Roll (deg)");
    p->setRange(-180.0, 180.0);
    p->setDefault(0.0);
    p->setIncrement(1.0);
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