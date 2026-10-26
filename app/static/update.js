const softwareUpdateButton = document.getElementById('updateButton');
const updateNotice = document.getElementById('updateNotice') || document.createElement('p');
if (!updateNotice.id) {
    updateNotice.id = 'updateNotice';
    updateNotice.setAttribute('role', 'status');
    document.querySelector('.admin-header').after(updateNotice);
}
let watchingUpdate = false;

function showUpdate(message, busy) {
    updateNotice.hidden = false;
    updateNotice.textContent = message;
    softwareUpdateButton.disabled = busy;
    softwareUpdateButton.querySelector('.button-label').textContent = busy ? 'Updating…' : 'Update';
}

async function watchUpdate(token) {
    if (watchingUpdate) return;
    watchingUpdate = true;
    const deadline = Date.now() + 610000;
    try {
        while (Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            let response;
            try {
                response = await fetch('/api/update', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
            } catch (_) {
                showUpdate('Waiting for the app to reconnect…', true);
                continue;
            }
            if (!response.ok) throw new Error('Could not check update progress. Reload this page to reconnect.');
            const data = await response.json();
            if (token && data.token !== token) throw new Error('Update tracking changed. Reload this page to check its status.');
            if (data.status === 'complete') {
                showUpdate(`Update complete. Running version ${data.version}. Reloading…`, true);
                location.reload();
                return;
            }
            if (data.status === 'failed') throw new Error(data.message || 'Update failed.');
            showUpdate(data.message || 'Updating…', true);
        }
        throw new Error('The app did not reconnect after the update. Reload this page to check its status.');
    } catch (error) {
        showUpdate(error.message, false);
    } finally {
        watchingUpdate = false;
    }
}

softwareUpdateButton.onclick = async () => {
    if (!confirm('Update Office Door Sign and restart the app? Your schedules and settings will be kept.')) return;
    showUpdate('Starting update…', true);
    try {
        const response = await fetch('/api/update', {method: 'POST'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not start update.');
        if (!data.token) throw new Error('The older updater has started. Once the files finish downloading, press Update again to load the new service-reload support.');
        showUpdate(data.message, true);
        await watchUpdate(data.token);
    } catch (error) {
        showUpdate(error.message, false);
    }
};

async function restoreUpdateProgress() {
    try {
        const response = await fetch('/api/update', {cache: 'no-store'});
        if (!response.ok) return;
        const data = await response.json();
        if (data.status === 'updating' || data.status === 'restarting') {
            showUpdate(data.message, true);
            await watchUpdate(data.token);
        } else if (data.status === 'failed') {
            showUpdate(data.message, false);
        }
    } catch (_) { /* A click can retry if the backend is briefly unavailable. */ }
}
restoreUpdateProgress();
