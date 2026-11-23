# The science behind the numbers

This page explains what the app measures, how each number is computed, and
how far the numbers can be trusted.

In short: a published brain-encoding model, TRIBE v2, predicts how an average
viewer's cortex would respond to a clip, second by second. The app groups that
prediction into ten brain systems, compares them with reference ads, and asks
a language model to explain the result. Every number is a prediction for an
average viewer, not a measurement of real people, and none of them forecasts
sales.

## From a clip to a cortical response

1. **Prepare the media.** ffmpeg converts the upload into model inputs, finds
   scene cuts (`scdet`), and extracts keyframes (`backend/src/adcortex/media/`).
   A script is first read aloud with gTTS, so the model hears it the way it
   would hear a voice-over.
2. **Transcribe.** WhisperX transcribes the speech with word timings and
   detects the language (`brain/transcript.py`, `brain/whisperx_runner.py`).
3. **Predict.** TRIBE v2 (d'Ascoli et al., 2026) predicts the fMRI response on
   the fsaverage5 cortical mesh: 20,484 vertices, 10,242 per hemisphere. It
   sees the video through V-JEPA 2, hears the audio through Wav2Vec-BERT 2.0,
   and reads the words through Llama 3.2 3B (`brain/tribe.py`).
4. **Align to seconds.** The predictions go on a 1 Hz grid: row *k* holds the
   prediction whose segment starts in [*k*, *k* + 1). Seconds the model skipped
   stay empty instead of shifting later seconds (`analysis/curves.py`).

The wrapper around TRIBE v2 changes three things in its reference pipeline:

- **Word placement.** For audio longer than 90 s, TRIBE shifts every word by
  every chunk's start, which misplaces and duplicates the transcript. Here each
  word is placed once, in the chunk that contains it.
- **Language.** TRIBE hard-codes English. Here the language comes from the
  upload form or from speech detection, so any language with a WhisperX
  alignment model can be transcribed.
- **Sentence splitting.** Languages without a dedicated spaCy pipeline use the
  multilingual splitter. If text annotation still fails, the prediction uses
  the video and audio features only.

## Ten brain systems

A vertex-level map is hard to read, so the app summarizes it as ten systems.
Each system is a set of areas from the HCP-MMP1.0 parcellation (Glasser et al.,
2016), projected onto the same fsaverage5 mesh. A system's response at second
*k* is the mean prediction over the vertices of its areas in both hemispheres.
The definitions live in `backend/src/adcortex/data/systems.yaml`.

| System | HCP-MMP1.0 areas | What it tracks | Confidence |
|---|---|---|---|
| Early visual | V1, V2, V3, V4 | Contrast, edges, color, and how much the picture changes | High |
| Motion | MT, MST, FST, V4t | Moving objects, camera moves, and optic flow | High |
| Faces | FFC, PIT | Faces and, more weakly, bodies and objects | Medium |
| Places & scenes | PHA1–3, VMV1–3, RSC | Places, landscapes, and spatial layout | Medium |
| Sound | A1, LBelt, MBelt, PBelt, RI | Loudness, pitch, and acoustic change | High |
| Speech & language | A4, A5, STSda, STSdp, STSva, STSvp, STGa, 44, 45, 47l, 55b, PSL, SFL | Spoken words and, more strongly, meaningful sentences | Medium |
| Social cognition | TPOJ1, TPOJ2, STV, PGi, TGd, TGv, 9m, PCV | Thinking about people's intentions and stories | Low |
| Attention | FEF, PEF, LIPv, LIPd, VIP, IPS1, 7PC, 7AL, 7PL, MIP, AIP | Orienting to and tracking what is on screen | Medium |
| Salience | AVI, AAIC, MI, FOP4, FOP5, a24pr, p24pr, 33pr, p32pr, a32pr | Surprising, important, or emotionally charged moments | Low |
| Valuation | 10r, 10v, s32, 25, OFC, pOFC, 11l, 13l | Subjective value | Low |

Confidence says how specific the link between the areas and the named
function is:

- **High:** decades of converging evidence tie these areas to this function.
- **Medium:** well supported, but the areas also take part in other functions.
- **Low:** the areas serve several functions; read the system as a hint, not a
  measurement.

The four visual systems apply to video only. For audio and scripts the app
marks them "needs a picture" and leaves them out of every score.

## Comparing with reference ads

Raw predictions have no natural unit, so the app expresses them against a
**reference library**: a set of reference clips run through the same pipeline
(`analysis/baseline.py`). For each system, the library stores the mean and
standard deviation of the per-second response across all reference clips, and
each clip's mean. It also stores each reference clip's mean response over its
first 3 seconds, for the Hook score.

- **z-score:** how many standard deviations a second's response lies above or
  below the reference average for that system. +1 SD is a clearly stronger
  response; +2 SD is exceptional.
- **Percentile vs reference:** where the clip's mean response ranks among the
  reference clips' means.
- **Percentile vs your library:** where the clip's raw mean response ranks
  among your own earlier analyses (`analysis/library.py`). It appears once
  there are at least ten of them, and needs no reference library.

The 3D brain shows per-vertex z-scores, quantized to one byte per vertex per
second: *z* = −3 + 6 · *b* / 255, so 128 is the average and values beyond
±3 SD are clipped (`analysis/frames.py`).

**Without a reference library**, the app compares the clip with itself: each
system and each vertex is z-scored against the clip's own mean and standard
deviation. Peaks and dips stay meaningful, but every system's mean is zero by
construction. Response index, Hook, Sustain, and the reference percentiles
are then unavailable, and the systems are ranked by their strongest second
instead. The repository does not ship a
reference library yet; a deployment runs in this mode until one is added as
`backend/src/adcortex/data/baseline_v1.json`.

## Scores

The four headline numbers are deterministic functions of the system z-curves
(`analysis/scores.py`). The *mean response* at a second is the average z-score
of the applicable systems.

| Score | Definition |
|---|---|
| Response index | Average reference percentile of the applicable systems, 0–100 |
| Hook | Where the mean response over the first 3 seconds ranks among the reference clips' first 3 seconds |
| Sustain | Share of seconds where the mean response is above the reference average |
| Peaks | Number of peak moments |

The first three need a reference library.

## Moments

Moments are the clearest peaks and dips in the system curves
(`analysis/moments.py`):

- A **peak** is a local maximum of at least +1.0 SD that stands at least
  0.75 SD above its surroundings (prominence).
- A **dip** is the mirror image: a local minimum of −1.0 SD or lower.
- Within one system, peaks are at least 3 seconds apart, and so are dips; of
  two closer ones, the stronger is kept.
- At most 12 moments are reported: the strongest by absolute z-score.

## The written report

The report is optional: the metrics stand without it. A language model chosen
with `ADCORTEX_LLM_MODEL` (any model Pydantic AI supports) reads a brief of the
metrics: scores, systems with their confidence, moments, scenes, and the
transcript (`llm/prompts.py`). It also receives the richest media the model
accepts (`llm/report.py`):

- With `ADCORTEX_LLM_MEDIA=video`, a small proxy of the clip (or, for audio, the
  sound), up to 18 MB. A model that does not accept it gets keyframes instead.
- With `keyframes`, up to 16 scene keyframes.
- With `text`, the metrics only.

Its instructions tell it that the numbers are predictions for an average
viewer, to ground every claim in the numbers or in what is on screen, to keep
every time inside the clip, to treat low-confidence systems as tentative, and
never to claim to measure emotions, preference, or purchase intent. The output
is a typed object: headline, summary, strengths, risks, key moments, and
recommendations. A time outside the clip or an unknown scene sends the report
back to the model to correct.

## Limitations

- **Predicted, not measured.** TRIBE v2 predicts the response of an average
  viewer. It says nothing about a specific audience, individual differences,
  memory, liking, or purchase intent.
- **Reverse inference.** A stronger response in an area does not prove that the
  named mental process happened: most areas serve several functions (Poldrack,
  2006). The confidence labels exist for this reason.
- **Weak regions.** The ventromedial prefrontal and orbitofrontal cortex give a
  weak fMRI signal, so Valuation is the least reliable system.
- **Language.** TRIBE v2 was trained on English. Other languages are
  transcribed and predicted, but the app flags them as less reliable.
- **Time resolution.** The analysis works in whole seconds. Effects shorter
  than a second blur together.
- **Relative numbers.** Percentiles are relative to the reference library. A
  library of different ads would give different percentiles.

## Licenses

- **TRIBE v2** weights are licensed CC BY-NC 4.0: non-commercial use only.
- **Llama 3.2 3B** is gated on Hugging Face; the account that downloads it
  accepts the Llama 3.2 Community License.
- **HCP-MMP1.0** data are redistributed under the WU-Minn HCP Open Access Data
  Use Terms. The required acknowledgment is in
  `backend/src/adcortex/data/README.md`.
- The other models TRIBE v2 uses (V-JEPA 2, Wav2Vec-BERT 2.0, and DINOv2) and
  WhisperX's transcription and alignment models carry their own licenses; read
  their model cards before any commercial use.

## References

- Bartra O, McGuire JT, Kable JW (2013). The valuation system: a
  coordinate-based meta-analysis of BOLD fMRI experiments examining neural
  correlates of subjective value. NeuroImage 76:412–427.
  doi:10.1016/j.neuroimage.2013.02.063
- Corbetta M, Shulman GL (2002). Control of goal-directed and stimulus-driven
  attention in the brain. Nat Rev Neurosci 3:201–215. doi:10.1038/nrn755
- d'Ascoli S et al. (2026). A foundation model of vision, audition, and
  language for in-silico neuroscience. arXiv:2605.04326
- Epstein R, Kanwisher N (1998). A cortical representation of the local visual
  environment. Nature 392:598–601. doi:10.1038/33402
- Fedorenko E et al. (2010). New method for fMRI investigations of language.
  J Neurophysiol 104:1177–1194. doi:10.1152/jn.00032.2010
- Glasser MF et al. (2016). A multi-modal parcellation of human cerebral
  cortex. Nature 536:171–178. doi:10.1038/nature18933
- Huk AC, Dougherty RF, Heeger DJ (2002). Retinotopy and functional
  subdivision of human areas MT and MST. J Neurosci 22:7195–7205.
  doi:10.1523/JNEUROSCI.22-16-07195.2002
- Kanwisher N, McDermott J, Chun MM (1997). The fusiform face area. J Neurosci
  17:4302–4311. doi:10.1523/JNEUROSCI.17-11-04302.1997
- Moerel M, De Martino F, Formisano E (2014). An anatomical and functional
  topography of human auditory cortical areas. Front Neurosci 8:225.
  doi:10.3389/fnins.2014.00225
- Poldrack RA (2006). Can cognitive processes be inferred from neuroimaging
  data? Trends Cogn Sci 10:59–63. doi:10.1016/j.tics.2005.12.004
- Saxe R, Kanwisher N (2003). People thinking about thinking people: the role
  of the temporo-parietal junction in "theory of mind". NeuroImage
  19:1835–1842. doi:10.1016/S1053-8119(03)00230-1
- Seeley WW et al. (2007). Dissociable intrinsic connectivity networks for
  salience processing and executive control. J Neurosci 27:2349–2356.
  doi:10.1523/JNEUROSCI.5587-06.2007
- Wandell BA, Dumoulin SO, Brewer AA (2007). Visual field maps in human
  cortex. Neuron 56:366–383. doi:10.1016/j.neuron.2007.10.012
