document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('leaderboard_data.json');
        const data = await res.json();
        renderLeaderboard(data);
        renderStats(data);
    } catch (e) {
        document.getElementById('leaderboard-body').innerHTML = 
            '<tr><td colspan="4">No results yet</td></tr>';
    }
});

function renderLeaderboard(data) {
    const tbody = document.getElementById('leaderboard-body');
    
    if (!data.models?.length) {
        tbody.innerHTML = '<tr><td colspan="4">No results yet</td></tr>';
        return;
    }

    tbody.innerHTML = data.models.map((model, i) => {
        const s = data.model_stats[model];
        const squares = data.exams.map(exam => {
            const result = data.exam_results[exam]?.[model];
            const passed = result?.passed;
            return `<div class="square ${passed ? 'passed' : 'failed'}"></div>`;
        }).join('');
        const displayName = s.display_name || model;
        const colonIdx = displayName.lastIndexOf(':');
        const badge = colonIdx !== -1 ? `<span class="badge">${displayName.slice(colonIdx + 1)}</span>` : '';
        const harness = s.harness ? `<span class="badge harness-badge" title="Harness: ${esc(s.harness)}">${esc(s.harness)}</span>` : '';
        return `
            <tr onclick="window.location.href='detail.html?model=${encodeURIComponent(model)}'" class="clickable">
                <td class="rank">${i + 1}</td>
                <td class="model">${esc(displayName)} ${badge} ${harness}</td>
                <td class="score">${s.passed}/${s.total}<br><small>${s.total_steps}/${s.max_steps} steps</small></td>
                <td class="squares-cell"><div class="squares">${squares}</div></td>
            </tr>
        `;
    }).join('');
}

function renderStats(data) {
    document.getElementById('total-models').textContent = data.total_models || 0;
    document.getElementById('total-exams').textContent = data.total_exams || 0;
    if (data.generated_at) {
        document.getElementById('last-updated').textContent = 
            new Date(data.generated_at).toLocaleDateString();
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
