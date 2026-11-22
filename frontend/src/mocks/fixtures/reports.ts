// Hand-written reports for the mock clips. They quote the synthetic metrics
// of the default seeds (see seeds.ts), as the real report model would.
import type { ComparisonReport, Report } from '@/api/types'

import type { ClipId } from './clips'

const LUMEN_30: Report = {
  headline:
    'The presenter and end card carry this spot; the silent title card wastes the first three seconds.',
  summary:
    'Across 30 seconds the predicted response sits at the 57th percentile of the reference set, led by valuation (84th) and speech (83rd). The clearest peak comes when the presenter appears: faces reach +2.6 SD at 0:11 and social cognition follows a second later. Valuation dips during the city montage (-1.3 SD at 0:06), then builds through the product shot and stays high on the end card. The opening is the weak point: the hook is in the 24th percentile because the title card is static and nearly silent.',
  key_moments: [
    {
      t: 1,
      title: 'Static title card opens flat',
      what_happens: 'The LUMEN wordmark fades in over a quiet music bed.',
      brain_response:
        'Speech (-0.8 SD) and sound (-0.6 SD) stay below average for the first three seconds; the hook is in the 24th percentile.',
      why_it_matters: 'Most viewers decide whether to keep watching in this window.',
    },
    {
      t: 5,
      title: 'City montage lights up scene areas',
      what_happens: 'Amber city lights zoom past: "Every night, the city glows."',
      brain_response:
        'Places & scenes peaks at +1.2 SD, while valuation falls to -1.3 SD a second later.',
      why_it_matters:
        'The montage holds the eye but gives viewers nothing to want yet; it reads as atmosphere, not product.',
    },
    {
      t: 11,
      title: "The presenter's face drives the strongest peak",
      what_happens: 'The presenter appears: "Meet Lumen, the lamp that learns your rhythm."',
      brain_response:
        'Faces peaks at +2.6 SD, social cognition at +1.8 SD (0:12), and speech at +1.6 SD (0:10).',
      why_it_matters:
        'A human face is the most engaging element of the spot, and the brand is named while it is on screen.',
    },
    {
      t: 17,
      title: 'Product glow lifts valuation',
      what_happens:
        'The lamp pulses warm and bright: "Warm when you unwind. Bright when you focus."',
      brain_response:
        'Valuation peaks at +1.6 SD, right after the benefit line (speech +1.3 SD at 0:15).',
      why_it_matters: 'The benefit line lands with the product on screen; keep the two together.',
    },
    {
      t: 20,
      title: 'Bokeh sequence is busy but impersonal',
      what_happens:
        'Soft evening lights drift across the frame: "Your evenings, your rhythm, your light."',
      brain_response:
        'Early visual peaks at +1.2 SD and motion at +1.1 SD (0:19); social cognition falls to -1.1 SD by 0:24.',
      why_it_matters: 'Visually rich, but the human thread from the presenter scene is lost.',
    },
    {
      t: 26,
      title: 'End card closes on brand and value',
      what_happens: '"Lumen. Available now." over the wordmark.',
      brain_response: 'Speech peaks at +1.2 SD; valuation stays near +1.8 SD to the last second.',
      why_it_matters: 'A strong close: viewers leave with the name and a reason to act.',
    },
  ],
  recommendations: [
    {
      title: 'Open on the presenter or the product',
      detail:
        'Move a two-second shot of the presenter, or the glowing lamp, to the first frame. Faces and valuation are the strongest responses in this spot, and the current opening puts the hook in the 24th percentile.',
      t: 0,
    },
    {
      title: 'Tie the city montage to the product',
      detail:
        'Valuation falls to -1.3 SD during the montage. Show the lamp in a window, or name the problem it solves, so the scene builds desire instead of only atmosphere.',
      t: 5,
    },
    {
      title: 'Keep a person in the lifestyle sequence',
      detail:
        'Social cognition falls to -0.7 SD at 0:22 and -1.1 SD by 0:24. A hand reaching for the lamp, or the presenter in the room, would carry the human thread to the end card.',
      t: 22,
    },
    {
      title: 'Protect the end card in cut-downs',
      detail:
        'Speech and valuation peak together on "Lumen. Available now." This close works; keep it whole in shorter versions.',
      t: 26,
    },
  ],
  risks: [
    'The first three seconds are static and nearly silent; the hook is in the 24th percentile.',
    'The city montage lowers valuation (-1.3 SD) before the product appears.',
    'Valuation and social cognition are low-confidence systems; read their swings as hints, not measurements.',
  ],
  strengths: [
    'The presenter scene produces the strongest response in the spot (faces +2.6 SD, social cognition +1.8 SD).',
    'Valuation builds from the product shot (+1.6 SD at 0:17) to the end card (+2.0 SD at 0:29).',
    'The voice-over keeps speech areas engaged: 83rd percentile against the reference set.',
  ],
  scene_notes: [
    {
      scene_index: 0,
      note: 'Title card: most systems respond below average; only salience is clearly above it (+0.4 SD).',
    },
    {
      scene_index: 1,
      note: 'City montage: scene areas engage (+0.8 SD on average) while valuation dips (-1.0 SD).',
    },
    {
      scene_index: 2,
      note: 'Presenter: the high point of the spot for faces (+2.3 SD), social cognition, and speech.',
    },
    {
      scene_index: 3,
      note: 'Product: valuation climbs (+1.2 SD on average) as the benefit line is spoken.',
    },
    {
      scene_index: 4,
      note: 'Lifestyle: visually rich (early visual +0.9 SD), but social cognition falls (-0.7 SD).',
    },
    {
      scene_index: 5,
      note: 'End card: valuation stays high (+1.8 SD) and salience lifts with the brand line.',
    },
  ],
}

