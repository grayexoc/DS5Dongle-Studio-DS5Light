import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from channel_mix import ChannelMixer
from core import Processor, Controls, BLOCK, RATE, duplicate, select_stereo, StreamingResampler
from haptic_control import HapticControlDsp, encode_studio_pcm
from studio_rehearsal_format import (
    LIVE_PCM_SCALE, REHEARSAL_MAX_FRAMES, REHEARSAL_PEAK, measure_rehearsal_output,
    read_rehearsal_wav, rehearsal_bounds,
)

FEATURE_SCHEMA_ID = 'ds5light.band-evidence.raw.v1'

def read_wav(path):
    rate, x = wavfile.read(path)
    return rate, normalize_wav(x)


def normalize_wav(x):
    if x.ndim == 1:
        x = x[:, None]
    if x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128) / 128
    elif np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float32) / float(2 ** (np.iinfo(x.dtype).bits - 1))
    else:
        x = x.astype(np.float32)
    return x


def feature_record(sequence, sample_index, values):
    return dict(kind='feature_frame', version=1, stream_generation=1, profile_revision=0,
                feature_schema_id=FEATURE_SCHEMA_ID, inference_epoch=1, sequence=sequence,
                sample_index=sample_index, features=values.ravel().tolist())


def process_array(x, rate=RATE, controls=Controls(), *, feature_frames=None, control_frames=None,
                  studio_pcm16=False, stereo_control=False, shape_control=False, live_pcm_scale=False):
    if studio_pcm16 and (x.ndim != 2 or x.shape[1] != 2):
        raise ValueError('Studio PCM rehearsal requires a stereo input WAV.')
    p, r = Processor(), StreamingResampler(rate)
    out=[]; times=[]
    output_samples = 0
    stereo_control = stereo_control and x.ndim == 2 and x.shape[1] == 2
    haptic_dsp = (HapticControlDsp(p, stereo=stereo_control, shape=shape_control)
                  if control_frames is not None or studio_pcm16 else None)
    layout_id = 'offline.stereo-evidence-control' if stereo_control else 'offline.centered-control'
    if shape_control:
        layout_id = layout_id.replace('offline.', 'offline.shaped-')
    mixer=ChannelMixer()
    size=max(1, round(BLOCK*rate/RATE))
    for i in range(0,len(x),size):
        start=time.perf_counter()
        raw=x[i:i+size]
        if (controls.rear or controls.lfe or controls.center) and raw.ndim==2 and raw.shape[1]==6:
            pcm=np.clip(np.rint(raw*32768),-32768,32767).astype('<i2')
            raw=np.frombuffer(mixer.process(pcm.tobytes(),6,rate,controls.rear,controls.lfe,controls.limiter,center=controls.center),'<i2').reshape(-1,6).astype(np.float32)/32768
        block=r.process(select_stereo(raw))
        if live_pcm_scale:
            # The live worker receives signed PCM16 from the capture bridge.
            block = np.clip(np.rint(block * 32768), -32768, 32767) / 32768
        band_features = np.empty((4, 4), dtype=np.float32) if feature_frames is not None and len(block) else None
        if haptic_dsp is None:
            y = p.process(block, controls, now=i/rate, band_features=band_features)
        else:
            y, control_lr = haptic_dsp.process(block, controls, now=i/rate, band_features=band_features)
        if control_frames is not None and len(y):
            control_frames.append(dict(kind='haptic_frame', version=1, stream_generation=1,
                                       profile_revision=0, layout_id=layout_id,
                                       first_sample=output_samples, frames=len(y), sample_rate_hz=RATE,
                                       control_lr=control_lr.ravel().tolist()))
        output_samples += len(y)
        if band_features is not None:
            feature_frames.append((output_samples - 1, band_features))
        if studio_pcm16:
            if live_pcm_scale:
                block = block * LIVE_PCM_SCALE
                control_lr = control_lr * LIVE_PCM_SCALE
            out.append(encode_studio_pcm(block, control_lr))
        else:
            out.append(duplicate(y))
        times.append((time.perf_counter()-start)*1000)
    return np.concatenate(out) if out else np.empty((0,4), dtype='<i2' if studio_pcm16 else float), times

def rehearsal_window(x, rate, start=0):
    first, length = rehearsal_bounds(len(x), rate, start, RATE)
    window = x[first:first + length]
    if not np.isfinite(window).all():
        raise ValueError('Studio 시험 구간에 유한하지 않은 PCM 값이 있습니다.')
    return window


def limit_rehearsal(pcm):
    pcm = pcm[:REHEARSAL_MAX_FRAMES]
    if not len(pcm):
        raise ValueError('No audio frames in the Studio rehearsal window.')
    peak = int(np.max(np.abs(pcm.astype(np.int32))))
    if peak > REHEARSAL_PEAK:
        return np.rint(pcm.astype(np.float64) * (REHEARSAL_PEAK / peak)).astype('<i2')
    return pcm


