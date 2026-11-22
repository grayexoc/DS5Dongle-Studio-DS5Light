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

static float compare_attack_texture(float hz, int rise_samples, bool split) {
    HapticImpactTexture baseline, candidate, right;
    float lowpass[4]{}, crossover[2]{};
    float envelope = 0.0f, lower = 0.0f, upper = 0.0f, gate = 0.0f;
    const float lowpass_step = 1.0f - std::exp(-haptic_math::phase_end * 120.0f / 48000.0f);
    const float crossover_step = 1.0f - std::exp(-haptic_math::phase_end * 55.0f / 48000.0f);
    const auto track = [](float &value, float magnitude) {
        value += (magnitude > value ? .15f : .016f) * (magnitude - value);
    };
    float largest_reduction = 0.0f, output_peak[2]{};
    int first = -1, last = -1;
    for (int i = 0; i < 2400; ++i) {
        const float ramp = std::min(1.0f, static_cast<float>(i) / rise_samples);
        float filtered = .30f * ramp * std::sin(haptic_math::phase_end * hz * i / 48000.0f);
        for (float &state : lowpass) {
            state += lowpass_step * (filtered - state);
            filtered = state;
        }
        crossover[0] += crossover_step * (filtered - crossover[0]);
        crossover[1] += crossover_step * (crossover[0] - crossover[1]);
        track(envelope, std::fabs(filtered));
        track(lower, std::fabs(crossover[1]));
        track(upper, std::fabs(filtered - crossover[1]));
        const float level = split ? lower + .45f * upper : envelope;
        const float target = std::clamp((level - .016f) / .04f, 0.0f, 1.0f);
        gate += (target > gate ? .20f : .02f) * (target - gate);
        const float gated = level * gate;
        const float old_blend = baseline.update(envelope, gated);
        const float new_blend = candidate.update(envelope, gated, split ? lower : 0.0f, split ? upper : 0.0f);
        assert(new_blend == right.update(envelope, gated, split ? lower : 0.0f, split ? upper : 0.0f));
        assert((old_blend > 0.0f) == (new_blend > 0.0f));
        if (new_blend > 0.0f) {
            if (first < 0) first = i;
            if (last >= 0) assert(i == last + 1);
            last = i;
        }
        if (first < 0 || i - first < 480) assert(old_blend == new_blend);
        largest_reduction = std::max(largest_reduction, old_blend - new_blend);
        const float phase = haptic_math::phase_end * 90.0f * i / 48000.0f;
        const float carrier = std::sin(phase);
        const float edge = std::sin(2.0f * phase);
        const float before = haptic_math::soft_clip(gated * (carrier + old_blend * (edge - carrier)));
        const float after = haptic_math::soft_clip(gated * (carrier + new_blend * (edge - carrier)));
        output_peak[0] = std::max(output_peak[0], std::fabs(before));
        output_peak[1] = std::max(output_peak[1], std::fabs(after));
        if (old_blend == 0.0f) assert(before == after);
        assert(std::fabs(after) <= 1.0f);
    }
    assert(first >= 0 && last - first + 1 == 767);
    std::fprintf(stderr, "Texture %.0f Hz rise %d samples split %d: first %d, max blend reduction %.3f, output peak %.4f -> %.4f\n",
                hz, rise_samples, split, first, largest_reduction, output_peak[0], output_peak[1]);
    return largest_reduction;
}

static void check_attack_direction(float left_gain, float right_gain,
                                   bool expect_steering = true, bool quiet = false) {
    const float gain[] = {left_gain, right_gain};
    HapticImpactTexture texture[2];
    float envelope[2]{}, lowpass[2]{}, base_energy[2]{}, steered_energy[2]{};
    const float lowpass_step = 1.0f - std::exp(-haptic_math::phase_end * 120.0f / 48000.0f);
    for (int i = 0; i < 6000; ++i) {
        const int elapsed = i - 2400;
        float gated[2], blend[2];
        for (int side = 0; side < 2; ++side) {
            const float bed = .022f * std::sin(haptic_math::phase_end * 45.0f * i / 48000.0f);
            const float transient = elapsed >= 0 && elapsed < 960
                ? gain[side] * std::sin(haptic_math::phase_end * 105.0f * elapsed / 48000.0f)
                    * std::exp(-elapsed / 960.0f)
                : 0.0f;
            lowpass[side] += lowpass_step * ((quiet ? 0.0f : bed) + transient - lowpass[side]);
            const float magnitude = std::fabs(lowpass[side]);
            envelope[side] += (magnitude > envelope[side] ? .15f : .0258f) * (magnitude - envelope[side]);
            gated[side] = envelope[side] * std::clamp((envelope[side] - .016f) / .04f, 0.0f, 1.0f);
            blend[side] = texture[side].update(envelope[side], gated[side]);
        }
        const float phase = haptic_math::phase_end * 90.0f * i / 48000.0f;
        const float carrier = std::sin(phase), edge = std::sin(2.0f * phase);
        for (int side = 0; side < 2; ++side) {
            const float mixed = texture[side].steer_onset(blend[side], texture[1 - side]);
            assert(mixed <= blend[side]);
            const float base = haptic_math::soft_clip(gated[side] * (carrier + blend[side] * (edge - carrier)));
            const float steered = haptic_math::soft_clip(gated[side] * (carrier + mixed * (edge - carrier)));
            if (elapsed < 0 || i > 4200 || gain[side] >= gain[1 - side] || !expect_steering)
                assert(base == steered);
            if (elapsed >= 0) {
                base_energy[side] += std::pow(gated[side] * blend[side] * edge, 2);
                steered_energy[side] += std::pow(gated[side] * mixed * edge, 2);
            }
        }
    }
    if (quiet) {
        assert(steered_energy[0] == 0.0f && steered_energy[1] == 0.0f);
    } else if (left_gain == right_gain) {
        assert(steered_energy[0] == steered_energy[1] && steered_energy[0] > 0.0f);
    } else if (expect_steering) {
        const int weak = left_gain < right_gain ? 0 : 1;
        assert(base_energy[weak] > 0.0f && steered_energy[weak] <= .26f * base_energy[weak]);
        std::printf("Direction %.2f/%.2f: weak 180 Hz energy %.3f of baseline\n",
                    left_gain, right_gain, steered_energy[weak] / base_energy[weak]);
    }
}