const LUMEN_15: Report = {
  headline:
    "The cut-down hooks faster with the product up front, but loses the presenter's human pull.",
  summary:
    'The 15-second cut-down sits at the 54th percentile of the reference set. Showing the product at 0:02 lifts the hook to the 58th percentile, and valuation is the strongest system (91st percentile). Without the presenter, faces stay in the 20th percentile and social cognition in the 38th. Speech falls to -1.2 SD at 0:07, in the gap between voice-over lines.',
  key_moments: [
    {
      t: 4,
      title: 'Benefit line lands early',
      what_happens: '"Warm when you unwind. Bright when you focus." over the glowing lamp.',
      brain_response: 'Speech peaks at +1.0 SD as valuation starts to climb.',
      why_it_matters:
        'Front-loading the benefit works: the message arrives before attention fades.',
    },
    {
      t: 6,
      title: 'Valuation peaks on the product shot',
      what_happens: 'The lamp pulses warm and bright, without voice-over.',
      brain_response: 'Valuation reaches +1.0 SD.',
      why_it_matters: 'The product itself is doing the work here, which is what a cut-down needs.',
    },
    {
      t: 7,
      title: 'Silent gap drops speech',
      what_happens: 'The voice-over pauses for more than five seconds.',
      brain_response: 'Speech falls to -1.2 SD and stays below average until 0:11.',
      why_it_matters:
        'In 15 seconds, a five-second pause is a third of the spot without a message.',
    },
    {
      t: 9,
      title: 'Lifestyle shot engages scene areas',
      what_happens: 'Evening bokeh lights fill the frame.',
      brain_response: 'Places & scenes peaks at +1.5 SD; early visual reaches +0.9 SD.',
      why_it_matters: 'The shot is visually engaging but carries no product or person.',
    },
  ],
  recommendations: [
    {
      title: 'Bring back a face',
      detail:
        'Even one second of the presenter could lift faces and social cognition, which sit in the 20th and 38th percentiles here.',
      t: 8,
    },
    {
      title: 'Fill the silent gap',
      detail:
        'Speech falls to -1.2 SD between 0:06 and 0:11. A short line over the lifestyle shot would keep language areas engaged.',
      t: 7,
    },
    {
      title: 'Keep the early product reveal',
      detail:
        'Opening on the product gives this version a far stronger hook than the 30-second spot (58th against 24th percentile).',
      t: 2,
    },
  ],
  risks: [
    'No face on screen: faces stay in the 20th percentile, the lowest of any system.',
    'A five-second gap in the voice-over lowers speech engagement.',
  ],
  strengths: [
    'The hook is in the 58th percentile, well above the 30-second version.',
    'Valuation is the strongest system (91st percentile) and ends at +1.3 SD.',
    'The response is above the reference average for 67% of seconds.',
  ],
  scene_notes: [
    {
      scene_index: 0,
      note: 'Title card: attention is high (+0.9 SD) as the spot starts on a cut.',
    },
    {
      scene_index: 1,
      note: 'Product: valuation builds (+0.4 SD on average) with the benefit line.',
    },
    { scene_index: 2, note: 'Lifestyle: scene areas peak (+1.2 SD), speech is low (-0.9 SD).' },
    { scene_index: 3, note: 'End card: valuation is at its highest (+1.1 SD on average).' },
  ],
}

