#include "haptic_math.h"
#include "haptic_impact_texture.h"
#include "haptic_mix.h"
#include "resample.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>

struct Pipeline {
    bool approximate;
    float phase[3]{}, aa1[2]{}, aa2[2]{};
    WDL_Resampler resampler;
    explicit Pipeline(bool use_tables): approximate(use_tables) {
        resampler.SetMode(true, 0, false);
        resampler.SetRates(48000, 3000);
        resampler.SetFeedMode(true);
    }
    int block(int first, int mode, int aa, float native_level, float *output) {
        WDL_ResampleSample *input;
        const int count=resampler.ResamplePrepare(48, 2, &input);
        assert(count==48);
        for (int i=0;i<count;++i) {
            float waves[3];
            for (int j=0;j<3;++j) {
                const float hz=j==0?90.0f:j==1?60.0f:160.0f;
                phase[j]+=2.0f*static_cast<float>(haptic_math::pi)*hz/48000.0f;
                if (phase[j]>haptic_math::phase_end) phase[j]-=haptic_math::phase_end;
                waves[j]=approximate?haptic_math::sine_phase(phase[j]):std::sin(phase[j]);
            }
            const int sample=first+i;
            const float envelope=(sample%24000<4000)?0.0f:(sample%24000<8000)?.01f:
                                 (sample%24000<12000)?.4f:(sample%24000<16000)?3.1819806f:18.0f;
            for (int channel=0;channel<2;++channel) {
                const float raw=envelope*waves[0]*(channel?.6f:1.0f);
                float h=approximate?haptic_math::soft_clip(raw):std::tanh(raw);
                if (mode==1) {
                    const float motor=sample%16000<8000?0.0f:1.0f;
                    h+=motor*waves[channel+1]*1.2f;
                }
                if (aa>=2) {
                    const float a=aa==2?.27f:.157f;
                    aa1[channel]+=a*(h-aa1[channel]);
                    h=aa1[channel];
                    if (aa>=3) {
                        aa2[channel]+=a*(h-aa2[channel]);
                        h=aa2[channel];
                    }
                }
                if (mode==1) {
                    const float native=std::clamp(native_level*std::sin(phase[channel+1]),-1.0f,1.0f);
                    h=haptic_mix(native,h);
                }
                input[i*2+channel]=std::clamp(h,-1.0f,1.0f);
            }
        }
        return resampler.ResampleOut(output,count,count/4,2);
    }
};