static void check_mix_packet_direction(float native_level) {
    WDL_Resampler resampler;
    resampler.SetMode(true, 0, false);
    resampler.SetRates(48000, 3000);
    resampler.SetFeedMode(true);
    int peaks[2]{};
    for (int block = 0; block < 100; ++block) {
        WDL_ResampleSample *input;
        const int frames = resampler.ResamplePrepare(48, 2, &input);
        for (int i = 0; i < frames; ++i) {
            const float phase = haptic_math::phase_end * 180.0f * (block * frames + i) / 48000.0f;
            const float edge = std::sin(phase);
            input[2 * i] = haptic_mix(native_level * edge, .25f * edge);
            input[2 * i + 1] = haptic_mix(native_level * edge, .0625f * edge);
        }
        float output[96]{};
        const int count = resampler.ResampleOut(output, frames, frames / 4, 2);
        if (block < 10) continue;
        for (int i = 0; i < count; ++i) {
            for (int side = 0; side < 2; ++side) {
                const int sample = std::clamp(static_cast<int>(output[2 * i + side] * 127), -128, 127);
                peaks[side] = std::max(peaks[side], std::abs(sample));
            }
        }
    }
    assert(peaks[0] > peaks[1] && peaks[1] > 0);
    if (native_level == 0) assert(peaks[0] >= 4 * peaks[1]);
    else assert(peaks[0] < 2 * peaks[1]);
    std::printf("Mix packet peaks, centered native %.2f: %d / %d\n", native_level, peaks[0], peaks[1]);
}

int main() {
    static_assert(HapticImpactTexture::uses_front(1, 0));
    static_assert(HapticImpactTexture::uses_front(2, 0));
    static_assert(!HapticImpactTexture::uses_front(1, 1));
    static_assert(!HapticImpactTexture::uses_front(2, 1));
    static_assert(!HapticImpactTexture::uses_front(0, 0));
    check_mix_packet_direction(0.0f);
    check_mix_packet_direction(.60f);
    HapticImpactTexture tail;
    int active_samples = 0;
    for (int i = 0; i < 1000; ++i) {
        const float blend = tail.update(.1f, .1f, .09f, .01f);
        if (blend > 0) ++active_samples;
        if (active_samples == 576) {
            const float previous_tail = .20f * (192.0f / 672.0f);
            assert(blend < .90f * previous_tail);
        }
    }
    assert(active_samples == 767);
    check_attack_direction(.24f, .24f, false);
    check_attack_direction(.24f, .22f, false);
    check_attack_direction(.36f, .10f);
    check_attack_direction(.10f, .36f);
    check_attack_direction(.008f, .002f, false, true);
    for (int rise : {48, 240}) {
        const float weight = compare_attack_texture(35.0f, rise, true);
        const float sharp = compare_attack_texture(110.0f, rise, true);
        assert(weight > .01f && sharp == 0.0f);
        assert(compare_attack_texture(35.0f, rise, false) == 0.0f);
    }
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
    HapticImpactTexture sustained_candidate;
    float envelope = 0.0f, previous_blend = 0.0f;
    int attacks = 0;
    for (int frame = 0; frame < 48000; ++frame) {
        const float level = std::fabs(.15f * std::sin(frame * haptic_math::phase_end * 20.0f / 48000.0f));
        envelope += (level > envelope ? .15f : .016f) * (level - envelope);
        const float gated = envelope * std::clamp((envelope - .016f) / .04f, 0.0f, 1.0f);
        const float blend = texture.update(envelope, gated);
        const float candidate = sustained_candidate.update(envelope, gated, envelope, 0.0f);
        assert((candidate > 0.0f) == (blend > 0.0f));
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