const RADIO_20: Report = {
  headline:
    'The opening question grabs language areas; attention sags in the pause after the call to action.',
  summary:
    'Without a reference set, these numbers compare the spot with itself: they show where the response rises and falls, not how it ranks against other ads. Speech areas respond most to the opening question (+1.5 SD at 0:01), and valuation peaks as the product is named (+1.5 SD at 0:05). Attention falls to its lowest point (-2.2 SD at 0:13) after the call to action and recovers with the sign-off, where salience peaks (+2.2 SD at 0:16).',
  key_moments: [
    {
      t: 1,
      title: 'Opening question engages language',
      what_happens: '"Tired of cold, harsh light at home?"',
      brain_response: 'Speech peaks at +1.5 SD in the first seconds.',
      why_it_matters: 'A question is a strong radio opener: listeners process it at once.',
    },
    {
      t: 5,
      title: 'Naming the product lifts valuation',
      what_happens: '"Lumen adapts to your day."',
      brain_response:
        'Valuation peaks at +1.5 SD and attention at +1.4 SD; social cognition dips to -1.7 SD.',
      why_it_matters: 'The product name lands while attention is high.',
    },
    {
      t: 13,
      title: 'Attention bottoms out after the call to action',
      what_happens: 'The music carries on alone after "Find Lumen at your local store today."',
      brain_response: 'Attention falls to -2.2 SD and speech to -1.2 SD.',
      why_it_matters: 'Listeners drift in the pause, right before the brand line.',
    },
    {
      t: 16,
      title: 'Sign-off spikes salience',
      what_happens: '"Lumen. Light that listens."',
      brain_response: 'Salience peaks at +2.2 SD.',
      why_it_matters: 'The brand line is the most noticeable moment of the spot.',
    },
  ],
  recommendations: [
    {
      title: 'Close the gap after the call to action',
      detail:
        'Attention reaches its low point (-2.2 SD) in the pause at 0:13. Bring the sign-off forward by a second, or fill the pause with a sound cue.',
      t: 13,
    },
    {
      title: 'Analyze with a reference set',
      detail:
        'Without one, every curve averages to zero by construction, so the spot cannot be ranked against other ads.',
      t: null,
    },
  ],
  risks: [
    'Attention collapses after the call to action (-2.2 SD at 0:13).',
    'No reference set: the scores show the shape of the response, not how it compares with other ads.',
  ],
  strengths: [
    'The opening question engages language areas at once (+1.5 SD at 0:01).',
    'Naming the product lifts valuation (+1.5 SD at 0:05).',
  ],
  scene_notes: [
    {
      scene_index: 0,
      note: 'Opening question: speech (+1.0 SD) and valuation (+1.0 SD) are high.',
    },
    { scene_index: 1, note: 'Benefit line: attention is at its highest (+0.8 SD on average).' },
    {
      scene_index: 2,
      note: 'Call to action: attention falls (-1.0 SD) while social cognition rises.',
    },
    { scene_index: 3, note: 'Sign-off: salience peaks; speech and valuation are low.' },
  ],
}

