import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { compileScript, parse } from '@vue/compiler-sfc'
import ts from 'typescript'

// Use the project's existing Vue/TS compilers to exercise the real component in
// Node's test runner. No browser, new test framework, or production data needed.
async function loadTypescript(source) {
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  })
  const code = outputText.replace(
    /from ["']([^"']+)["']/g,
    (_, dependency) => `from ${JSON.stringify(import.meta.resolve(dependency))}`,
  )
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}

const { splitLeaderboard } = await loadTypescript(
  await readFile(new URL('../src/services/leaderboard.ts', import.meta.url), 'utf8'),
)
const filename = new URL('../src/components/LeaderboardTable.vue', import.meta.url)
const { descriptor } = parse(await readFile(filename, 'utf8'), { filename: filename.pathname })
const compiled = compileScript(descriptor, { id: 'leaderboard-table-tests', inlineTemplate: true })
const { default: LeaderboardTable } = await loadTypescript(compiled.content)

function player(id, place = null, score = null, completed = false) {
  return {
    participant_id: id,
    display_name: `@player_${id}`,
    place,
    total_score: score,
    completed,
    closed_questions: completed ? 10 : 3,
    status: completed ? 'completed' : 'playing',
  }
}

test('top three finishers appear only in cards; fourth place and playing users remain in table', () => {
  const rows = [
    player(1, 1, 900, true),
    player(2, 2, 800, true),
    player(3, 3, 700, true),
    player(4, 4, 600, true),
    player(5),
  ]
  const result = splitLeaderboard(rows)
  assert.deepEqual(
    result.podium.map((p) => p.participant_id),
    [1, 2, 3],
  )
  assert.deepEqual(
    result.table.map((p) => p.participant_id),
    [4, 5],
  )
})

test('unfinished players never fill empty podium positions', () => {
  const rows = [player(1, 1, 90, true), player(2), player(3), player(4)]
  const result = splitLeaderboard(rows)
  assert.deepEqual(
    result.podium.map((p) => p.participant_id),
    [1],
  )
  assert.deepEqual(
    result.table.map((p) => p.participant_id),
    [2, 3, 4],
  )
  assert.deepEqual(splitLeaderboard(rows.slice(1)).podium, [])
})

test('table masks unfinished scores and has plain nicknames without adjacent icons', async () => {
  const rows = [player(4, 4, 600, true), player(5, null, 9999)]
  const html = await renderToString(
    createSSRApp(LeaderboardTable, { players: rows, count: 10, search: '', hasLeaders: true }),
  )
  const body = html.split('<tbody>')[1].split('</tbody>')[0]
  assert.match(body, /600/)
  assert.match(body, /В игре/)
  assert.doesNotMatch(body, /9999|avatar|completed-icon|<svg/)
  assert.match(body, /@player_4/)
  assert.match(body, /@player_5/)
})

test('an empty table below the podium does not claim first place is vacant', async () => {
  const html = await renderToString(
    createSSRApp(LeaderboardTable, { players: [], count: 10, search: '', hasLeaders: true }),
  )
  assert.match(html, /Других участников пока нет/)
  assert.doesNotMatch(html, /Первое место пока свободно/)
})
