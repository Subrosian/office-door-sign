const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');

async function page(replies) {
    const label = {textContent: 'Update'};
    const button = {disabled: false, querySelector: () => label};
    const notice = {id: 'updateNotice', hidden: true, textContent: ''};
    let reloads = 0;
    let initial = true;
    const context = vm.createContext({
        document: {getElementById: id => id === 'updateButton' ? button : notice},
        confirm: () => true, location: {reload: () => reloads++},
        Date, AbortSignal, setTimeout: callback => callback(),
        fetch: async () => {
            if (initial) { initial = false; return {ok: true, json: async () => ({status: 'idle'})}; }
            const next = replies.shift();
            assert.ok(next, 'Unexpected request');
            if (next instanceof Error) throw next;
            return {ok: next.ok !== false, json: async () => next};
        }
    });
    vm.runInContext(fs.readFileSync(require.resolve('../app/static/update.js'), 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    return {button, notice, label, reloads: () => reloads};
}

test('update reconnects and reloads only after a confirmed new backend', async () => {
    const ui = await page([
        {token: 'one', status: 'updating', message: 'Downloading'},
        new Error('Connection closed during reload'),
        {token: 'one', status: 'restarting', message: 'Restarting'},
        {token: 'one', status: 'complete', version: '1.2.0'}
    ]);
    await ui.button.onclick();
    assert.equal(ui.reloads(), 1);
    assert.match(ui.notice.textContent, /Running version 1.2.0/);
});

test('update failure stays visible and permits retry', async () => {
    const ui = await page([
        {token: 'one', status: 'updating'},
        {token: 'one', status: 'failed', message: 'Download failed'}
    ]);
    await ui.button.onclick();
    assert.equal(ui.reloads(), 0);
    assert.equal(ui.notice.textContent, 'Download failed');
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.label.textContent, 'Update');
});

test('legacy updater never reports an unconfirmed success', async () => {
    const ui = await page([{status: 'started'}]);
    await ui.button.onclick();
    assert.match(ui.notice.textContent, /press Update again/);
    assert.equal(ui.reloads(), 0);
});

test('a rejected update shows the server error', async () => {
    const ui = await page([{ok: false, error: 'An update is already running'}]);
    await ui.button.onclick();
    assert.equal(ui.notice.textContent, 'An update is already running');
    assert.equal(ui.button.disabled, false);
});