const SCRIPT_15: Report = {
  headline:
    'A steady language response, but the script never gives the listener a reason to want the lamp.',
  summary:
    'Read aloud by text-to-speech, the script keeps speech areas above average for almost its whole length (75th percentile against the reference set). Attention and salience build in the second half, around the morning line. Valuation drifts from +0.3 SD to -0.7 SD by 0:08 and ends in the 24th percentile: the script lists what the lamp does without a payoff for the listener. There are no pictures, so the visual systems do not apply.',
  key_moments: [
    {
      t: 1,
      title: 'Product named in the first line',
      what_happens: '"Introducing Lumen, the adaptive lamp."',
      brain_response: 'Valuation is at +0.3 SD and speech is above average from the start.',
      why_it_matters: 'Naming the product at once suits a short spot.',
    },
    {
      t: 8,
      title: 'Feature list flattens valuation',
      what_happens: '"In the evening it glows warm and soft."',
      brain_response: 'Valuation falls to -0.7 SD.',
      why_it_matters: 'Features without a benefit do not build desire.',
    },
    {
      t: 9,
      title: 'Morning line raises salience',
      what_happens: '"In the morning it wakes you gently."',
      brain_response: 'Salience rises to +0.7 SD and attention to +0.4 SD.',
      why_it_matters: 'A concrete moment of the day is easier to picture than a feature.',
    },
    {
      t: 14,
      title: 'Sign-off holds attention',
      what_happens: '"Lumen. Light that listens."',
      brain_response: 'Attention climbs to +1.3 SD while speech falls away.',
      why_it_matters: 'The brand line lands at the most attentive moment.',
    },
  ],
  recommendations: [
    {
      title: 'Give the listener a payoff',
      detail:
        'Turn features into outcomes ("fall asleep easier", "wake up rested"). Valuation is the weakest system here (24th percentile).',
      t: 6,
    },
    {
      title: 'Build on the morning line',
      detail: 'Salience and attention rise around 0:09. Lead with that scene in the next draft.',
      t: 9,
    },
    {
      title: 'Test a human read',
      detail:
        'Text-to-speech flattens emphasis; a voice actor may lift salience at the brand line.',
      t: null,
    },
  ],
  risks: [
    'Valuation drifts down after the opening and ends in the 24th percentile.',
    'Only the script was analyzed: a produced spot with music and pictures will respond differently.',
  ],
  strengths: [
    'Speech areas stay engaged for nearly the whole script (75th percentile).',
    'Attention builds toward the sign-off (+1.3 SD at 0:14).',
  ],
  scene_notes: [
    { scene_index: 0, note: 'Introduction: speech and valuation are above average.' },
    {
      scene_index: 1,
      note: 'Evening line: social cognition (+0.4 SD) and attention rise; valuation falls.',
    },
    {
      scene_index: 2,
      note: 'Morning line and sign-off: attention is highest (+0.5 SD on average).',
    },
  ],
}

export const CLIP_REPORTS: Record<ClipId, Report> = {
  'lumen-30s': LUMEN_30,
  'lumen-15s': LUMEN_15,
  'radio-20s': RADIO_20,
  'script-15s': SCRIPT_15,
}

/** The comparison of the 30-second spot (A) with its 15-second cut-down (B). */
export const LUMEN_COMPARISON: ComparisonReport = {
  headline:
    'The 30-second spot engages faces and language; the cut-down hooks faster and values the product more.',
  summary:
    "Overall the two versions are close: response index 57 for the 30-second spot (A) and 54 for the cut-down (B). A's presenter scene gives it the strongest single moment (faces +2.6 SD at 0:11) and keeps speech areas engaged (83rd percentile against 42nd). B shows the product at 0:02 and is far stronger in the first three seconds (hook in the 58th percentile against the 24th). B's valuation is slightly higher (91st percentile against 84th), but without a face its social response stays low.",
  a_strengths: [
    'Presenter scene: faces +2.6 SD and social cognition +1.8 SD.',
    'Speech areas in the 83rd percentile, against the 42nd for B.',
    'Valuation climbs to +2.0 SD on the end card.',
  ],
  b_strengths: [
    'Hook in the 58th percentile, against the 24th for A.',
    'Valuation is its strongest system (91st percentile).',
    'Above the reference average for 67% of seconds, against 57% for A.',
  ],
  recommendation:
    'Open the 30-second spot the way the cut-down does, with the product in the first two seconds, and keep a short presenter shot in both versions: it is the element that lifts faces, social cognition, and speech.',
}
