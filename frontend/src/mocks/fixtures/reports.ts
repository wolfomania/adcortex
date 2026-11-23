// Hand-written reports for the mock clips. They quote the synthetic metrics
// of the default seeds (see seeds.ts), as the real report model would.
import type { ComparisonReport, Report } from '@/api/types'

import type { ClipId } from './clips'

const LUMEN_30: Report = {
  headline: 'The presenter and end card carry the spot; the silent opening wastes 3 seconds.',
  key_moments: [
    {
      t: 1,
      title: 'Static title card opens flat',
      what_happens: 'The LUMEN wordmark fades in over a quiet music bed.',
      brain_response: 'Speech -0.8 SD and sound -0.6 SD; hook in the 24th percentile.',
    },
    {
      t: 5,
      title: 'City montage lowers valuation',
      what_happens: 'Amber city lights zoom past: "Every night, the city glows."',
      brain_response: 'Places & scenes +1.2 SD; valuation falls to -1.3 SD a second later.',
    },
    {
      t: 11,
      title: "Presenter's face drives the peak",
      what_happens: 'The presenter appears: "Meet Lumen, the lamp that learns your rhythm."',
      brain_response: 'Faces +2.6 SD, social cognition +1.8 SD, speech +1.6 SD.',
    },
    {
      t: 20,
      title: 'Lifestyle shots lose the person',
      what_happens: 'Soft evening lights drift across the frame.',
      brain_response: 'Early visual +1.2 SD; social cognition falls to -1.1 SD by 0:24.',
    },
    {
      t: 26,
      title: 'End card closes on the brand',
      what_happens: '"Lumen. Available now." over the wordmark.',
      brain_response: 'Speech +1.2 SD; valuation holds near +1.8 SD to the end.',
    },
  ],
  recommendations: [
    {
      title: 'Open on the presenter or lamp',
      detail: 'Move a 2-second shot of the presenter or the glowing lamp to the first frame.',
      t: 0,
    },
    {
      title: 'Show the lamp in the montage',
      detail: 'Put the lamp in a window during the montage, where valuation falls to -1.3 SD.',
      t: 5,
    },
    {
      title: 'Keep a person on screen',
      detail: 'Add a hand reaching for the lamp at 0:22, before social cognition falls to -1.1 SD.',
      t: 22,
    },
    {
      title: 'Protect the end card in cut-downs',
      detail: 'Keep "Lumen. Available now." whole in shorter versions.',
      t: 26,
    },
  ],
}

const LUMEN_15: Report = {
  headline: 'The product-first opening hooks faster; the cut-down loses the presenter.',
  key_moments: [
    {
      t: 4,
      title: 'Benefit line lands early',
      what_happens: '"Warm when you unwind. Bright when you focus." over the glowing lamp.',
      brain_response: 'Speech +1.0 SD as valuation starts to climb.',
    },
    {
      t: 6,
      title: 'Valuation peaks on the product',
      what_happens: 'The lamp pulses warm and bright, without voice-over.',
      brain_response: 'Valuation +1.0 SD.',
    },
    {
      t: 7,
      title: 'Silent gap drops speech',
      what_happens: 'The voice-over pauses for more than five seconds.',
      brain_response: 'Speech falls to -1.2 SD and stays below average until 0:11.',
    },
    {
      t: 9,
      title: 'Lifestyle shot engages scene areas',
      what_happens: 'Evening bokeh lights fill the frame.',
      brain_response: 'Places & scenes +1.5 SD; early visual +0.9 SD.',
    },
  ],
  recommendations: [
    {
      title: 'Bring back the presenter',
      detail: 'Add one second of the presenter; faces sit in the 20th percentile here.',
      t: 8,
    },
    {
      title: 'Fill the silent gap',
      detail: 'Put a short line over the lifestyle shot, where speech falls to -1.2 SD.',
      t: 7,
    },
    {
      title: 'Keep the early product reveal',
      detail: 'Open on the product in every cut; the hook here is in the 58th percentile.',
      t: 2,
    },
  ],
}

const RADIO_20: Report = {
  headline: 'The opening question grabs language areas; attention sags after the call to action.',
  key_moments: [
    {
      t: 1,
      title: 'Opening question engages language',
      what_happens: '"Tired of cold, harsh light at home?"',
      brain_response: 'Speech +1.5 SD.',
    },
    {
      t: 5,
      title: 'Product name lifts valuation',
      what_happens: '"Lumen adapts to your day."',
      brain_response: 'Valuation +1.5 SD and attention +1.4 SD.',
    },
    {
      t: 13,
      title: 'Attention bottoms out after the call',
      what_happens: 'Music plays alone after "Find Lumen at your local store today."',
      brain_response: 'Attention -2.2 SD and speech -1.2 SD.',
    },
    {
      t: 16,
      title: 'Sign-off spikes salience',
      what_happens: '"Lumen. Light that listens."',
      brain_response: 'Salience +2.2 SD.',
    },
  ],
  recommendations: [
    {
      title: 'Close the pause after the call',
      detail: 'Bring the sign-off forward by a second, or fill the pause with a sound cue.',
      t: 13,
    },
    {
      title: 'Keep the question opener',
      detail: 'Open every cut with the question; speech peaks at +1.5 SD on it.',
      t: 1,
    },
  ],
}

const SCRIPT_15: Report = {
  headline: 'Language engages throughout; the script gives no reason to want the lamp.',
  key_moments: [
    {
      t: 1,
      title: 'Product named in the first line',
      what_happens: '"Introducing Lumen, the adaptive lamp."',
      brain_response: 'Speech above average from the start; valuation +0.3 SD.',
    },
    {
      t: 8,
      title: 'Feature list flattens valuation',
      what_happens: '"In the evening it glows warm and soft."',
      brain_response: 'Valuation falls to -0.7 SD.',
    },
    {
      t: 9,
      title: 'Morning line raises salience',
      what_happens: '"In the morning it wakes you gently."',
      brain_response: 'Salience +0.7 SD and attention +0.4 SD.',
    },
    {
      t: 14,
      title: 'Sign-off holds attention',
      what_happens: '"Lumen. Light that listens."',
      brain_response: 'Attention climbs to +1.3 SD as speech falls away.',
    },
  ],
  recommendations: [
    {
      title: 'Turn features into outcomes',
      detail: 'Replace the feature list with outcomes, such as "fall asleep easier".',
      t: 6,
    },
    {
      title: 'Lead with the morning line',
      detail: 'Open the next draft on the morning scene, where salience and attention rise.',
      t: 9,
    },
  ],
}

export const CLIP_REPORTS: Record<ClipId, Report> = {
  'lumen-30s': LUMEN_30,
  'lumen-15s': LUMEN_15,
  'radio-20s': RADIO_20,
  'script-15s': SCRIPT_15,
}

export const LUMEN_COMPARISON: ComparisonReport = {
  headline: 'The 30-second spot engages faces and language; the cut-down hooks faster.',
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
    'Open the 30-second spot on the product, as the cut-down does. Keep a short presenter shot in both versions.',
}