def main():
    parser=argparse.ArgumentParser(description='오프라인 WAV 처리. 원본 파일은 덮어쓰지 않습니다.')
    parser.add_argument('input',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--bypass',action='store_true')
    parser.add_argument('--limiter',choices=['hard','soft'],default='hard')
    parser.add_argument('--center',action='store_true',help='센터를 좌우에 추가')
    parser.add_argument('--rear',action='store_true',help='표준 5.1 WAV의 후방 L/R 추가')
    parser.add_argument('--lfe',action='store_true',help='표준 5.1 WAV의 LFE 추가')
    parser.add_argument('--strength',type=float,default=.55)
    parser.add_argument('--no-transient',action='store_true')
    parser.add_argument('--no-background',action='store_true')
    parser.add_argument('--features-jsonl',type=Path,help='공유 DSP 특징을 별도 JSONL 파일에 기록')
    parser.add_argument('--control-jsonl',type=Path,help='오프라인 햅틱 제어 후보를 JSONL로 기록')
    parser.add_argument('--stereo-control',action='store_true',
                        help='오프라인 시험용 스테레오 타격의 좌우 제어 후보 생성')
    parser.add_argument('--shape-control',action='store_true',
                        help='오프라인 시험용 600Hz 이하 타격 상승 파형 비교')
    studio = parser.add_mutually_exclusive_group()
    studio.add_argument('--studio-rehearsal', type=float, nargs='?', const=0.0, metavar='START_S',
                        help='독점 재생용 최대 1.5초 WAV 생성 · 선택한 초부터 시작')
    studio.add_argument('--studio-pcm16',action='store_true',help='Studio Replace/후면 검증용 전면 원음·후면 제어 PCM16 생성')
    args=parser.parse_args()
    outputs = [path for path in (args.output, args.features_jsonl, args.control_jsonl) if path is not None]
    if any(path.exists() for path in outputs) or len({path.resolve() for path in outputs}) != len(outputs):
        parser.error('출력마다 서로 다른 새 경로를 지정하세요.')
    rehearsal = args.studio_rehearsal is not None
    if (args.stereo_control or args.shape_control) and not (args.control_jsonl or args.studio_pcm16 or rehearsal):
        parser.error('제어 시험 옵션에는 햅틱 제어 JSONL 또는 Studio PCM 출력이 필요합니다.')
    studio_pcm16 = args.studio_pcm16 or rehearsal
    if rehearsal:
        try:
            rate, raw = read_rehearsal_wav(args.input, stereo_start=args.studio_rehearsal)
            if raw.ndim != 2 or raw.shape[1] != 2:
                parser.error('Studio PCM 시험에는 스테레오 입력이 필요합니다.')
            x = normalize_wav(rehearsal_window(raw, rate))
            del raw
        except ValueError as exc:
            parser.error(str(exc))
    else:
        rate, x = read_wav(args.input)
    if studio_pcm16 and x.shape[1] != 2:
        parser.error('Studio PCM 시험에는 스테레오 입력이 필요합니다.')
    features = [] if args.features_jsonl is not None else None
    control_frames = [] if args.control_jsonl is not None else None
    y,t=process_array(x,rate,Controls(bypass=args.bypass,strength=args.strength,background=not args.no_background,transient=not args.no_transient,rear=args.rear,lfe=args.lfe,limiter=args.limiter,center=args.center),feature_frames=features,control_frames=control_frames,studio_pcm16=studio_pcm16,stereo_control=args.stereo_control,shape_control=args.shape_control)
    if rehearsal:
        try:
            y = limit_rehearsal(y)
        except ValueError as exc:
            parser.error(str(exc))
    with args.output.open('xb') as wav:
        wavfile.write(wav,RATE,y if studio_pcm16 else y.astype(np.float32))
    if features is not None:
        with args.features_jsonl.open('x',encoding='utf-8') as report:
            for sequence,(sample_index,values) in enumerate(features):
                report.write(json.dumps(feature_record(sequence,sample_index,values),allow_nan=False)+'\n')
    if control_frames is not None:
        with args.control_jsonl.open('x',encoding='utf-8') as report:
            for frame in control_frames:
                report.write(json.dumps(frame,allow_nan=False)+'\n')
    percentiles=np.percentile(t,[50,95,99,100]).tolist() if t else []
    report = dict(input_rate=rate, output_rate=RATE, frames=len(y),
                  dsp_ms_percentiles=percentiles, hardware_haptics_test=False)
    if rehearsal:
        report['studio_rehearsal'] = dict(start_s=args.studio_rehearsal,
                                          stereo_control=args.stereo_control, shape_control=args.shape_control,
                                          rear_ceiling=REHEARSAL_PEAK, **measure_rehearsal_output(y))
    print(json.dumps(report, indent=2))

if __name__=='__main__': main()
