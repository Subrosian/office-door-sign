const schedulesDialog = document.getElementById('schedulesDialog');
const scheduleRows = document.getElementById('scheduleRows');
const scheduleError = document.getElementById('scheduleError');
const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

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
    row.append(days, timeLabel, statusLabel, remove);
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
        document.getElementById('scheduleTimezone').textContent = `Uses the Pi’s local time (${data.timezone}).`;
        data.schedules.forEach(addScheduleRow);
        schedulesDialog.showModal();
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
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({schedules})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not save schedules.');
        schedulesDialog.close();
    } catch (error) { scheduleError.textContent = error.message; }
    finally { save.disabled = false; }
};
