import { describe, expect, it } from 'vitest'

import { generate, stripPropertyTitles } from './gen-api-types.mjs'

describe('stripPropertyTitles', () => {
  it('drops title keywords on properties but keeps definition titles', () => {
    const schema = {
      $defs: {
        Clip: {
          title: 'Clip',
          type: 'object',
          properties: { duration_s: { title: 'Duration S', type: 'number' } },
        },
      },
    }

    const out = stripPropertyTitles(schema)

    expect(out.$defs.Clip.title).toBe('Clip')
    expect(out.$defs.Clip.properties.duration_s).toEqual({ type: 'number' })
  })

  it('keeps properties that are named "title"', () => {
    const schema = {
      $defs: {
        Note: {
          title: 'Note',
          type: 'object',
          properties: { title: { title: 'Title', type: 'string' } },
          required: ['title'],
        },
      },
    }

    const out = stripPropertyTitles(schema)

    expect(out.$defs.Note.properties.title).toEqual({ type: 'string' })
    expect(out.$defs.Note.required).toEqual(['title'])
  })
})

describe('generate', () => {
  it('emits one exported type per definition', async () => {
    const source = await generate({
      $defs: {
        Word: {
          title: 'Word',
          type: 'object',
          properties: {
            text: { title: 'Text', type: 'string' },
            start: { title: 'Start', type: 'number' },
          },
          required: ['text', 'start'],
        },
      },
    })

    expect(source).toContain('export interface Word {')
    expect(source).toContain('text: string')
    expect(source).not.toContain('ApiSchema {}')
    expect(source).not.toContain('type Text =')
  })
})
