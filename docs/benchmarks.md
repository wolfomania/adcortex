# Benchmarks

How long an analysis takes on Modal, what it costs, and how the speed-ups
change the predicted brain responses. Measured on 2026-11-23 with a 10 s and a
64 s clip of an event highlights video, converted to 1280×720.

## Results

| GPU | 64 s video, warm worker | Worker cost per hour | Cost per 64 s video |
|---|---|---|---|
| L40S (default) | 157 s | $2.46 | $0.11 |
| L4 | 256 s | $1.31 | $0.09 |

Times run from upload to the finished analysis, without the written report.
Costs include the worker's 8 reserved CPU cores and 16 GiB of RAM, at Modal's
November 2026 prices. A worker that has to start first adds its start-up: on
the L40S, the 10 s clip took 94 s from a cold worker.

Twice during these measurements an L4 job waited 7 to 15 minutes for Modal to
find a free L4. Modal logged no such wait for the L40S.

Before the changes below, the L4 spent 7.85 s on each video step, about
16 minutes for a 64 s clip, and a 130 s clip exceeded the worker's 20-minute
limit.

## Where the time goes

TRIBE v2 encodes video with V-JEPA 2 ViT-g: every 0.5 s, it reads the 64
frames of the previous 4 s, resized and cropped to 256×256. A 64 s clip takes
127 such steps, which dominate the analysis. Transcription, the audio and text
features, and the rest of the pipeline take about 60 s together.

One step on an L40S:

| Part | Before | Now | Change |
|---|---|---|---|
| Decode 64 frames | 0.34 s | each frame decoded once | `brain/frames.py` keeps the last 5 s of frames |
| Convert frames to arrays | 0.18 s | 0.18 s | none |
| Resize and normalize | 0.80 s on the CPU | 0.26 s on the GPU | `patch_video_model` in `brain/tribe.py` |
| V-JEPA 2 forward pass | 1.57 s in float32 | 0.30 s in float16 | `patch_video_model` |
| Whole step | 2.84 s | 0.77 s | |

On an L4, a whole step went from 7.85 s to 1.41 s.

The forward pass at each precision, for the same step:

| Precision | Forward pass | Change in the features TRIBE reads |
|---|---|---|
| float32 | 1.57 s | reference |
| TF32 | 1.23 s | 0.11 % |
| float16 autocast | 0.30 s | 0.31 % |
| bfloat16 autocast | 0.30 s | 8.1 % |

The change is the relative error of the features TRIBE takes from V-JEPA 2:
tokens averaged, at 75 % and 100 % of the model's depth. float16 is as fast as
bfloat16 and 26 times as close to float32, so the worker runs V-JEPA 2 in
float16. A step whose activations overflow float16 runs again in float32. The
other float32 matrix products use TF32.

## Accuracy

The predicted responses of the 10 s clip (11 time points × 20,484 vertices,
standard deviation 0.156), compared with float32 on an L40S:

| Run | Pearson r | Max abs. difference | Mean abs. difference |
|---|---|---|---|
| float32 on an L4 | 0.999999 | 0.0020 | 0.00020 |
| TF32 | 0.999998 | 0.0024 | 0.00020 |
| float16 and GPU resizing | 0.999998 | 0.0029 | 0.00020 |
| float16, GPU resizing, and the frame cache (current) | 0.999998 | 0.0029 | 0.00019 |
| current, on an L4 | 0.999998 | 0.0024 | 0.00020 |

The first row is the noise floor: two GPU types running the same float32
code. The speed-ups stay at that level. On the 64 s clip (standard deviation
0.137), the frame cache changes the responses by r = 0.999996 (max. difference
0.0073), and the L4 and L40S agree at r = 0.999995 (0.0076).

## CPU

The worker reserves 8 CPU cores. Without a reservation an L4 worker got one
core: transcription took 274 to 332 s instead of 21 to 27 s, and the 64 s clip
688 s instead of 256 s.

## Method

- Each run uploaded a byte-different copy of a clip (new metadata), so no
  earlier result was reused. `scripts/smoke_modal.py` uploads clips and prints
  the stage timings.
- The predicted responses were read from each analysis's `prediction.npz` on
  the data Volume and compared over all vertices and time points.
- The step profile timed the parts of one step inside a running GPU container,
  with the frames of the 10 s clip.
