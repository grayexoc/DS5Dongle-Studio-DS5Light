# HT-GRU-Lab-Lite와 DS5Light의 오프라인 연계

[HT-GRU-Lab-Lite](https://github.com/grayexoc/HT-GRU-Lab-Lite)는 같은 게임 WAV에서 이벤트를 검수하고 사람이 확정한 레이블을 내보낸다. DS5Light는 그 WAV에서 기존 DSP의 특징을 계산한다. Qwen3-VL, PANNs, CLAP 결과는 후보 검수에 사용하며 DS5Light 특징이나 정답으로 가져오지 않는다.

## 검수 결과를 받는 방법

HT-GRU-Lab-Lite의 `portable_data/data/raw/`에서 **검수에 사용한 그대로의 WAV**와 `portable_data/data/processed/confirmed_annotations/`에서 해당 `*_confirmed.jsonl`을 사용한다. 내보내기에서 `game_id`와 `session_id`를 지정한다. WAV를 잘라 내거나 이름을 바꾸면 기존 구간과 `source_id`를 그대로 사용할 수 없다. 어댑터는 이름과 ID를 확인하며 같은 이름의 다른 WAV까지 식별하지는 못하므로 원본 파일의 SHA-256을 별도로 보존한다.

DS5Light 소스의 `DS5Light/`에서 실행한다.

```powershell
python training_alignment.py capture.wav capture_confirmed.jsonl aligned.jsonl
```

- `confirmed`이고 출처가 `human_review` 또는 `human_export`인 구간만 사용한다. 소스 ID는 WAV 파일명에서 확장자를 뺀 값이다. 서로 다른 WAV 또는 게임·세션을 섞은 확정 라벨은 거부한다.
- 확정 구간은 시작을 포함하고 종료를 제외한다. V1 특징 프레임의 마지막 48kHz 샘플 인덱스로 구간을 판정한다. 겹치는 구간의 레이블을 함께 기록한다. 프레임과 만나지 않은 짧은 구간은 실행 보고서에서 `unmatched_intervals`로 확인할 수 있다. 영상 오프셋을 다시 적용하지 않는다.
- 출력에는 게임·세션 ID, `labels`와 V1 `frame` 객체가 들어간다. `labels: null`은 검수되지 않은 프레임이다. 이후 학습에서 이를 곧바로 배경·무음 또는 부정 사례로 처리하지 않는다. 게임·세션 단위의 분할을 유지하고, 같은 소스나 복제본이 여러 분할에 포함되지 않는지 확인한다.
- 이 도구는 Phase 2의 `ds5light.band-evidence.raw.v1` 특징을 사용한다. 실제 학습용 특징 순서·정규화·텐서 규격·추론 주기는 Phase 3에서 확정한다. 프레임 교환 JSON Schema를 학습기 전용 `approved_schema.json`으로 그대로 제출하지 않는다.

## 학습 완료 후 받을 결과

1. 모델 파일과 해시, 모델 ID 및 형식, 특징 스키마 ID와 해시, 공용 추출기 커밋, 정규화, 입력·상태·출력 텐서의 이름·형태·dtype, 라벨 순서, 리셋·워밍업 규칙을 함께 받는다.
2. 게임·세션 분할 근거와 동일 기준 동작의 DSP Only 대비 효과 검출 결과, CPU 지연 p50/p95/p99, 장시간 오류·누락 결과를 함께 받는다.
3. DS5Light에서 같은 특징으로 오프라인 재생을 먼저 대조한다. 형식이나 동등성 검증을 통과하면 그때 런타임 연계와 기존 DSP Only 폴백을 검증한다.

## 외부 추론 결과를 먼저 평가하는 방법

평가할 클립의 `aligned.jsonl` 각각에 대해, 원래 특징 프레임의 식별자와 샘플 인덱스를 복사한 `InferenceResultV1` JSONL을 시퀀스 순서대로 내보낸다. 워밍업·무효 결과는 `valid: false`로 표시한다. 추론 간격 때문에 생략한 프레임은 그대로 비워 둔다.

`evaluation.json`에는 다음 키를 넣는다.

| 키 | 값 |
|---|---|
| `version` | `1` |
| `aligned_sha256` | 해당 `aligned.jsonl`의 전체 바이트 SHA-256, 소문자 16진수 |
| `model_id` | 모든 결과 프레임의 `model_id`와 같은 값 |
| `labels` | 모델 확률 배열과 동일한 순서의 레이블 목록 |
| `threshold` | 이 평가에서 고정한 확률 임계값, 0–1 |

```powershell
python training_evaluation.py aligned.jsonl predictions.jsonl evaluation.json
```

모델 파일까지 인수할 때는 같은 평가 매니페스트에 `model_sha256`(모델 파일의 SHA-256)과 `feature_schema_id`(모든 정렬 프레임의 스키마 ID)를 추가한 뒤 다음과 같이 실행한다.

```powershell
python training_evaluation.py aligned.jsonl predictions.jsonl evaluation.json --model-artifact model.onnx
```

검사는 모델 파일 바이트와 선언된 스키마 ID를 대조한다. 모델을 실제로 실행해 예측과 대조하는 재현 시험 및 텐서·정규화·CPU 성능 검증은 모델 인수 후 별도로 수행한다. 기존 모델 파일 없는 평가 명령도 사용할 수 있다.

DSP Only 결과를 같은 레이블의 `InferenceResultV1` 평가 레코드로 준비한 뒤 `--reference dsp-results.jsonl dsp-evaluation.json`을 붙이면 레이블별 재현율 차이를 계산한다. 두 결과는 같은 정렬 파일, 같은 임계값, 같은 레이블 집합, 같은 유효 검수 프레임을 사용해야 한다. 유효 프레임 수가 같아도 실제 프레임 위치가 다르면 비교를 거부한다.

모델 파일과 기준선이 모두 준비된 경우 한 명령으로 검사한다.

```powershell
python training_evaluation.py aligned.jsonl predictions.jsonl evaluation.json --model-artifact model.onnx --reference dsp-results.jsonl dsp-evaluation.json
```

사람이 특정 이벤트의 부재를 확인한 구간은 확인된 주석 레코드에 `"present": false`를 붙여 정렬 도구에 전달할 수 있다. 기존 주석은 `present`를 생략하면 이벤트가 존재하는 구간으로 처리한다. 정렬 결과의 `negative_labels`에는 명시적으로 확인한 부재만 기록한다. 같은 프레임에서 같은 레이블이 존재와 부재로 동시에 확인되면 정렬과 평가는 모두 오류로 처리한다. 평가 보고서는 유효한 부재 프레임 중 임계값을 넘은 비율과 DSP Only 대비 차이를 제공한다.

보고서는 라벨별 확정 프레임 수, 유효 추론이 대응하는 프레임 수, 임계값을 넘은 수와 대응 프레임 재현율을 제공한다. 모델 목록에 빠진 확정 라벨도 표시한다. 모델 간 비교에서는 동일 클립과 프레임 범위, 평가 전에 정한 임계값 정책을 사용한다. 유효 추론이 일부 구간에만 있는 경우 재현율과 커버리지를 함께 본다. 미검수 구간 및 각 프레임의 나머지 라벨은 부정 사례로 계산하지 않는다. 오탐률과 DSP Only 대비 합격 판정은 별도로 검수한 부정 사례와 동등한 기준선이 필요하다.

## 검증 기록

HT-GRU-Lab-Lite의 실제 JSONL 내보내기 함수로 합성 WAV의 검수 데이터를 만들었다. DS5Light CLI에서 이를 읽어 출력한 10개 V1 특징 프레임이 모두 스키마를 통과했다. 4개는 확정 레이블과 연결됐고 6개는 미검수로 표시됐다. 실제 게임 자료와 모델 학습은 이번 범위에 포함되지 않았다.

합성 추론 레코드로 입력 해시, 프레임 순서·식별자, 라벨 순서, 확률 범위와 미검수 구간 제외를 검사했다. 평가 도구는 모델 파일을 로드하지 않으며, 별도 학습 결과를 처리할 때도 DS5Light 런타임 동작은 변경되지 않는다.

합성 WAV와 존재·부재 주석부터 실제 정렬 CLI와 평가 CLI를 연속 실행했다. 시험용 파일 해시 확인과 동일 검수 프레임에서의 재현율·오탐률 차이가 기대값과 일치했다. 실제 게임 또는 학습 모델의 품질을 평가한 결과는 아니다.