int main() {
    HapticImpactTexture texture;
    const auto check_texture = [&](int frames, float envelope, float gated) {
        float peak = 0.0f;
        for (int i = 0; i < frames; ++i)
            peak = std::max(peak, texture.update(envelope, gated));
        return peak;
    };
    assert(check_texture(960, .1f, 0.0f) == 0.0f);
    texture = {};
    assert(check_texture(960, .1f, .1f) > .35f);
    assert(check_texture(4800, .1f, .1f) == 0.0f);
    assert(check_texture(1920, 0.0f, 0.0f) == 0.0f);
    assert(check_texture(960, .1f, .1f) > .35f);
    texture = {};
    float envelope = 0.0f, previous_blend = 0.0f;
    int attacks = 0;
    for (int frame = 0; frame < 48000; ++frame) {
        const float level = std::fabs(.15f * std::sin(frame * haptic_math::phase_end * 20.0f / 48000.0f));
        envelope += (level > envelope ? .15f : .016f) * (level - envelope);
        const float gated = envelope * std::clamp((envelope - .016f) / .04f, 0.0f, 1.0f);
        const float blend = texture.update(envelope, gated);
        if (blend > 0.0f && previous_blend == 0.0f) ++attacks;
        previous_blend = blend;
    }
    assert(attacks == 1);
    using haptic_math::quantize_native;
    if (quantize_native(0) != 0 || quantize_native(.49f) != 0 ||
        quantize_native(-.49f) != 0 || quantize_native(.5f) != 1 ||
        quantize_native(-.5f) != -1 || quantize_native(254) != 127 ||
        quantize_native(-254) != -128) return 1;

    // Compare quantizers on the same samples at the resampler output.
    for (float peak : {0.8f, 12.0f, 254.0f}) {
        int old_zero = 0, new_zero = 0, old_rail = 0, new_rail = 0;
        double old_error = 0, new_error = 0;
        for (int i = 0; i < 3000; ++i) {
            const float input = peak * std::sin(2.0 * haptic_math::pi * 90 * i / 3000);
            const auto old_sample = std::clamp(static_cast<int>(input), -128, 127);
            const auto new_sample = quantize_native(input);
            const float reference = std::clamp(input, -128.0f, 127.0f);
            old_zero += old_sample == 0;
            new_zero += new_sample == 0;
            old_rail += old_sample == -128 || old_sample == 127;
            new_rail += new_sample == -128 || new_sample == 127;
            old_error += std::fabs(old_sample - reference);
            new_error += std::fabs(new_sample - reference);
        }
        if (new_error >= old_error || new_zero > old_zero) return 1;
        std::printf("Native peak %.1f: zeros %d -> %d, MAE %.4f -> %.4f, rails %d -> %d\n",
                    peak, old_zero, new_zero, old_error / 3000, new_error / 3000, old_rail, new_rail);
    }

    NativeMixLowpass native_filter;
    float left = -0.5f, right = 0.25f;
    native_filter.process(left, right, 0.25f);
    if (left != -0.5f || right != 0.25f) return 1;
    left = 0.5f;
    right = -0.25f;
    native_filter.process(left, right, 0.25f);
    if (left != -0.25f || right != 0.125f) return 1;
    native_filter.reset();
    left = 0.75f;
    right = -0.75f;
    native_filter.process(left, right, 0.25f);
    if (left != 0.75f || right != -0.75f) return 1;

    float sine_error=0,clip_error=0,previous=-1;
    for (int i=0;i<=2000000;++i) {
        const float phase=haptic_math::phase_end*i/2000000;
        sine_error=std::max(sine_error,std::fabs(std::sin(phase)-haptic_math::sine_phase(phase)));
        const float x=-20.0f+40.0f*i/2000000;
        const float candidate=haptic_math::soft_clip(x);
        assert(candidate>=previous && candidate>=-1 && candidate<=1);
        previous=candidate;
        clip_error=std::max(clip_error,std::fabs(std::tanh(x)-candidate));
    }
    assert(sine_error<5.0e-6f && clip_error<1.0e-5f);
    assert(std::signbit(haptic_math::soft_clip(-0.0f)));
    assert(std::isnan(haptic_math::soft_clip(std::numeric_limits<float>::quiet_NaN())));
    assert(haptic_math::soft_clip(std::numeric_limits<float>::infinity())==1);
    assert(haptic_math::soft_clip(-std::numeric_limits<float>::infinity())==-1);
    unsigned long long total=0,changed=0;
    int maximum_delta=0;
    for (int mode:{1,2}) for (int aa:{1,2,3}) for (float native:{0.0f,.5f,1.0f}) {
        Pipeline before(false),after(true);
        for (int first=0;first<48000*3;first+=48) {
            float reference[24],candidate[24];
            const int count=before.block(first,mode,aa,native,reference);
            assert(count==after.block(first,mode,aa,native,candidate));
            for (int i=0;i<count*2;++i) {
                const int a=std::clamp(static_cast<int>(reference[i]*127),-128,127);
                const int b=std::clamp(static_cast<int>(candidate[i]*127),-128,127);
                const int difference=std::abs(a-b);
                assert(difference<=1);
                changed+=difference!=0;
                maximum_delta=std::max(maximum_delta,difference);
                ++total;
            }
            for (int j=0;j<3;++j) assert(before.phase[j]==after.phase[j]);
        }
    }
    std::printf("PASS: sine max %.9g, tanh max %.9g; Mix/Replace AA1/2/3 native0/0.5/1 WDL samples %llu; changed %llu (%.6f%%), max int8 delta %d\n",
        sine_error,clip_error,total,changed,100.0*changed/total,maximum_delta);
}
