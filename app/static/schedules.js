const schedulesDialog = document.getElementById('schedulesDialog');
const scheduleRows = document.getElementById('scheduleRows');
const scheduleError = document.getElementById('scheduleError');
const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const timezoneSelect = document.getElementById('scheduleTimezoneSelect');
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const timezones = new Set(['UTC', browserTimezone]);
if (Intl.supportedValuesOf) Intl.supportedValuesOf('timeZone').forEach(zone => timezones.add(zone));
[...timezones].sort().forEach(zone => timezoneSelect.add(new Option(zone.replaceAll('_', ' '), zone)));
let serverTime = 0;
let timeReceived = 0;
let serverOffset = '';

function updateScheduleDiagnostics(data) {
    serverTime = Date.parse(data.current_time);
    timeReceived = Date.now();
    serverOffset = data.current_time.slice(-6);
    const health = data.scheduler || {};
    const current = buttons.find(button => button.dataset.status === data.status)?.textContent || data.status;
    document.getElementById('schedulerHealth').textContent = health.error
        ? `Scheduler error: ${health.error}`
        : `Current sign: ${current}. ${health.running ? 'Background scheduler running.' : 'Background scheduler unavailable; sign refresh checks are active.'}`;
    [...scheduleRows.children].forEach(row => {
        const lastRun = data.last_runs?.[row.dataset.id];
        row.querySelector('.schedule-last-run').textContent = lastRun
            ? `Last ran: ${lastRun.replace('T', ' ')}` : 'Has not run yet.';
    });
    showScheduleClock();
}

async function refreshScheduleDiagnostics() {
    if (!schedulesDialog.open) return;
    try {
        const response = await fetch('/api/schedules', {cache: 'no-store'});
        if (!response.ok) throw new Error('Could not check scheduler.');
        updateScheduleDiagnostics(await response.json());
    } catch (error) {
        document.getElementById('schedulerHealth').textContent = 'Cannot reach scheduler. Check the connection to the sign.';
    }
}
setInterval(refreshScheduleDiagnostics, 2000);

function showScheduleClock() {
    if (!schedulesDialog.open) return;
    const now = new Date(serverTime + Date.now() - timeReceived);
    const timezone = timezoneSelect.value;
    let text;
    if (timezone) {
        text = now.toLocaleString([], {timeZone: timezone, weekday: 'short', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short'});
    } else {
        // Preserve the server's local offset instead of formatting in the browser's timezone.
        const offset = serverOffset === 'Z' ? 0 : (serverOffset[0] === '-' ? -1 : 1) *
            (Number(serverOffset.slice(1, 3)) * 60 + Number(serverOffset.slice(4, 6)));
        text = new Date(now.getTime() + offset * 60000).toLocaleString([], {
            timeZone: 'UTC', weekday: 'short', hour: 'numeric', minute: '2-digit', second: '2-digit'
        }) + ` (UTC${serverOffset})`;
    }
    document.getElementById('scheduleTimezone').textContent = `Scheduler time: ${text}`;
}
timezoneSelect.onchange = showScheduleClock;
setInterval(showScheduleClock, 1000);

function addScheduleRow(item = {days: [0, 1, 2, 3, 4], time: '17:00', status: 'out'}) {
    const row = document.createElement('fieldset');
    row.className = 'schedule-row';
    row.dataset.id = item.id || '';
    const legend = document.createElement('legend');
    legend.textContent = 'Status change';
    row.append(legend);
    const days = document.createElement('div');
    days.className = 'schedule-days';
    dayNames.forEach((name, index) => {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = index;
        input.checked = item.days.includes(index);
        label.append(input, name);
        days.append(label);
    });
    const timeLabel = document.createElement('label');
    timeLabel.textContent = 'At';
    const time = document.createElement('input');
    time.type = 'time';
    time.required = true;
    time.value = item.time;
    timeLabel.append(time);
    const statusLabel = document.createElement('label');
    statusLabel.textContent = 'Set status to';
    const select = document.createElement('select');
    buttons.forEach(button => select.add(new Option(button.textContent, button.dataset.status)));
    select.value = item.status;
    statusLabel.append(select);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Remove';
    remove.onclick = () => row.remove();
    const lastRun = document.createElement('p');
    lastRun.className = 'schedule-last-run';
    lastRun.textContent = 'Has not run yet.';
    row.append(days, timeLabel, statusLabel, remove, lastRun);
    scheduleRows.append(row);
}

document.getElementById('schedulesButton').onclick = async () => {
    closeKeyboard();
    scheduleRows.replaceChildren();
    scheduleError.textContent = '';
    try {
        const response = await fetch('/api/schedules', {cache: 'no-store'});
        if (!response.ok) throw new Error('Could not load schedules.');
        const data = await response.json();
        const timezone = data.timezone || '';
        if (timezone && ![...timezoneSelect.options].some(option => option.value === timezone)) {
            timezoneSelect.add(new Option(timezone, timezone));
        }
        timezoneSelect.value = timezone;
        data.schedules.forEach(addScheduleRow);
        schedulesDialog.showModal();
        updateScheduleDiagnostics(data);
    } catch (error) { alert(error.message); }
};
document.getElementById('addSchedule').onclick = () => addScheduleRow();
document.getElementById('cancelSchedules').onclick = () => schedulesDialog.close();
document.getElementById('schedulesForm').onsubmit = async event => {
    event.preventDefault();
    const schedules = [...scheduleRows.children].map(row => ({
        id: row.dataset.id || undefined,
        days: [...row.querySelectorAll('input:checked')].map(input => Number(input.value)),
        time: row.querySelector('input[type=time]').value,
        status: row.querySelector('select').value
    }));
    const save = document.getElementById('saveSchedules');
    save.disabled = true;
    scheduleError.textContent = '';
    try {
        const response = await fetch('/api/schedules', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({schedules, timezone: timezoneSelect.value})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not save schedules.');
        schedulesDialog.close();
        document.getElementById('scheduleNotice').textContent = 'Schedules saved. Status changes will run when their selected time arrives.';
    } catch (error) { scheduleError.textContent = error.message; }
    finally { save.disabled = false; }
};
